"""
This program is used to stop a set of instances.
In AWS-speak, set required instances to the 'terminated' state.

Usage: swarm stop <options>

where <options> is zero or more of:
    -c   --config   set the config from a file
    -h   --help     print this help and stop
    -p   --prefix   name prefix used to select nodes (required)
    -q   --quiet    be quiet for scripting
    -s   --state    state of instances to terminate ('running' is assumed otherwise)
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)
    -w   --wait     wait until instances actually stopped
    -y   --yes      always stop instances, don't prompt user

As an example, the following will stop all instances whose name starts with
'test'.

    swarm stop -p test
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
          'entry': 'stop',
          'version': '%s' % VersionString,
          'command': 'stop',
         }


def usage(msg=None):
    """Print help for the befuddled user."""

    if msg:
        print('*'*60)
        print(msg)
        print('*'*60)
    print(__doc__)        # module docstring used

def stop(args):
    """Stop a set of instances.

    args    list of arg values to be parsed
    """

    # parse the command args
    parser = argparse.ArgumentParser(prog='swarm stop',
                                     description='This program is designed to stop a number of EC2 instances.')
    parser.add_argument('-c', '--config', dest='config', action='store',
                        help='set the config from this file',
                        metavar='<configfile>')
    parser.add_argument('-p', '--prefix', dest='prefix', action='store',
                        help='set the prefix for the new instance name',
                        metavar='<prefix>')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true',
                        help='be quiet for scripting', default=False)
    parser.add_argument('-s', '--state', dest='state', action='store',
                        help='the state of the instances to be stopped',
                        metavar='<state>', default=defaults.State)
    parser.add_argument('-v', '--verbose', dest='verbose', action='count',
                        default=0, help='make execution verbose')
    parser.add_argument('-V', '--version', action='version', version=VersionString,
                        help='print the version and stop')
    parser.add_argument('-w', '--wait', dest='wait', action='store_true',
                        help='wait for the instance to stop', default=False)
    parser.add_argument('-y', '--yes', dest='yes', action='store_true',
                        help="don't prompt before stopping", default=False)

    args = parser.parse_args(args)

    # read config file, if we have one
    # set global values from the config file
    config_values = {}
    if args.config:
        config_values = utils.load_config(args.config)

    # increase verbosity if required
    for _ in range(args.verbose):
        log.bump_level()
        verbose = True

    # set variables to possibly modified defaults
    prefix = config_values.get('args.prefix', args.prefix)
    quiet = args.quiet
    state = config_values.get('state', args.state)
    verbose = args.verbose
    wait = args.wait
    yes = args.yes

    log.debug('sw_stop: prefix=%s' % str(prefix))
    log.debug('sw_stop: state=%s' % str(state))
    log.debug('sw_stop: wait=%s' % str(wait))
    log.debug('sw_stop: yes=%s' % str(yes))

    # check if enough information supplied
    if prefix is None and state is None:
        usage("You must specify instance(s) to stop ('-p' and/or '-s' options).")
        return 1

    # get all instances
    swm = swarmcore.Swarm(verbose=verbose)
    all_instances = swm.instances()
    log('instances=%s' % str(all_instances))

    # get a filtered list of instances depending on prefix, state, etc
    prefix_str = '*'        # assume user wants to stop ALL instances
    filtered_instances = all_instances
    if prefix is not None:
        prefixes = prefix.split(',')
        prefix_str = '*|'.join(prefixes) + '*'
        filtered_instances = []
        for prefix in prefixes:
            f = swm.filter_name_prefix(prefix)
            s = swm.filter(all_instances, f)
            filtered_instances = swm.union(filtered_instances, s)
    log('prefix=%s, prefix_str=%s' % (str(prefix), prefix_str))
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
    log('state=%s, state_str=%s' % (str(state), state_str))
    log('filtered_instances=%s' % str(filtered_instances))

    if not quiet:
        print("Stopping %d instances named '%s', state='%s'"
              % (len(filtered_instances), prefix_str, state_str))
    log("Stopping %d instances named '%s*', state='%s'"
        % (len(filtered_instances), prefix_str, state_str))

    # if no filtered instances, do nothing
    if len(filtered_instances) == 0:
        if not quiet:
            print("No instances found with prefix=%s and state=%s"
                  % (prefix_str, state_str))
        return 0

    # give user a chance to bail
    if yes:
        answer = 'y'
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

    if not quiet:
        print('Stopped %d instances.' % len(filtered_instances))

    log.debug('==============================================================')
    log.debug('=========================  FINISHED  =========================')
    log.debug('==============================================================')

    return 0
