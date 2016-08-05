#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This plugin waits for the given state on the specified instances.  The
states we can wait for are:
    . running
    . ssh
    . terminated

Usage: swarm wait <options> <state>

where <options> is zero or more of:
    -h   --help     print this help and stop
    -i   --ip       show instance IP address, not name
    -p   --prefix   name prefix used to select nodes (default is all servers)
    -q   --quiet    be quiet (for scripting)
    -V   --version  print version information and stop
    -v   --verbose  make logging verbose (cumulative)

The return status is non-zero if not all instances achived the required state
before timeout.

An example:
    swarm wait -p test ssh
this waits until all instances with names starting 'test' can accept an
SSH connection.
"""

import os
import sys
import argparse

import swarmcore
import swarmcore.log
import swarmcore.utils as utils
import swarmcore.defaults as defaults


# set up logging
log = swarmcore.log.Log('swarm.log', swarmcore.log.Log.DEBUG)

# program version
MajorRelease = 0
MinorRelease = 1
VersionString = 'v%d.%d' % (MajorRelease, MinorRelease)

Plugin = {
          'entry': 'wait',
          'version': '%s' % VersionString,
          'command': 'wait',
         }

# default values
DefaultAuthDir = os.path.expanduser('~/.ssh')

# legal state strings
LegalStates = [
               'running',    # instance is running
               'ssh',        # instance accepts SSH connection
               'terminated', # instance has terminated
              ]


def usage(msg=None):
    """Print help for the befuddled user."""

    if msg:
        print('*'*60)
        print(msg)
        print('*'*60)
    print(__doc__)        # module docstring used

def wait(args):
    """Wait for the specified state on the given instances.

    args    list of arg values
    """

    # parse the command args
    parser = argparse.ArgumentParser(prog="swarm wait",
                                     description='This plugin waits for a state on the specified instances.')
    parser.add_argument('-i', '--ip', dest='show_ip', action='store_true',
                        help='show public IP instead of instance name',
                        default=False)
    parser.add_argument('-p', '--prefix', dest='prefix', action='store',
                        help='set the prefix for the new instance name',
                        metavar='<prefix>')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true',
                        help='be quiet for scripting', default=False)
    parser.add_argument('-v', '--verbose', dest='verbose', action='count',
                        default=0, help='make logging more verbose (cumulative)')
    parser.add_argument('-V', '--version', action='version',
                        version=VersionString, help='print the version and stop')
    parser.add_argument('state', action='store', help='the state to wait for')

    args = parser.parse_args(args)

    # set variables
    show_ip = args.show_ip
    prefix = args.prefix
    quiet = args.quiet
    state = args.state

    # increase verbosity if required
    verbose = False
    for _ in range(args.verbose):
        log.bump_level()
        verbose = True

    log.debug("wait: show_ip=%s, prefix='%s', state='%s'"
              % (str(show_ip), str(prefix), state))

    if state not in LegalStates:
        states = '\n    '.join(LegalStates)
        msg = ("State '%s' is not recognised, legal states are:\n    %s"
               % (state, states))
        usage(msg)
        return 1

    # get all instances
    swm = swarmcore.Swarm(verbose=verbose)
    all_instances = swm.instances()

    # get a filtered list of instances depending on prefix
    prefixes = []
    filtered_instances = all_instances
    if prefix is not None:
        prefixes = prefix.split(',')
        filtered_instances = []
        for prefix in prefixes:
            filter = swm.filter_name_prefix(prefix)
            s = swm.filter(all_instances, filter)
            filtered_instances = swm.union(filtered_instances, s)

    if not quiet:
        print("Doing 'wait %s' on %d instances named '%s*'"
              % (state, len(filtered_instances), '*|'.join(prefixes)))

    # kick off the wait
    # answer is a tuple (status, data)
    # where data is a list of tuples: (name, ip, state)
    answer = swm.wait(filtered_instances, state)
    log.debug('swm.wait() returned: %s' % str(answer))

    # display results
    (status, data) = answer
    if not quiet:
        if show_ip:
            d_list = [(ip, s) for (name, ip, s) in data]
            d_list.sort()
            log.debug('state=%s, d_list=%s' % (s, str(d_list)))
            for (ip, s) in d_list:
                if state == s:
                    print('%-17s |%s' % (ip, s))
                else:
                    print('%-17s*|%s' % (ip, s))
        else:
            d_list = [(name, s) for (name, ip, s) in data]
            d_list.sort()
            log.debug('state=%s, d_list=%s' % (state, str(d_list)))
            for (name, s) in d_list:
                if state == s:
                    print('%-17s |%s' % (ip, s))
                else:
                    print('%-17s*|%s' % (ip, s))

    return status
