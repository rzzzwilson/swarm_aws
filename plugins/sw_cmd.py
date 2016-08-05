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
    -v   --verbose  be verbose
and <command> is the command string to execute on the node.

An example:

    swarm cmd -v -p "test" "ls -la /tmp"
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

# plugin info
Plugin = {
          'entry': 'command',
          'version': VersionString,
          'command': 'cmd',
         }

# this function can't be in utils.py as we need access to __doc__
def usage(msg=None):
    """Print help for the befuddled user."""

    if msg:
        print('*'*60)
        print(msg)
        print('*'*60)
    print(__doc__)        # module docstring used

def command(args):
    """Perform the command on required instances..

    args    list of arg values
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

    # parse the command args
    parser = argparse.ArgumentParser(prog='swarm cmd',
                                     description='This program runs a command on the specified EC2 instances.')
    parser.add_argument('-a', '--auth', dest='auth', action='store',
                        help='set the path to the authentication directory',
                        metavar='<auth>', default=defaults.AuthPath)
    parser.add_argument('-c', '--config', dest='config', action='store',
                        help='set the config from this file',
                        metavar='<configfile>')
    parser.add_argument('-i', '--ip', dest='show_ip', action='store_true',
                        help='display the instance IP in the results',
                        default=False)
    parser.add_argument('-k', '--key', dest='key', action='store',
                        help='set the key file to use',
                        metavar='<key>', default=defaults.Key)
    parser.add_argument('-p', '--prefix', dest='prefix', action='store',
                        help='set the prefix for the new instance name',
                        metavar='<prefix>')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true',
                        help='be quiet for scripting', default=False)
    parser.add_argument('-r', '--region', dest='region', action='store',
                        help='set the region to use',
                        metavar='<region>', default=defaults.Region)
    parser.add_argument('-s', '--secgroup', dest='secgroup', action='store',
                        help='set the security group to use',
                        metavar='<secgroup>', default=defaults.Secgroup)
    parser.add_argument('-v', '--verbose', dest='verbose', action='count',
                        default=0, help='make execution more verbose (cumulative)')
    parser.add_argument('-V', '--version', action='version', version=VersionString,
                        help='print the version and stop')
    parser.add_argument('-z', '--zone', dest='zone', action='store',
                        help='set the zone to use',
                        metavar='<zone>', default=defaults.Zone)
    parser.add_argument('command', metavar='<command>', action='store',
                        type=str, help='the command to run on each instance')
    args = parser.parse_args(args)

    # read config file, if we have one
    # set global values from the config file
    config_values = {}
    if args.config:
        config_values = utils.load_config(args.config)

    # increase verbosity if required
    verbose = False
    for _ in range(args.verbose):
        log.bump_level()
        verbose = True

    # set variables to possibly modified defaults
    auth = config_values.get('auth', args.auth)
    key = config_values.get('args.key', args.key)
    prefix = config_values.get('args.prefix', args.prefix)
    quiet = args.quiet
    region = config_values.get('region', args.region)
    secgroup = config_values.get('secgroup', args.secgroup)
    show_ip = config_values.get('show_ip', args.show_ip)
    zone = config_values.get('zone', args.zone)

    # gather all parameters and make a command string
    cmd = args.command

    # get all instances
    swm = swarmcore.Swarm(verbose=verbose)
    all_instances = swm.instances()

    # get a filtered list of instances depending on prefix
    prefixes = []
    filtered_instances = all_instances
    if prefix is not None:
        prefixes = prefix.split(',')
        filtered_instances = []
        for p in prefixes:
            filter = swm.filter_name_prefix(p)
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
#    if not quiet:
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
