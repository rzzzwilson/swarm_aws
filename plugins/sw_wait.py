#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This plugin waits for the given state on the specified instances.  The
states we can wait for are:
    . active
    . ssh
    . terminated

Usage: wait <options> <state>

where <options> is zero or more of:
    -a   --auth     directory holding authentication keys (default is ~/.ssh)
    -h   --help     print this help and stop
    -i   --ip       show source as IP address, not instance name
    -p   --prefix   name prefix used to select nodes (default is all servers)
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)

An example:
    wait -p test ssh
this waits until all instances with names starting 'test' can accept an
SSH connection.
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

Plugin = {
          'entry': 'wait',
          'version': '%d.%d' % (MajorRelease, MinorRelease),
          'command': 'wait',
         }

# default values
DefaultAuthDir = os.path.expanduser('~/.ssh')

# legal state strings
LegalStates = [
               'active',    # instance is running
               'ssh',       # instance accepts SSH connection
               'terminate', # instance has terminated
              ]


def usage(msg=None):
    """Print help for the befuddled user."""

    if msg:
        print('*'*60)
        print(msg)
        print('*'*60)
    print(__doc__)        # module docstring used

def wait(args, kwargs):
    """Wait for the specified state on the given instances.

    args    list of arg values
    kwargs  a dict of default values
    """

    # parse the command params
    try:
        (opts, args) = getopt.getopt(args, 'a:hip:Vv',
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
            pass        # done above

    # get the state required
    if len(args) != 1:
        usage('Only one wait state may be specified.')
        return 1

    state = args[0].lower()
    log.debug("wait: auth_dir=%s, show_ip=%s, name_prefix='%s', state='%s'"
              % (auth_dir, str(show_ip), str(name_prefix), state))

    if state not in LegalStates:
        states = '\n    '.join(LegalStates)
        msg = ("State '%s' is not recognised, legal states are:\n    %s"
               % (state, states))
        usage(msg)
        return 1

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

    print("# doing 'wait %s' on %d instances named '%s*'"
          % (state, len(filtered_instances), '*|'.join(prefixes)))

    # kick off the wait
    answer = swm.wait(filtered_instances, state, swm.info_ip())

    # sort by IP
    answer = sorted(answer, key=ip_key)

    # display results
    for (output, status, ip) in answer:
        output = output.split('\n')
        canonical_output = ('\n'+' '*17+'|').join(output)
        if status == 0:
            print('%-17s |%s' % (ip, canonical_output))
        else:
            print('%-17s*|%s' % (ip, canonical_output))
