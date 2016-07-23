#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This program is designed to start a number of new EC2 instances.

Usage: swarm start <options> <number>

where <options> is zero or more of:
    -a  <auth>      set path to key directory (default ~/.ssh)
    -c  <config>    set the config file to use
    -f  <flavour>   set the image flavour
    -h              print this help and stop
    -i  <image>     sets image to use
    -k  <keyname>   set key to use
    -p  <prefix>    set the name prefix
    -q              be quiet, for scripting
    -r  <region>    set the instance region
    -s  <secgroup>  set the security group(s) (can be: 'xyzzy,default')
    -u  <userdata>  path to a userdata script file
    -v              verbose debug logging
    -V              print version and stop
    -z  <zone>      set the availability zone to use
and <number> is the number of additional instances to start.
This program only adds new Instances.

The config file overrides any built-in defaults, and the options
can override any config file values.
"""

import os
import sys
import shutil
import time
import argparse
import commands
import tempfile
import traceback

import swarmcore
from swarmcore import log
import swarmcore.utils as utils
import swarmcore.defaults as defaults

log = log.Log('swarm.log', log.Log.DEBUG)


# program version
MajorRelease = 0
MinorRelease = 1
VersionString = 'v%d.%d' % (MajorRelease, MinorRelease)

Plugin = {
          'entry': 'start',
          'version': VersionString,
          'command': 'start',
         }

# this function can't be in utils.py as we need access to __doc__
def usage(msg=None):
    """Print help for the befuddled user."""

    if msg:
        print('*'*60)
        print(msg)
        print('*'*60)
    print(__doc__)        # module docstring used

def start(args, kwargs):
    """Start a number of new cloud Instances.

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

    # parse the command args
    parser = argparse.ArgumentParser(description='This program is designed to start a number of new EC2 instances.')
    parser.add_argument('-a', '--auth', dest='auth', action='store',
                        help='set the path to the authentication directory',
                        metavar='<auth>', default=defaults.AuthPath)
    parser.add_argument('-c', '--config', dest='config', action='store',
                        help='set the config from this file',
                        metavar='<configfile>')
    parser.add_argument('-f', '--flavour', dest='flavour', action='store',
                        help='set the new instance flavour',
                        metavar='<flavour>', default=defaults.Flavour)
    parser.add_argument('-i', '--image', dest='image', action='store',
                        help='set the image for the new instance',
                        metavar='<image>', default=defaults.Image)
    parser.add_argument('-k', '--key', dest='key', action='store',
                        help='set the key file for the new instance',
                        metavar='<key>', default=defaults.Key)
    parser.add_argument('-p', '--prefix', dest='prefix', action='store',
                        help='set the prefix for the new instance name',
                        metavar='<prefix>')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true',
                        help='be quiet for scripting', default=False)
    parser.add_argument('-r', '--region', dest='region', action='store',
                        help='set the region for the new instance name',
                        metavar='<region>', default=defaults.Region)
    parser.add_argument('-s', '--secgroup', dest='secgroup', action='store',
                        help='set the security group for the new instance',
                        metavar='<secgroup>', default=defaults.Secgroup)
    parser.add_argument('-u', '--userdata', dest='userdata', action='store',
                        help='set the userdata file for the new instance',
                        metavar='<userdata>')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                        help='make execution verbose', default=False)
    parser.add_argument('-V', '--version', action='version', version=VersionString,
                        help='print the version and stop')
    parser.add_argument('-z', '--zone', dest='zone', action='store',
                        help='set the zone for the new instance',
                        metavar='<zone>', default=defaults.Zone)
    parser.add_argument('number', metavar='N', action='store',
                        type=int, help='the number of instances to start')

    args = parser.parse_args()

    # read config file, if we have one
    # set global values from the config file
    config_values = {}
    if args.config:
        config_values = utils.load_config(args.config)

    # set variables to possibly modified defaults
    auth = config_values.get('auth', None)
    flavour = config_values.get('flavour', args.flavour)
    image = config_values.get('image', args.image)
    key = config_values.get('args.key', args.key)
    prefix = config_values.get('args.prefix', args.prefix)
    quiet = args.quiet
    region = config_values.get('region', args.region)
    secgroup = config_values.get('secgroup', args.secgroup)
    userdata = config_values.get('userdata', args.userdata)
    verbose = args.verbose
    zone = config_values.get('zone', args.zone)
    number = args.number

    if number < 0:
        usage('Instance number must be a non-negative integer')
        sys.exit(1)

    # look at prefix - if it doesn't contain '{number' add it
    prefix_name = prefix
    if '{number' not in prefix and number != 1:
        usage("Instance prefix must contain '{number...}' if number of instances > 1")
        sys.exit(1)

    if verbose:
        log.debug('sw_start: prefix=%s' % prefix)
        log.debug('sw_start: number=%d' % number)
        log.debug('sw_start: prefix_name=%s' % prefix_name)

    # prepare security group info
    secgroup = secgroup.split(',')

    if not quiet:
        print('Starting %d worker nodes, prefix=%s' % (number, prefix_name))

    # connect to AWS
    s = swarmcore.Swarm(auth_dir=auth, verbose=verbose)

    # get the userdata as a string
    userdata_str = None
    if userdata is not None:
        with open(userdata, 'rb') as fd:
            userdata_str = fd.read()
        if verbose:
            log.debug('userdata:\n%s' % userdata_str)

    # start instance nodes, wait until running
    log.debug('prefix=%s' % str(prefix))
    new = s.start(number, prefix, image=image, region=region, zone=zone,
                  flavour=flavour, key=key, secgroup=secgroup,
                  userdata=userdata_str)
    if not quiet:
        print('%d new instances running' % len(new))

    if verbose:
        log.debug('sw_start: number=%d' % number)
        log.debug('sw_start: prefix=%s' % prefix)
        log.debug('sw_start: image=%s' % image)
        log.debug('sw_start: flavour=%s' % flavour)
        log.debug('sw_start: key=%s' % key)
        log.debug('sw_start: region=%s' % region)
        log.debug('sw_start: zone=%s' % zone)
        log.debug('sw_start: secgroup=%s' % str(secgroup))
        log.debug('sw_start: userdata=%s' % str(userdata))
        log.debug('sw_start: userdata_str=\n%s' % str(userdata_str))
        log.debug('sw_start: auth=%s' % auth)

    if verbose:
        log.debug('==============================================================')
        log.debug('=========================  FINISHED  =========================')
        log.debug('==============================================================')

    return 0
