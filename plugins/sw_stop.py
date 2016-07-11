#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This program is used to stop a set of instances.
In AWS-speak, set required instances to the 'terminated' state.

Usage: swarm stop <options>

where <options> is zero or more of:
    -h   --help     print this help and stop
    -p   --prefix   name prefix used to select nodes (required)
    -s   --state    state of instances to terminate ('running' is assumed otherwise)
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)
    -w   --wait     wait until instances actually stopped
    -y   --yes      always stop instances, don't prompt user

As an example, the following will stop all instances whose name start 'cxwn' and
will wait until the instances are actually gone:
    swarm stop -p test -w
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
          'entry': 'stop',
          'version': '%d.%d' % (MajorRelease, MinorRelease),
          'command': 'stop',
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
        (opts, args) = getopt.getopt(args, 'hp:s:Vviwy',
                                     ['help', 'prefix=', 'state=',
                                      'version', 'verbose', 'wait', 'yes'])
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
    y_opt = False
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
        elif opt in ['-y', '--yes']:
            y_opt = True

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
        print('instances=%s' % str(all_instances))
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
    if y_opt:
        answer = 'n'
    else:
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
