#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Code to manage a swarm of instances.
"""

# program version
__program__ = 'Swarm'
_MajorRelease = 0
_MinorRelease = 1
__version__ = '%d.%d' % (_MajorRelease, _MinorRelease)


import os
import sys
import time
import commands
import threading
import Queue
import boto3
from . import classify
from . import log
from . import utils



class Swarm(object):

    # default attributes when starting a server
    DefaultImage = 'ami-d9d7f9ba'
    DefaultFlavour = 't2.nano'
    #DefaultFlavour = 't2.micro'
    DefaultKey = 'ec2_sydney'
    DefaultSecgroup = 'sydney'.split(',')

    DefaultRegionName = 'ap-southeast-2'
    DefaultConfig = None

    # SSH timeout, seconds
    SshTimeout = 10

    # various timeouts, seconds
    DefaultActiveTimeout = 10*60	# 10 minutes
    DefaultConnectTimeout = 15*60	# 15 minutes

    # various loop times, seconds
    ActiveLoopWait = 30
    ConnectLoopWait = 60

    # sleep time to get around 'rate limit'
    LimitRateErrors = 0.0

    # number of concurrent threads talking to AWS
    NumOSThreads = 5

    # external commands we are going to use
    Cmd_nc = 'nc'	# to check net connectivity

    # time (seconds) to wait for instances to stop
    WaittimeStopServers = 10


    def version(self):
        """Get a tuple of (major, minor) release numbers."""

        return (_MajorRelease, _MinorRelease)


    def __init__(self, auth_dir=None, access_key_id=None,
                 secret_access_key=None, region_name=DefaultRegionName,
                 config=DefaultConfig, verbose=False):
        """Initialize the swarm.

        auth_dir           path to the directory holding keys
        access_key_id      AWS credentials
        secret_access_key  AWS credentials
        region_name        AWS region name
        config             AWS config dict

        The auth_dir directory is searched when guessing which SSH key
        to use when SSHing to a server.

        The AWS credentials, region name and config need not be supplied.  They
        will be looked for in environment variables if required.
        """

        self.log = log.Log('swarm.log', log.Log.DEBUG)

        self.region_name = region_name
        self.verbose = verbose
        self.log('self.verbose=%s' % str(self.verbose))

        # override config stuff from the environment if not given
        access_key_id = self._check_env(access_key_id, 'AWS_ACCESS_KEY_ID')
        secret_access_key = self._check_env(secret_access_key, 'AWS_SECRET_ACCESS_KEY')
        region_name = self._check_env(region_name, 'AWS_REGION_NAME')
        config = self._check_env(config, 'AWS_CONFIG')

        self.ec2 = boto3.resource(service_name='ec2',
                                  aws_access_key_id=access_key_id,
                                  aws_secret_access_key=secret_access_key,
                                  region_name=region_name, config=config)

        # are we paranoid enough yet??
        access_key_id = 'DEADBEEF DEADBEEF DEADBEEF DEADBEEF DEADBEEF'
        secret_access_key = 'DEADBEEF DEADBEEF DEADBEEF DEADBEEF DEADBEEF'
        del access_key_id, secret_access_key
        # are we paranoid enough yet??
        # not that it matters much in a GC language

        # get absolute path to user ~/.ssh directory
        self.ssh_dir = os.path.expanduser('~/.ssh')
        if auth_dir is not None:
            self.ssh_dir = auth_dir

        # check that we have some external commands installed
        self.check_external(self.Cmd_nc)

        # get data about running instances
        names_already_used = []
        i_coll = self.ec2.instances.filter(Filters=[])
        for instance in list(i_coll):
            if instance.state['Name'] in ('pending', 'running'):
                name = self.get_name(instance)
                if name:
                    names_already_used.append(name)
        if names_already_used:
            self.log('Running instances:')
            for i in names_already_used:
                self.log('    %s' % i)
        else:
            self.log('No running instances')

        self.ec2c = boto3.client('ec2')

        # get a list of regions
        self.regions = self._get_regions()
        if self.verbose:
            self.log('Regions:\n%s' % str(self.regions))

        # get a list of zones
        self.zones = self._get_availability_zones()
        if self.verbose:
            self.log('Zones:\n%s' % str(self.zones))

        self.log('Swarm %s initialized!' % __version__)


    def instances(self):
        """Returns a list of all *running* instances."""

        result = []
        for instance in sorted(list(self.ec2.instances.all())):
            if instance.state['Name'] == 'running':
                result.append(instance)

        return result

    def start(self, num, name, image=DefaultImage,
              flavour=DefaultFlavour, key=DefaultKey,
              secgroup=DefaultSecgroup, userdata=None):
        """Start 'num' instances, return list of new instances.

        num       number of instances to start
        name      name of server, may contain {number} formatting
        image     image ID or name
        flavour   flavour of the server to start
        key       the key pair name
        secgroup  the security group(s) to use, list of strings
        userdata  userdata string, may be None
        """

        self.log('Starting %d instances, name=%s, flavour=%s, key=%s, secgroup=%s'
                 % (num, name, flavour, key, str(secgroup)))
        self.log('                     image=%s' % image)

        # get list of server names already in use
        names_already_used = []
        for server in self.instances():
            if server.state['Name'] in ('pending', 'running'):
                running_name = self.get_name(server)
                names_already_used.append(running_name)

        result = []
        instance_number = 0
        number_names = 0
        pending_names = []

        # generate unique instance names
        # result is 'pending_names': list of names to call new instances
        self.log.debug('name=%s, names_already_used=%s' % (name, str(names_already_used)))
        while number_names < num:
            # look for an unused name
            instance_number += 1
            instance_name = name.format(number=instance_number)
            self.log.debug('instance_number=%d, name=%s, instance_name=%s' % (instance_number, name, instance_name))
            if instance_name in names_already_used:
                if instance_number > 999:
                    # runaway search
                    msg = ("Runaway name search, instance_name=%s.\n"
                           "Perhaps name doesn't have a {number} format and name already used?"
                           % instance_name)
                    raise Exception(msg)
                continue
            self.log('new server name=%s' % instance_name)
            number_names += 1
            pending_names.append(instance_name)
            names_already_used.append(instance_name)

        self.log('pending_names=%s' % str(pending_names))

        pending_instances = self.ec2.create_instances(ImageId=image,
                                                      InstanceType=flavour,
                                                      KeyName=key,
                                                      SecurityGroups=secgroup,
                                                      MinCount=num,
                                                      MaxCount=num)

        self.log('started %d instances, flavour=%s, key=%s, secgroup=%s, image=%s'
                 % (num, flavour, key, str(secgroup), image))

        # wait until instances are running and then name them
        self.log('Start of Name tagging')
        if pending_instances:
            for (server, name) in zip(pending_instances, pending_names):
                server.wait_until_running()
                server.create_tags(Tags=[{'Key': 'Name', 'Value': name}])
                self.log('Instance %s tagged as Name=%s' % (server.id, name))

        return pending_instances

    def terminate(self, instances, wait=False):
        """Terminate instances in list, optionally wait until actually stopped."""

        # kill all instances in list
        for i in instances:
            self.log('terminating: %s' % str(i))
            i.terminate()

        # wait until all actually stopped, if required
        if wait:
            self.log('Waiting until all instances actually terminated...')
            while instances:
                new_instances = []
                for i in instances:
                    refreshed = self.ec2.Instance(i.id)
                    if refreshed.state['Name'] != 'terminated':
                        new_instances.append(i)
                instances = new_instances

                time.sleep(self.WaittimeStopServers)
            self.log('All instances terminated')

    def get_name(self, instance):
        """Get a running instance name from .tags."""

        if instance.tags:
            for d in instance.tags:
                if 'Key' in d and d['Key'] == 'Name':
                    return d['Value']
        return None

#    def refresh(self, instances):
#        """Refresh a list of instances."""
#
#        result = []
#
#        for s in instances:
#            try:
#                refresh_s = s.manager.get(s.id)
#            except exceptions.NotFound:
#                # ignore as it's probably just a server stopping
#                continue
#            result.append(refresh_s)
#
#        return result

    def wait(self, instances, state, timeout=DefaultConnectTimeout):
        """Wait until all instances have the required state.

        Returns a list of server info tuples:
            (output, status, ip, name)
        """

        self.log.info("wait: Waiting on %d instances for state '%s'"
                      % (len(instances), state))

        # ensure all machines are ACTIVE
        self.wait_active(instances, timeout)

        self.log.info("wait: All %d instances are ACTIVE" % len(instances))
        if state == 'active':
            return

        # prepare for timeout: get start time
        start = time.time()

        # list of sane instances
        sane_instances = []

        # wait until all all instances running or timed out
        cmd = '%s -z -w %d %%s 22' % (self.Cmd_nc, self.SshTimeout)
        while instances:
            time.sleep(self.ConnectLoopWait)

            # check instances can connect
            remove_index = []
            instances = self.refresh(instances)     # to pick up status changes
            for (x, server) in enumerate(instances):
                if len(server.networks.items()) == 0:
                    # not ready yet
                    self.log.debug("wait: server %s has no IP yet"
                                   % server.name)
                    break
                ip = instance.public_ip_address
                nc_cmd = cmd % ip
                self.log.debug('wait: doing: %s' % nc_cmd)
                (status, output) = commands.getstatusoutput(nc_cmd)
                if status != 0:
                    self.log.debug('wait: server %s unable to connect'
                                   % server.name)
                    break
                else:
                    sane_instances.append(server)
                    remove_index.append(x)
                    self.log.debug('wait: server %s connected!'
                                   % server.name)

            # remove instance_ids that have connected
            remove_index.sort(reverse=True) # remove higher numbers first
            for i in remove_index:
                instances.pop(i)

            # check for timeout
            delta = time.time() - start
            self.log.debug('wait: delta=%d, timeout=%d'
                           % (int(delta), timeout))
            if delta > timeout:
                break

        # delete the failed instances
        if instances:
            self.log.info('wait: %d instances failed - deleting'
                          % len(instances))
            self.log.critical('Would delete these instances, but chicken:\n%s'
                              % str([s.name for s in instances]))
#            self.stop(instances)

        # return the connected instances
        self.log.info('wait: %d instances connected' % len(sane_instances))
        return self.refresh(sane_instances)

    def wait_connect(self, instances, timeout=DefaultConnectTimeout):
        """Wait until all instances are ACTIVE and have a connection.

        Returns a list of refreshed server instances.
        """

        # ensure all machines are ACTIVE
        self.wait_active(instances, timeout)

        self.log.info('wait_connect: Waiting on %d instances' % len(instances))

        # prepare for timeout: get start time
        start = time.time()

        # list of sane instances
        sane_instances = []

        # wait until all all instances running or timed out
        cmd = '%s -z -w %d %%s 22' % (self.Cmd_nc, self.SshTimeout)
        while instances:
            time.sleep(self.ConnectLoopWait)

            # check instances can connect
            remove_index = []
            instances = self.refresh(instances)     # to pick up status changes
            for (x, server) in enumerate(instances):
                if len(server.networks.items()) == 0:
                    # not ready yet
                    self.log.debug("wait_connect: server %s has no IP yet"
                                   % server.name)
                    break
                ip = instance.public_ip_address
                nc_cmd = cmd % ip
                self.log.debug('wait_connect: doing: %s' % nc_cmd)
                (status, output) = commands.getstatusoutput(nc_cmd)
                if status != 0:
                    self.log.debug('wait_connect: server %s unable to connect'
                                   % server.name)
                    break
                else:
                    sane_instances.append(server)
                    remove_index.append(x)
                    self.log.debug('wait_connect: server %s connected!'
                                   % server.name)

            # remove instance_ids that have connected
            remove_index.sort(reverse=True) # remove higher numbers first
            for i in remove_index:
                instances.pop(i)

            # check for timeout
            delta = time.time() - start
            self.log.debug('wait_connect: delta=%d, timeout=%d'
                           % (int(delta), timeout))
            if delta > timeout:
                break

        # delete the failed instances
        if instances:
            self.log.info('wait_connect: %d instances failed - deleting'
                          % len(instances))
            self.log.critical('Would delete these instances, but chicken:\n%s'
                              % str([s.name for s in instances]))
#            self.stop(instances)

        # return the connected instances
        self.log.info('wait_connect: %d instances connected' % len(sane_instances))
        return self.refresh(sane_instances)

    def reboot(self, instances):
        """Soft reboot instances in list."""

        for s in instances:
            self.log('soft rebooting: %s' % str(s))
            s.reboot(reboot_type=instances.REBOOT_SOFT)


    def reboot_hard(self, srvs):
        """Hard reboot instances in list."""

        for s in srvs:
            self.log('hard rebooting: %s' % str(s))
            s.reboot(reboot_type=instances.REBOOT_HARD)


    def filter(self, instances, *args):
        """Apply one or more filters to a server list.

        instances  the list of instances to filter
        *args    one or more functions to filter with

        Returns a list of instances for which all filters return True.
        """

        result = []

        for s in instances:
            for f in args:
                if not f(s):
                    break
            else:
                result.append(s)

        return result


    def union(self, instances1, instances2):
        """Return union of two server lists.

        Returns list of instances that are in either list.
        """

        result = instances1

        for s in instances2:
            if s not in result:
                result.append(s)

        return result


    def intersection(self, instances1, instances2):
        """Return list of instances that are in both input lists.

        Returns list of instances that are in both lists.
        """

        result = []

        for s1 in instances1:
            for s2 in instances2:
                if s1 == s2:
                    result.append(s1)

        return result


    def info(self, instances, *args):
        """Return list of tuples of information about instances.

        instances  list of instances
        args       tuple of info functions

        Returns a list of tuples of information, same order as functions.
        For example, s.info(instances, hostname, ip) returns a list of
        (hostname, ip), one for each server in the list.

        Uses a thread pool to perform the operation.
        """

        self.log.debug('info: %d instances' % len(instances))
        args_names = [f.func_name for f in args]
        self.log.debug('info: args=%s' % str(args_names))

        return self._apply_threads(instances, *args)


    def copy(self, instances, src, dst, *args):
        """Copy a file to each instance in the list.

        instances  list of instances
        src      path to a file to copy
        dst      place on instance to copy file to
        *args    callbacks to adorn each VM output
                 (applied to each instance)

        Copies in parallel.  Should need no throttling.
        """

        # thread class - run a copy via SCP
        class CopyThread(threading.Thread):
            def __init__(self, instance, cmd, queue, args):
                threading.Thread.__init__(self)
                self.instance = instance
                self.cmd = cmd
                self.queue = queue
                self.args = args

            def run(self):
                # execute the command, queue the result
                adorn_list = []
                for cb in args:
                    adorn_list.append(cb(self.instance))
                (status, output) = commands.getstatusoutput(self.cmd)
                result = [output, status]
                result.extend(adorn_list)
                self.queue.put(result)

        # queue where results are placed
        result_queue = Queue.Queue()

        # generate SCP command, pass to thread
        cmd = ('scp -q -i %%s -o "ConnectTimeout %d" -o "BatchMode yes" '
               '-o "CheckHostIP no" '
               '-o "PreferredAuthentications publickey" '
               '-o "StrictHostKeyChecking no" '
               '%s ec2-user@%%s:%s' % (self.SshTimeout, src, dst))
        for instance in instances:
            ip = instance.public_ip_address
            key_file = self.guess_key(instance.key_name)
            copy_cmd = cmd % (key_file, ip)
            CopyThread(instance, copy_cmd, result_queue, args).start()

        # get results and build return string
        result = []
        while threading.active_count() > 1 or not result_queue.empty():
            while not result_queue.empty():
                result_tuple = result_queue.get()
                result.append(result_tuple)
            time.sleep(1)

        return result


    def cmd(self, instances, cmd, *args):
        """Execute a command on each instance in the list.

        instances  list of instances
        cmd      command to execute on each instance
        *args    callbacks to adorn each VM output
                 (applied to each instance)

        Returns list of iterables:
           (output, cb1, cb2, ...)

        Uses a thread pool to perform the operation.
        """

        self.log.debug('cmd: %d instances' % len(instances))
        args_names = [f.func_name for f in args]
        self.log.debug('cmd: args=%s' % str(args_names))

        def exec_func(instance):
            """Function to perform command on instance."""

            key_file = self.guess_key(instance.key_name)
            ip = instance.public_ip_address

            ssh = ('ssh -q -i %s -o "ConnectTimeout %d" -o "BatchMode yes" '
                   '-o "CheckHostIP no" '
                   '-o "PreferredAuthentications publickey" '
                   '-o "StrictHostKeyChecking no" '
                   'ec2-user@%s "%s" 2>&1' % (key_file, self.SshTimeout, ip, cmd))
            self.log.debug('SSH cmd: %s' % ssh)
            (status, output) = commands.getstatusoutput(ssh)

            return (status, output)

        enhanced_args = [exec_func]
        enhanced_args.extend(args)

        result = self._apply_threads(instances, *enhanced_args)
        self.log.debug('cmd: result=%s' % str(result))

        return result

    ##########
    # Info callbacks
    ##########

    def info_name(self):
        """Given a instance, return name string."""

        def name_info(instance):
#            return instance.name
            return self.get_name(instance)

        return name_info


    def info_flavour(self):
        """Given a instance, return flavor index."""

        def flavour_info(instance):
            return int(instance.flavor['id'])

        return flavour_info


    def info_key(self):
        """Given a instance, return key name."""

        def key_info(instance):
            return int(instance.flavor['id'])

        return key_info


    def info_ncpu(self):
        """Given a instance, return number of CPUs."""

        def ncpu_info(instance):
            return self.flavour2ncpu[int(instance.flavor['id'])]

        return ncpu_info


    def info_hostname(self):
        """Given a instance, return hostname string."""

        def hostname_info(instance):
            # have to ssh to instance and run 'hostname' command
            ip = instance.public_ip_address
            key = instance.key_name

            # get path to key file - guess from key name
            key_file = self.guess_key(key)
            options = ('-o "ConnectTimeout %d" -o "BatchMode yes" '
                       '-o "CheckHostIP no" '
                       '-o "PreferredAuthentications publickey" '
                       '-o "StrictHostKeyChecking no"' % self.SshTimeout)
            cmd = ('ssh -q -i %s %s ec2-user@%s hostname'
                   % (key_file, options, ip))
            (status, output) = commands.getstatusoutput(cmd)

            return output

        return hostname_info


    def info_ip(self):
        """Given a instance, return IP string."""

        def ip_info(instance):
#            return instance.networks.items()[0][1][0]
            return instance.public_ip_address

        return ip_info


    def info_classify(self):
        """Given a instance, return classification string."""

        # string in log when machine restarts
        RestartString = "Linux version"

        def classify_info(instance):
            """Given a instance, get console log and classify health."""

            # get complete console log for the instance
            error = False
            for _ in range(5):
                try:
                    console = instance.get_console_output() #.output
                except exceptions.BadRequest:
                    console = 'Bad request?'
                    error = True
                except TypeError, e:
                    console = 'AWS got TypeError: %s' % str(e)
                    error = True
                    break
                else:
                    error = False
                    break
            if error:
                return console

            # ensure we have only log since latest boot
            while RestartString in console:
                index = console.index(RestartString)
                console = console[index+1:]

            # classify the VM from the log contents
            return classify.classify(console)

        return classify_info

    ##########
    # Filters
    ##########

    def filter_name_prefix(self, prefix):
        """Return filter for instance name starts with a prefix."""

        def check_name(instance):
            """Check instance 'instance' has name that starts with 'prefix'."""

            if instance.tags:
               for d in instance.tags:
                   if 'Key' in d and d['Key'] == 'Name':
                       return d['Value'].startswith(prefix)

        return check_name

    def filter_state(self, state):
        """Return filter for instances with a given state."""

        return lambda instance: instance.state['Name'] == state

    def filter_flavour(self, flavour):
        """Return filter for instance flavour."""

        flavour_id = self.str2flavour[flavour]

        return lambda instance: (int(instance.flavor['id']) == flavour_id)


    def filter_image(self, image):
        """Return filter for instance image."""

        image = self.ensure_image_id(image)

        return lambda instance: (instance.image['id'] == image)

    ##########
    # utility/debug functions
    ##########

    def check_external(self, cmd):
        """Check that a program external to swarm exists.

        Raise an exception if command isn't installed.
        A little harsh, perhaps, but better than fossicking around
        in log files to see what wrong!

        Here we *must* assume the 'which' program is available.
        """

        exists_cmd = 'which %s' % cmd
        (status, output) = commands.getstatusoutput(exists_cmd)
        if status != 0:
            raise Exception("Sorry, the program '%s' isn't installed\n"
                            "(or maybe 'which' isn't installed?)" % cmd)


    def dump_instance(self, instance):
        self.log('instance:\n%s' % utils.obj_dump(instance))


    def guess_key(self, key):
        """Try to guess the key filename from key name."""

        self.log.debug('guess_key: key=%s, .ssh_dir=%s' % (key, self.ssh_dir))
        key_file = None
        for f in os.listdir(self.ssh_dir):
            path = os.path.join(self.ssh_dir, f)
            if os.path.isfile(path):
                filename = os.path.basename(f)
                if filename == key:
                    key_file = path
                    break
                (prefix, ext) = os.path.splitext(filename)
                if prefix == key and key_file is None:
                    key_file = path
                    break

        if key_file is None:
            msg = ("Can't find key file matching '%s'" % key)
            raise Exception(msg)

        self.log.debug('guess_key: key %s -> key_file %s' % (key, str(key_file)))

        return key_file


    def flavour_type_to_index(self, type_str):
        """Convert a flavour type string to index."""

        result = self.str2flavour.get(type_str, None)
        if result is None:
            msg = ("Type '%s' not found: type_str=%s (%s)"
                   % (str(type_str), type(type_str)))
            raise Exception(msg)

        return result


    def flavour_index_to_type(self, index):
        """Convert a flavour index to the type string."""

        result = self.flavour2str.get(int(index), None)
        if result is None:
            msg = ("Index not found: index=%s (%s)"
                   % (str(index), type(index)))
            raise Exception(msg)

        return result


    def flavour_index_to_ncpu(self, index):
        """Convert a flavour index to number of cpus."""

        result = self.flavour2ncpu.get(index, None)
        if result is None:
            msg = ("Index '%s' not found: index=%s (%s)"
                   % (str(index), type(index)))
            raise Exception(msg)

        return result


    def ensure_image_id(self, image):
        """Ensure we have an image ID, convert name to ID if necessary."""

        # check if image given is NAME, convert to ID
        images = self.client.images.list()
        found = False
        for i in images:
            if i.human_id == image:
                if found:
                    msg = ("Sorry, image name '%s' found twice in image list"
                           % image)
                    self.log.error(msg)
                    raise Exception(msg)
                found = True
                image = i.id
        # now check that image actually exists in the image list
        found = False
        for i in images:
            if i.id == image:
                found = True
                break
        if not found:
            msg = ("Sorry, image ID '%s' not found in image list"
                   % image)
            self.log.error(msg)
            raise Exception(msg)

        return image


    def _apply_threads(self, instances, *args):
        """Evaluate all 'args' functions over 'instances'.

        instances  a list of instance objects
        args     tuple of operations

        Use a pool of 'NumOSThreads' threads to do it.
        """

        self.log.debug('_apply_threads: NumOSThreads=%d' % self.NumOSThreads)
        self.log.debug('_apply_threads: %d instances' % len(instances))
        self.log.debug('_apply_threads: args=%s' % str(args))

        # the actual thread code
        class doitThread(threading.Thread):
            def __init__(self, input_q, output_q, args):
                threading.Thread.__init__(self)
                self.input_q = input_q
                self.output_q = output_q
                self.args = args

            def run(self):
                # read a instance off the input queue and process it
                # if the queue is empty, quit thread
                while not input_q.empty():
                    try:
                        instance = input_q.get_nowait()
                    except Queue.Empty:
                        break

                    result = []
                    for func in self.args:
                        result.append(func(instance))
                    self.output_q.put(result)

        # create input/output queue, fill input queue
        input_q = Queue.Queue()
        output_q = Queue.Queue()

        for instance in instances:
            input_q.put(instance)

        # start worker threads
        for i in xrange(self.NumOSThreads):
            doitThread(input_q, output_q, args).start()

        # pick up results as they are posted to the output queue
        result = []
        while threading.active_count() > 1 or not output_q.empty():
            while not output_q.empty():
                result_tuple = output_q.get()
                result.append(result_tuple)
                self.log.debug('info: result=%s' % str(result_tuple))
            time.sleep(1)

        return result

    @staticmethod
    def _check_env(value, env_str):
        """Maybe overwrite variable from the environment.

        value    value that may be overridden
        env_str  environment variable name

        Returns a value which is either the original value or the
        value from the environment.  The environment overrides the value
        only if the value is None.
        """

        if value is None:
            try:
                value = os.environ[env_str]
            except KeyError:
                pass

        return value

    def _get_regions(self):
        """Return a sorted list of available regions."""

        regions = [r['RegionName'] for r in self.ec2c.describe_regions()['Regions']]
        return sorted(regions)

    def _get_availability_zones(self, region_name=None, state='available'):
        """Return a sorted list of availability zones in the given region.

        region_name  name of the region we want availability zones for
        state        filter on this state
        """

        result = []
        az = self.ec2c.describe_availability_zones()
        for zone in az['AvailabilityZones']:
            if zone['State'] == state:
                result.append(zone['ZoneName'])

        return sorted(result)

    def describe_instances(self, instances):
        """ """

        client = boto3.client('ec2')
        instance_ids = [i.describe_attribute(Attribute='instanceType')['InstanceId'] for i in instances]
        print('instance_ids=%s' % str(instance_ids))

#        data = instance.describe_attribute(Attribute='instanceType')['InstanceId']

        data = client.describe_instances(InstanceIds=instance_ids)
        self.log.debug('data=%s' % str(data))

#        data={u'Reservations': [{u'OwnerId': '558208586350', u'ReservationId': 'r-0c985fbc493161f2c', u'Groups': [], u'Instances': [{u'Monitoring': {u'State': 'disabled'}, u'PublicDnsName': 'ec2-54-206-41-152.ap-southeast-2.compute.amazonaws.com', u'State': {u'Code': 16, u'Name': 'running'}, u'EbsOptimized': False, u'LaunchTime': datetime.datetime(2016, 7, 8, 0, 23, 55, tzinfo=tzutc()), u'PublicIpAddress': '54.206.41.152', u'PrivateIpAddress': '172.31.16.206', u'ProductCodes': [], u'VpcId': 'vpc-248aa941', u'StateTransitionReason': '', u'InstanceId': 'i-00865720a7a35a0b5', u'ImageId': 'ami-d9d7f9ba', u'PrivateDnsName': 'ip-172-31-16-206.ap-southeast-2.compute.internal', u'KeyName': 'ec2_sydney', u'SecurityGroups': [{u'GroupName': 'sydney', u'GroupId': 'sg-1dda4f79'}], u'ClientToken': '', u'SubnetId': 'subnet-bcfdedfa', u'InstanceType': 't2.micro', u'NetworkInterfaces': [{u'Status': 'in-use', u'MacAddress': '0a:10:6c:41:5b:ed', u'SourceDestCheck': True, u'VpcId': 'vpc-248aa941', u'Description': '', u'Association': {u'PublicIp': '54.206.41.152', u'PublicDnsName': 'ec2-54-206-41-152.ap-southeast-2.compute.amazonaws.com', u'IpOwnerId': 'amazon'}, u'NetworkInterfaceId': 'eni-b29d57eb', u'PrivateIpAddresses': [{u'PrivateDnsName': 'ip-172-31-16-206.ap-southeast-2.compute.internal', u'Association': {u'PublicIp': '54.206.41.152', u'PublicDnsName': 'ec2-54-206-41-152.ap-southeast-2.compute.amazonaws.com', u'IpOwnerId': 'amazon'}, u'Primary': True, u'PrivateIpAddress': '172.31.16.206'}], u'PrivateDnsName': 'ip-172-31-16-206.ap-southeast-2.compute.internal', u'Attachment': {u'Status': 'attached', u'DeviceIndex': 0, u'DeleteOnTermination': True, u'AttachmentId': 'eni-attach-2e7f9117', u'AttachTime': datetime.datetime(2016, 7, 8, 0, 23, 55, tzinfo=tzutc())}, u'Groups': [{u'GroupName': 'sydney', u'GroupId': 'sg-1dda4f79'}], u'SubnetId': 'subnet-bcfdedfa', u'OwnerId': '558208586350', u'PrivateIpAddress': '172.31.16.206'}], u'SourceDestCheck': True, u'Placement': {u'Tenancy': 'default', u'GroupName': '', u'AvailabilityZone': 'ap-southeast-2c'}, u'Hypervisor': 'xen', u'BlockDeviceMappings': [{u'DeviceName': '/dev/xvda', u'Ebs': {u'Status': 'attached', u'DeleteOnTermination': True, u'VolumeId': 'vol-15d31bce', u'AttachTime': datetime.datetime(2016, 7, 8, 0, 23, 55, tzinfo=tzutc())}}], u'Architecture': 'x86_64', u'RootDeviceType': 'ebs', u'RootDeviceName': '/dev/xvda', u'VirtualizationType': 'hvm', u'Tags': [{u'Value': 'test1_1', u'Key': 'Name'}], u'AmiLaunchIndex': 0}, {u'Monitoring': {u'State': 'disabled'}, u'PublicDnsName': 'ec2-54-206-27-140.ap-southeast-2.compute.amazonaws.com', u'State': {u'Code': 16, u'Name': 'running'}, u'EbsOptimized': False, u'LaunchTime': datetime.datetime(2016, 7, 8, 0, 23, 55, tzinfo=tzutc()), u'PublicIpAddress': '54.206.27.140', u'PrivateIpAddress': '172.31.16.207', u'ProductCodes': [], u'VpcId': 'vpc-248aa941', u'StateTransitionReason': '', u'InstanceId': 'i-01481911debabb9be', u'ImageId': 'ami-d9d7f9ba', u'PrivateDnsName': 'ip-172-31-16-207.ap-southeast-2.compute.internal', u'KeyName': 'ec2_sydney', u'SecurityGroups': [{u'GroupName': 'sydney', u'GroupId': 'sg-1dda4f79'}], u'ClientToken': '', u'SubnetId': 'subnet-bcfdedfa', u'InstanceType': 't2.micro', u'NetworkInterfaces': [{u'Status': 'in-use', u'MacAddress': '0a:d6:54:0e:74:7d', u'SourceDestCheck': True, u'VpcId': 'vpc-248aa941', u'Description': '', u'Association': {u'PublicIp': '54.206.27.140', u'PublicDnsName': 'ec2-54-206-27-140.ap-southeast-2.compute.amazonaws.com', u'IpOwnerId': 'amazon'}, u'NetworkInterfaceId': 'eni-b59d57ec', u'PrivateIpAddresses': [{u'PrivateDnsName': 'ip-172-31-16-207.ap-southeast-2.compute.internal', u'Association': {u'PublicIp': '54.206.27.140', u'PublicDnsName': 'ec2-54-206-27-140.ap-southeast-2.compute.amazonaws.com', u'IpOwnerId': 'amazon'}, u'Primary': True, u'PrivateIpAddress': '172.31.16.207'}], u'PrivateDnsName': 'ip-172-31-16-207.ap-southeast-2.compute.internal', u'Attachment': {u'Status': 'attached', u'DeviceIndex': 0, u'DeleteOnTermination': True, u'AttachmentId': 'eni-attach-2f7f9116', u'AttachTime': datetime.datetime(2016, 7, 8, 0, 23, 55, tzinfo=tzutc())}, u'Groups': [{u'GroupName': 'sydney', u'GroupId': 'sg-1dda4f79'}], u'SubnetId': 'subnet-bcfdedfa', u'OwnerId': '558208586350', u'PrivateIpAddress': '172.31.16.207'}], u'SourceDestCheck': True, u'Placement': {u'Tenancy': 'default', u'GroupName': '', u'AvailabilityZone': 'ap-southeast-2c'}, u'Hypervisor': 'xen', u'BlockDeviceMappings': [{u'DeviceName': '/dev/xvda', u'Ebs': {u'Status': 'attached', u'DeleteOnTermination': True, u'VolumeId': 'vol-5dd31b86', u'AttachTime': datetime.datetime(2016, 7, 8, 0, 23, 55, tzinfo=tzutc())}}], u'Architecture': 'x86_64', u'RootDeviceType': 'ebs', u'RootDeviceName': '/dev/xvda', u'VirtualizationType': 'hvm', u'Tags': [{u'Value': 'test1_2', u'Key': 'Name'}], u'AmiLaunchIndex': 1}]}], 'ResponseMetadata': {'HTTPStatusCode': 200, 'RequestId': '686bf490-48ae-4bf4-aafd-04a4cb34dfcb'}}

if __name__ == '__main__':
    s = Swarm()
    instances = s.start(1, 'test')
    self.log.debug('instances=%s' % str(instances))
    self.log.debug('s.instances()=%s' % str(s.instances()))
