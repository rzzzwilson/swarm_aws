#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This program is used to stop a set of instances.

Usage: sw_stop <options>

where <options> is zero or more of:
    -h   --help     print this help and stop
    -p   --prefix   name prefix used to select nodes (required)
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)
    -w   --wait     wait until instances actually stopped

As an example, the following will stop all instances whose name start 'cxwn' and
will wait until the servers are actually gone:
    sw_stop -p test -w
"""

import os
import getopt
import swarmcore
from swarmcore import log
log = log.Log('swarm.log', log.Log.DEBUG)


# program version
MajorRelease = 0
MinorRelease = 1

Plugin = {
          'entry': 'stop',
          'version': '%d.%d' % (MajorRelease, MinorRelease),
          'command': 'stop',
         }


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
        userdata  instance startup script path
        auth      path to auth directory
    """

    global Verbose

    # parse the command args
    try:
        (opts, args) = getopt.getopt(args, 'hp:Vviw',
                                     ['help', 'prefix=',
                                      'version', 'verbose', 'wait'])
    except getopt.error, msg:
        usage()
        return 1

    Verbose = 0
    for (opt, param) in opts:
        if opt in ['-v', '--verbose']:
            Verbose = True
            log.bump_level()

    # now parse the options
    name_prefix = None
    wait = False
    for (opt, param) in opts:
        if opt in ['-h', '--help']:
            usage()
            return 0
        elif opt in ['-p', '--prefix']:
            name_prefix = param
        elif opt in ['-V', '--version']:
            print('%s v%s' % (Plugin['command'], Plugin['version']))
            return 0
        elif opt in ['-v', '--verbose']:
            pass        # done above
        elif opt in ['-w', '--wait']:
            wait = True

    if len(args) != 0:
        usage()
        return 1

    if name_prefix is None:
        error('You must specify a instance name prefix.')

    # get all servers
    swm = swarmcore.Swarm(verbose=Verbose)
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

    print("Stopping %d instances named '%s*'"
          % (len(filtered_instances), '*|'.join(prefixes)))
    log("Stopping %d instances named '%s*'"
        % (len(filtered_instances), '*|'.join(prefixes)))

    # if no filtered instances, do nothing
    if len(filtered_instances) == 0:
        print("No instances found with prefix: '%s*'" % '*|'.join(prefixes))
        return

    # give user a chance to bail
    answer = raw_input('Stopping %d instances.  Proceed? (y/N): '
                       % len(filtered_instances))
    answer = answer.strip().lower()
    if len(answer) == 0 or answer[0] != 'y':
        return

    log.info('User elected to terminate %d instances:\n%s'
             % (len(filtered_instances), str(filtered_instances)))

    # stop all the instances
    swm.terminate(filtered_instances, wait)

    if Verbose > 0:
        print('Stopped %d instances.' % len(filtered_instances))

    return 0

