#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This program is designed to replace an ailing instance, gathering as much
required information from the sick instance as possible.

Usage: swarm replace <options> [<name> [, <name> ...]]

where <options> is zero or more of:
    -a  <auth>      set path to key directory (default ~/.ssh)
    -c  <config>    set the config file to use
    -f  <flavour>   set the image flavour
    -h              print this help and stop
    -i  <image>     sets image to use
    -k  <keyname>   set key to use
    -p  <prefix>    set the name prefix
    -s  <secgroup>  set the security group(s) (can be: 'xyzzy,default')
    -u  <userdata>  path to a userdata script file
    -v              become verbose (cumulative)
    -V              print version and stop
and <name> is the sick instance AWS dashboard name.

Zero or more <name> values may be specified.  If both the '-p' option and one or
more <name>s are given the given <prefix> selects suitable instances and the
instances in that selection with the given <name>s are replaced.

The config and/or command line options are used only if information cannot be
obtained from the running instances.
"""

import os
import sys
import shutil
import time
import getopt
import commands
import tempfile
import traceback

import swarmcore
from swarmcore import log
import swarmcore.utils as utils

log = log.Log('swarm.log', log.Log.DEBUG)


# program version
MajorRelease = 0
MinorRelease = 1

Plugin = {
          'entry': 'replace',
          'version': '%d.%d' % (MajorRelease, MinorRelease),
          'command': 'replace',
         }

# delay while polling status of dying instance
WaitForDyingServer = 5

# default instance values
DefaultAuthPath = os.path.expanduser('~/.ssh')
DefaultRegion = 'ap-southeast-2'
DefaultZone = 'ap-southeast-2b'
DefaultFlavour = 't2.micro'
DefaultImage = None
DefaultKey = 'ec2_sydney'
DefaultNamePrefix = None
DefaultSecgroup = 'sydney'
DefaultUserdata = None

# dictionary to map config names to global names
# the key is the name as it appears in the config file
# the value is the name of the global variable that should be changed
Config2Global = {'image': 'DefaultImage',
                 'flavor': 'DefaultFlavour',
                 'flavour': 'DefaultFlavour',
                 'key': 'DefaultKey',
                 'keypair': 'DefaultKey',
                 'nameprefix': 'DefaultNamePrefix',
                 'prefix': 'DefaultNamePrefix',
                 'name': 'DefaultNamePrefix',
                 'secgroup': 'DefaultSecgroup',
                 'security': 'DefaultSecgroup',
                 'securitygroup': 'DefaultSecgroup',
                 'prefix': 'DefaultNamePrefix',
                 'userdata': 'DefaultUserdata',
                 'auth': 'DefaultAuthPath',
                 'authdir': 'DefaultAuthPath',
                 'authpath': 'DefaultAuthPath',
                }


def usage(msg=None):
    """Print help for the befuddled user."""

    if msg:
        print('*'*60)
        print(msg)
        print('*'*60)
    print(__doc__)        # module docstring used

def load_config(config_file):
    """Set global defaults from the config file."""

    # see if config file exists
    if not os.path.isfile(config_file):
        error("Can't find config file %s" % config_file)

    log.debug("load_config: loading config from '%s'" % str(config_file))

    # read config, look for known variable definitions
    with open(config_file, 'rb') as fd:
        lines = fd.readlines()

    # construct dictionary of globals to update
    updated_globals = {}
    errors = False

    for (l, orig_line) in enumerate(lines):
        line = orig_line.strip()
        if line == '' or line[0] == '#':
            continue

        # expect lines of the form 'name = value'
        fields = line.split('=')
        if len(fields) != 2:
            error('Line %d of %s has bad format: %s'
                  % (l+1, config_file, orig_line))
        (name, value) = fields

        name = name.strip().lower()
        value = value.strip()

        if name not in Config2Global:
            log.warn("Line %d of %s: name '%s' is unrecognized"
                     % (l+1, config_file, name))
            errors = True
            continue

        global_name = Config2Global[name]
        if global_name in updated_globals:
            error("Line %d of %s: '%s' defined twice"
                  % (l+1, config_file, name))
            errors = True
        else:
            # add global+new value to dict - eval() removes any quotes
            updated_globals[global_name] = eval(value)

    if errors:
        sys.exit(1)

    # update globals with values from the config file
    log.debug('load_config: New globals:')
    for (key, value) in updated_globals.items():
        log.debug('    %s: %s,' % (str(key), str(value)))

    globals().update(updated_globals)

def replace(args, kwargs):
    """Replace an existing cloud instance.

    args    list of arg values to be parsed
    kwargs  a dict of default values

    Values potentially parsed from 'args' or found in 'kwargs':
        image     image for instance
        flavour   flavour of instance
        key       key for instance
        secgroup  security group(s)
        userdata  instance startup script path
        auth      path to auth directory
    """

    # parse the command args
    try:
        (opts, args) = getopt.getopt(args, 'a:c:f:hi:k:p:r:s:u:vV',
                                     ['auth=', 'config=', 'flavour=', 'help',
                                      'image=', 'key=', 'prefix=', 'region=',
                                      'secgroup=', 'userdata=', 'verbose',
                                      'version', ])
    except getopt.error, e:
        usage(str(e.msg))
        return 1

    # do -c and -v now
    config = None
    Verbose = False
    for (opt, param) in opts:
        if opt in ['-c', '--config']:
            config = param
        if opt in ['-v', '--verbose']:
            Verbose = True
            log.bump_level()

    # read config file, if we have one
    # this may update the variables just set from defaults
    if config:
        load_config(config)

    # set variables to possibly modified defaults
    auth = DefaultAuthPath
    flavour = DefaultFlavour
    image = DefaultImage
    key = DefaultKey
    name = DefaultNamePrefix
    region = DefaultRegion
    secgroup = DefaultSecgroup
    userdata = DefaultUserdata

    # now parse the options
    # this is the users final chance to change default values
    for (opt, param) in opts:
        if opt in ['-a', '--auth']:
            auth = param
        elif opt in ['-c', '--config']:
            # done above
            pass
        elif opt in ['-f', '--flavour']:
            flavour = param
        elif opt in ['-h', '--help']:
            usage()
            return 0
        elif opt in ['-i', '--image']:
            image = param
        elif opt in ['-k', '--key']:
            key = param
        elif opt in ['-p', '--prefix']:
            name = param
        elif opt in ['-r', '--region']:
            region = param
        elif opt in ['-s', '--secgroup']:
            secgroup = param
        elif opt in ['-u', '--userdata']:
            userdata = param
        elif opt in ['-V', '--version']:
            print('%s %s' % (Plugin['command'], Plugin['version']))
            return 0
        elif opt in ['-v', '--verbose']:
            # done above
            pass

    instances = args
    if len(args) == 0:
        if name is None:
            usage('You must supply name(s) of the instances to replace.')
            return 1

    log.debug('param: instances=%s' % str(instances))
    log.debug('param: name=%s' % str(name))
    log.debug('param: image=%s' % str(image))
    log.debug('param: flavour=%s' % str(flavour))
    log.debug('param: key=%s' % str(key))
    log.debug('param: secgroup=%s' % str(secgroup))
    log.debug('param: userdata=%s' % str(userdata))
    log.debug('param: auth=%s' % str(auth))

    if Verbose:
        print('Replacing instance(s) %s' % str(instances))

    # connect to AWS
    s = swarmcore.Swarm(auth_dir=auth, verbose=Verbose)
    all_instances = s.instances()
    print('all_instances=%s' % str(all_instances))

    # get list of instances satisfying 'prefix' option
    replace_instances = all_instances
    if name:
        replace_instances = []
        for instance in all_instances:
            instance_name = utils.get_instance_name(instance)

            if instance_name.startswith(name):
                replace_instances.append(instance)

    # now check if given instance names and find these in 'replace_instances'
    if instances:
        named_instances = []
        for instance in replace_instances:
            if utils.get_instance_name(instance) in instances:
                named_instances.append(instance)
        replace_instances = named_instances

    print('replace_instances=%s' % str(replace_instances))

    # check we have something to do
    if replace_instances is None:
        if name and instances:
            msg = ("Sorry, didn't find any instances of '%s*' with names '%s'"
                   % (name, str(instances)))
        elif name:
            msg = ("Sorry, didn't find any instances of '%s*'" % name)
        elif instances:
            msg = ("Sorry, didn't find any instances with names in '%s'" % str(instances))
        else:
            msg = "You must specify either the '-p' option, one or more names or both"
        log(msg)
        print(msg)
        sys.exit(10)

    # get instance information
#    help(replace_instances[0])
#    print(str(replace_instances[0].describe_attribute(Attribute='instanceType')))
#    data = replace_instances[0].describe_instances(replace_instances)
#    print('data=%s' % str(data))

    # gather what info we can from the running instances
    running_info = []
    data = s.describe_instances(replace_instances)

    # debug
    log('running_info=%s' % str(running_info))
    log('data=%s' % str(data))

    # if we don't have some required information, get it from the config
    # this will probably never happen
    msg = []
    if not new_name:
        new_name = name
        msg.append('Getting instance name from parameters: %s' % new_name)
    if not new_image:
        new_image = image
        msg.append('Getting instance image from parameters: %s' % new_image)
    if not new_flavour:
        new_flavour = flavour
        msg.append('Getting instance flavour from parameters: %s' % new_flavour)
    if not new_key:
        new_key = key
        msg.append('Getting instance key from parameters: %s' % new_key)
    if not new_security:
        new_security = secgroup
        msg.append('Getting instance security from parameters: %s' % new_security)
    if not new_userdata:
        new_userdata = userdata
        msg.append('Getting instance userdata from parameters: %s' % new_userdata)
    if msg:
        log("Couldn't get some data from running instance:\n%s" % '\n'.join(msg))

    # stop the unsane instance, wait until its really gone
    log('Stopping instance %s' % new_name)
    if Verbose:
        print('Stopping instance %s' % new_name)

    swm.stop([replace_instance], wait=True)

    log('Server %s stopped' % new_name)

    # we must be *absolutely sure* that the instance we just terminated has gone
    log('Ensuring instance %s has really been terminated...' % new_name)
    while True:
        all_instances = swm.instances()
        for s in all_instances:
            if s.name == new_name:
                log('Server %s still around, sleeping...' % new_name)
                time.sleep(1.0)
                continue
        break
    log('Server %s has really gone now' % new_name)

    # start replacement instance
    if Verbose:
        print('Starting new instance %s' % new_name)
    log('Starting 1 instance')

    new = swm.start(1, new_name, image=new_image, flavour=new_flavour, key=new_key,
                    secgroup=new_security, userdata=new_userdata)

    msg = 'Server %s started, waiting for connection' % new_name
    log.debug(msg)
    if Verbose:
        print(msg)

    swm.wait_connect(new)

    msg = 'New instance %s now connected' % new_name
    log.debug(msg)
    if Verbose:
        print(msg)

    if Verbose:
        print('Finished!')

    log.debug('==============================================================')
    log.debug('=========================  FINISHED  =========================')
    log.debug('==============================================================')

    return







#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This program is used to stop a set of instances.
In AWS-speak, set required instances to the 'terminated' state.

Usage: sw_stop <options>

where <options> is zero or more of:
    -h   --help     print this help and stop
    -p   --prefix   name prefix used to select nodes (required)
    -s   --state    state of instances to terminate ('running' is assumed otherwise)
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)
    -w   --wait     wait until instances actually stopped

As an example, the following will stop all instances whose name start 'cxwn' and
will wait until the instances are actually gone:
    sw_stop -p test -w
"""

import os
import sys
import getopt
import swarmcore
from swarmcore import log
from swarmcore import utils
log = log.Log('swarm.log', log.Log.DEBUG)


# program version
MajorRelease = 0
MinorRelease = 1

Plugin = {
          'entry': 'replace',
          'version': '%d.%d' % (MajorRelease, MinorRelease),
          'command': 'replace',
         }


def usage(msg=None):
    """Print help for the befuddled user."""

    if msg:
        print('*'*60)
        print(msg)
        print('*'*60)
    print(__doc__)        # module docstring used

def stop(args, kwargs):
    """Stop a set of instances.

    args    list of arg values to be parsed
    kwargs  a dict of default values

    Values potentially parsed from 'args' or found in 'kwargs':
        num       number of instance to start
        name      instance name prefix
        image     image for instance
        flavour   flavour of instance
        key       key for instance
        secgroup  security group(s)
        state     state of selected instances
        userdata  instance startup script path
        auth      path to auth directory
    """

    global Verbose

    # parse the command args
    try:
        (opts, args) = getopt.getopt(args, 'hp:s:Vviw',
                                     ['help', 'prefix=', 'state=',
                                      'version', 'verbose', 'wait'])
    except getopt.error, e:
        usage(str(e.msg))
        return 1

    Verbose = False
    for (opt, param) in opts:
        if opt in ['-v', '--verbose']:
            Verbose = True
            log.bump_level()

    # now parse the options
    name_prefix = None
    state = 'running'       # we assume that we only stop 'running' instances
    wait = False
    for (opt, param) in opts:
        if opt in ['-h', '--help']:
            usage()
            return 0
        elif opt in ['-p', '--prefix']:
            name_prefix = param
        elif opt in ['-s', '--state']:
            state = param
        elif opt in ['-V', '--version']:
            print('%s v%s' % (Plugin['command'], Plugin['version']))
            return 0
        elif opt in ['-v', '--verbose']:
            pass        # done above
        elif opt in ['-w', '--wait']:
            wait = True

    if len(args) != 0:
        usage("Don't need any params for 'stop'")
        return 1

    # it's too dangerous to allow a global terminate of all instances
    # use '-p ""' if you want to do this
    if name_prefix is None and state is None:
        usage("You must specify instance(s) to stop ('-p' and/or '-s' options).")
        return 1

    # get all instances
    swm = swarmcore.Swarm(verbose=Verbose)
    all_instances = swm.instances()
    if Verbose:
        log('instances=%s' % str(all_instances))

    # get a filtered list of instances depending on name_prefix, state, etc
    prefix_str = '*'        # assume user wants to stop ALL instances
    filtered_instances = all_instances
    if name_prefix is not None:
        prefixes = name_prefix.split(',')
        prefix_str = '*|'.join(prefixes) + '*'
        filtered_instances = []
        for prefix in prefixes:
            f = swm.filter_name_prefix(prefix)
            s = swm.filter(all_instances, f)
            filtered_instances = swm.union(filtered_instances, s)
    if Verbose:
        print('name_prefix=%s, prefix_str=%s' % (str(name_prefix), prefix_str))
        print('filtered_instances=%s' % str(filtered_instances))
        log('name_prefix=%s, prefix_str=%s' % (str(name_prefix), prefix_str))
        log('filtered_instances=%s' % str(filtered_instances))

    state_str = '*'         # assume user wants to stop all states of instances
    state_instances = filtered_instances
    if state is not None:
        state_list = state.split(',')
        state_str = state
        state_instances = []
        for st in state_list:
            f = swm.filter_state(state)
            s = swm.filter(filtered_instances, f)
            state_instances = swm.union(state_instances, s)
    filtered_instances = state_instances
    if Verbose:
        print('state=%s, state_str=%s' % (str(state), state_str))
        print('filtered_instances=%s' % str(filtered_instances))
        log('state=%s, state_str=%s' % (str(state), state_str))
        log('filtered_instances=%s' % str(filtered_instances))

    print("Stopping %d instances named '%s', state='%s'"
          % (len(filtered_instances), prefix_str, state_str))
    log("Stopping %d instances named '%s*', state='%s'"
        % (len(filtered_instances), prefix_str, state_str))

    # if no filtered instances, do nothing
    if len(filtered_instances) == 0:
        print("No instances found with prefix=%s and state=%s" % (prefix_str, state_str))
        return 0

    # give user a chance to bail
    answer = raw_input('Stopping %d instances.  Proceed? (y/N): '
                       % len(filtered_instances))
    answer = answer.strip().lower()
    if len(answer) == 0 or answer[0] != 'y':
        log.info('User chose not to stop %d instances' % len(filtered_instances))
        return 0

    log.info('User elected to terminate %d instances:\n%s'
             % (len(filtered_instances), str(filtered_instances)))

    # stop all the instances
    swm.terminate(filtered_instances, wait)

    if Verbose > 0:
        print('Stopped %d instances.' % len(filtered_instances))

    return 0
    print(__doc__)        # module docstring used
