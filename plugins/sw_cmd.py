#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This plugin is a generalization of lots of little scripts that get written
to do something on every worker node, like check the contents of a certain
file, check the hostname, etc.

Usage: swarm cmd <options> <command>

where <options> is zero or more of:
    -a   --auth     directory holding authentication keys (default is ~/.ssh)
    -h   --help     print this help and stop
    -i   --ip       show source as IP address, not VM name
    -p   --prefix   name prefix used to select nodes (default is all instances)
    -q   --quiet    be quiet for scripting
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)
and <command> is the command string to execute on the node.

An example:

    swarm cmd -vv "ls -la /tmp"
"""

import os
import sys
import getopt
import swarmcore
from swarmcore import log
log = log.Log('swarm.log', log.Log.DEBUG)


# program version
MajorRelease = 0
MinorRelease = 1

# plugin info
Plugin = {
          'entry': 'command',
          'version': 'v%d.%d' % (MajorRelease, MinorRelease),
          'command': 'cmd',
         }

# default values
DefaultAuthDir = os.path.expanduser('~/.ssh')


def error(msg):
    """Print error message and quit."""

    usage(msg)
    sys.exit(1)

def usage(msg=None):
    """Print help for the befuddled user."""

    if msg:
        print('*'*60)
        print(msg)
        print('*'*60)
    print(__doc__)        # module docstring used

def command(args, kwargs):
    """Perform the command on required instances..

    args    list of arg values
    kwargs  a dict of default values
    """

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

    # parse the command params
    try:
        (opts, args) = getopt.getopt(args, 'a:hip:qVv',
                                     ['auth=', 'help', 'ip', 'prefix=',
                                      'quiet', 'version', 'verbose'])
    except getopt.error, msg:
        usage()
        return 1

    verbose = False
    for (opt, param) in opts:
        if opt in ['-v', '--verbose']:
            log.bump_level()
            verbose = True

    # now parse the options
    auth_dir = DefaultAuthDir
    show_ip = False
    name_prefix = None
    quiet = False
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
        elif opt in ['-q', '--quiet']:
            quiet = True
        elif opt in ['-V', '--version']:
            print('%s %s' % (__program__, __version__))
            return 0
        elif opt in ['-v', '--verbose']:
            pass        # done above

    if len(args) < 1:
        usage()
        return 1

    cmd = ' '.join(args)

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

    if not quiet:
        print("Doing '%s' on %d instances named '%s*'"
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
    if not quiet:
        for (result, name) in answer:
            (status, output) = result
            output = output.split('\n')
            canonical_output = ('\n'+' '*17+' |').join(output)
            if status == 0:
                print('%-17s |%s' % (name, canonical_output))
            else:
                print('%-17s*|%s' % (name, canonical_output))

    if verbose:
        log.debug('==============================================================')
        log.debug('=========================  FINISHED  =========================')
        log.debug('==============================================================')

    return 0
