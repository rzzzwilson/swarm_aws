#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This plugin is a generalization of lots of little scripts that get written
to do something on every worker node, like check the contents of a certain
file, check the hostname, etc.

Usage: swarm_aws cmd <options> <command>

where <options> is zero or more of:
    -a   --auth     directory holding authentication keys (default is ~/.ssh)
    -h   --help     print this help and stop
    -i   --ip       show source as IP address, not VM name
    -p   --prefix   name prefix used to select nodes (default is all instances)
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)
and <command> is the command string to execute on the node.

An example:
swarm_aws cmd "cat /var/spool/torque/mom_priv/config|grep \\"^\\\\\$usecp\\" | grep users"
"""

import os
import swarmcore
from swarmcore import log
log = log.Log('sw_cmd.log', log.Log.DEBUG)


# program version
MajorRelease = 0
MinorRelease = 1


# default values
DefaultAuthDir = os.path.expanduser('~/.ssh')


def plugin(auth_dir=DefaultAuthDir, name_prefix=None, show_ip=False, *args):
    """Perform the command remotely.

    auth_dir     path to directory of authentication keys
    name_prefix  prefix of node name
    show_ip      if True show instance IP, else show EC2 name
    cmd          the command to execute remotely
    """

    print('plugin: *args=%s' % str(args))

    def ip_key(key):
        """Function to make a 'canonical' IP string for sorting.
        The given IP has each subfield expanded to 3 numeric digits, eg:
            given '1.255.24.6' return '001.255.014.006'

        The 'key' has the form ((status, output), ip).
        """

        ip = key[1]
        fields = ip.split('.')
        result = []
        for f in fields:
            result.append('%03d' % int(f))

        return result

    def name_key(key):
        """Function to sort data by name (field 1)."""

        return key[1]

    # get all instances
    swm = swarmcore.Swarm()
    all_instances = swm.instances()

    # get a filtered list of instances depending on name_prefix
    prefixes = []
    filtered_instances = all_instances
    if name_prefix is not None:
        prefixes = name_prefix.split(',')
        filtered_instances = []
        for prefix in prefixes:
            filter = swm.filter_name_prefix(prefix)
            s = swm.filter(all_instances, filter)
            filtered_instances = swm.union(filtered_instances, s)

    print("# doing '%s' on %d instances named '%s*'"
          % (cmd, len(filtered_instances), '*|'.join(prefixes)))

    # kick off the parallel cmd
    answer = swm.cmd(filtered_instances, cmd, swm.info_ip())

    # handle the case where user wants IP displayed
    if show_ip:
        answer = sorted(answer, key=ip_key)
    else:
        # get openstack names, make new answer
        ip_names = swm.info(filtered_instances, swm.info_ip(), swm.info_name())
        new_answer = []
        for (os_ip, os_name) in ip_names:
            name = os_ip		# if no match
            for (result, ans_ip) in answer:
                if ans_ip == os_ip:
                    name = os_name
                    break
            new_answer.append((result, os_name))
        answer = sorted(new_answer, key=name_key)

    # display results
    for (result, name) in answer:
        (status, output) = result
        output = output.split('\n')
        canonical_output = ('\n'+' '*17+' |').join(output)
        if status == 0:
            print('%-17s |%s' % (name, canonical_output))
        else:
            print('%-17s*|%s' % (name, canonical_output))

Plugin = {
          'entry': 'plugin',
          'version': '%d.%d' % (MajorRelease, MinorRelease),
          'command': 'cmd',
         }


if __name__ == '__main__':
    import sys
    import getopt
    import traceback

    def error(msg):
        """Print error message and quit."""

        print(msg)
        sys.exit(1)


    def warn(msg):
        """Print error message and continue."""

        log.warn(msg)
        print(msg)


    def usage(msg=None):
        """Print help for the befuddled user."""

        if msg:
            print(msg+'\n')
        print(__doc__)        # module docstring used


    def main(argv=None):
        if argv is None:
            argv = sys.argv[1:]

        try:
            opts, args = getopt.getopt(argv, 'a:hip:Vv',
                                       ['auth=', 'help', 'ip', 'prefix=',
                                        'version', 'verbose'])
        except getopt.error, msg:
            usage()
            return 1
        for (opt, param) in opts:
            if opt in ['-v', '--verbose']:
                log.bump_level()

        # now parse the options
        auth_dir = DefaultAuthDir
        show_ip = False
        name_prefix = None
        for (opt, param) in opts:
            if opt in ['-a', '--auth']:
                auth_dir = param
                if not os.path.isdir(auth_dir):
                    error("Authentication directory '%s' doesn't exist"
                          % auth_dir)
            elif opt in ['-h', '--help']:
                usage()
                return 0
            elif opt in ['-i', '--ip']:
                show_ip = True
            elif opt in ['-p', '--prefix']:
                name_prefix = param
            elif opt in ['-V', '--version']:
                print('%s %s' % (__program__, __version__))
                return 0
            elif opt in ['-v', '--verbose']:
                pass
#                log.bump_level()

        if len(args) < 1:
            usage()
            return 1
        cmd = ' '.join(args)

        # do the command
        plugin(cmd, auth_dir, name_prefix, show_ip)

        return 0

    # our own handler for uncaught exceptions
    def excepthook(type, value, tb):
        msg = '\n' + '=' * 80
        msg += '\nUncaught exception:\n'
        msg += ''.join(traceback.format_exception(type, value, tb))
        msg += '=' * 80 + '\n'

        print msg
        log.critical(msg)
        sys.exit(1)

    # plug our handler into the python system
    sys.excepthook = excepthook

    sys.exit(main(sys.argv[1:]))
