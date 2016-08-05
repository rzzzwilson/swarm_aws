#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This plugin is used to copy a file to many instances.

Usage: swarm copy <options> <src> <dst>

where <options> is zero or more of:
    -a   --auth     directory holding authentication keys (default is ~/.ssh)
    -h   --help     print this help and stop
    -i   --ip       show public IP instead of instance name
    -p   --prefix   name prefix used to select nodes (default is all servers)
    -q   --quiet    be quiet for scripting
    -v   --verbose  make logging more verbose (cumulative)
    -V   --version  print version information and stop
and <src> is the source file, <dst> is the remote destination.  Note
that the <dst> must be valid as an scp destination.

To copy a file to every instance with  prefix of 'test_', do:

    swarm copy -p test_ /tmp/config /var/spool/torque/mom_priv/config
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
          'entry': 'copy',
          'version': '%s' % VersionString,
          'command': 'copy',
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

def ip_key(key):
    """Function to make a 'canonical' IP string for sorting.
    The given IP has each subfield expanded to 3 numeric digits, eg:

        given '1.255.24.6' return '001.255.014.006'
    """

    log.debug('key=%s' % str(key))
    (_, _, ip) = key
    fields = ip.split('.')
    result = []
    for f in fields:
        result.append('%03d' % int(f))

    return result

def copy(args):
    """Perform the copy on required instances.

    args    list of arg values
    """

    # parse the command args
    parser = argparse.ArgumentParser(prog='swarm copy',
                                     description='This plugin is used to copy a file to many instances.')
    parser.add_argument('-a', '--auth', dest='auth_dir', action='store',
                        help='set the directory holding authentication files',
                        metavar='<auth>')
    parser.add_argument('-i', '--ip', dest='show_ip', action='store_true',
                        help='show public IP instead of instance name',
                        default=False)
    parser.add_argument('-p', '--prefix', dest='prefix', action='store',
                        help='set the prefix for the new instance name',
                        metavar='<prefix>')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true',
                        help='be quiet for scripting', default=False)
    parser.add_argument('-s', '--state', dest='state', action='store',
                        help='the state of the instances to be stopped',
                        metavar='<state>', default=defaults.State)
    parser.add_argument('-v', '--verbose', dest='verbose', action='count',
                        default=0, help='make logging more verbose (cumulative)')
    parser.add_argument('-V', '--version', action='version',
                        version=VersionString, help='print the version and stop')
    parser.add_argument('source', action='store', help='the file to be copied')
    parser.add_argument('destination', action='store',
                        help='path to file destination')

    args = parser.parse_args(args)

    # set variables to possibly modified defaults
    auth_dir = args.auth_dir
    show_ip = args.show_ip
    prefix = args.prefix
    quiet = args.quiet
    source = args.source
    destination = args.destination

    # increase verbosity if required
    verbose = False
    for _ in range(args.verbose):
        log.bump_level()
        verbose = True

    # check the auth directory exists
    if auth_dir is None:
        error('Sorry, you must specify the authentication directory')
    if not os.path.isdir(auth_dir):
        error("Authentication directory '%s' doesn't exist"
              % auth_dir)

    log.debug('copy: auth_dir=%s, show_ip=%s, prefix=%s, source=%s, destination=%s'
              % (auth_dir, str(show_ip), str(prefix), source, destination))

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
        print("Doing 'copy' on %d instances named '%s*'"
              % (len(filtered_instances), '*|'.join(prefixes)))

    # kick off the parallel copy
    answer = swm.copy(filtered_instances, source, destination, swm.info_ip())

    # sort by IP
    answer = sorted(answer, key=ip_key)

    # display results
    if not quiet:
        for (output, status, ip) in answer:
            output = output.split('\n')
            canonical_output = ('\n'+' '*17+'|').join(output)
            if status == 0:
                print('%-17s |%s' % (ip, canonical_output))
            else:
                print('%-17s*|%s' % (ip, canonical_output))

    if verbose:
        log.debug('==============================================================')
        log.debug('=========================  FINISHED  =========================')
        log.debug('==============================================================')

    return 0
