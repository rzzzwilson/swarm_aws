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
#import getopt
import argparse
import commands
import tempfile
import traceback

import swarmcore
from swarmcore import log
import swarmcore.utils as utils

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

# default instance  values
DefaultAuthPath = os.path.expanduser('~/.ssh')
DefaultRegion = 'ap-southeast-2'
DefaultZone = 'ap-southeast-2a'
DefaultFlavour = 't2.micro'
DefaultImage = None
DefaultKey = 'ec2_sydney'
DefaultNamePrefix = 'instance{number}'
DefaultSecgroup = 'sydney'
DefaultUserdata = None

# dictionary to map config names to global names
# the key is the name as it appears in the config file
# the value is the name of the global variable that should be changed
Config2Global = {'image': 'DefaultImage',
                 'region': 'DefaultRegion',
                 'flavor': 'DefaultFlavour',
                 'flavour': 'DefaultFlavour',
                 'zone': 'DefaultZone',
                 'key': 'DefaultKey',
                 'keypair': 'DefaultKey',
                 'nameprefix': 'DefaultNamePrefix',
                 'prefix': 'DefaultNamePrefix',
                 'name': 'DefaultNamePrefix',
                 'secgroup': 'DefaultSecgroup',
                 'security': 'DefaultSecgroup',
                 'securitygroup': 'DefaultSecgroup',
                 'prefix': 'DefaultNamePrefix',
                 'userdata': 'DefaultUserdata',
                 'auth': 'DefaultAuthPath',
                 'authdir': 'DefaultAuthPath',
                 'authpath': 'DefaultAuthPath',
                }

# flag for print verbosity
Verbose = False


def usage(msg=None):
    """Print help for the befuddled user."""

    if msg:
        print('*'*60)
        print(msg)
        print('*'*60)
    print(__doc__)        # module docstring used

def load_config(config_file):
    """Set global defaults from the config file."""

    # see if config file exists
    if not os.path.isfile(config_file):
        utils.error("Can't find config file '%s'" % config_file)

    if Verbose:
        log.debug("load_config: loading config from '%s'" % str(config_file))

    # read config, look for known variable definitions
    with open(config_file, 'rb') as fd:
        lines = fd.readlines()

    # construct dictionary of globals to update
    updated_globals = {}
    errors = False

    for (l, orig_line) in enumerate(lines):
        line = orig_line.strip()
        if line == '' or line[0] == '#':
            continue

        # expect lines of the form 'name = value'
        fields = line.split('=')
        if len(fields) != 2:
            utils.error("Line %d of '%s' has bad format: %s"
                        % (l+1, config_file, orig_line))
        (name, value) = fields

        name = name.strip().lower()
        value = value.strip()

        if name not in Config2Global:
            utils.warn("Line %d of %s: name '%s' is unrecognized"
                       % (l+1, config_file, name))
            errors = True
            continue

        global_name = Config2Global[name]
        if global_name in updated_globals:
            utils.error("Line %d of %s: '%s' defined twice"
                        % (l+1, config_file, name))
            errors = True
        else:
            # add global+new value to dict - eval() removes any quotes
            updated_globals[global_name] = eval(value)

    if errors:
        sys.exit(1)

    # update globals with values from the config file
    globals().update(updated_globals)

    if Verbose:
        log.debug('load_config: New globals:')
        for (key, value) in updated_globals.items():
            log.debug('    %s: %s,' % (str(key), str(value)))

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

    global Verbose

    # parse the command args
    parser = argparse.ArgumentParser(description='This program is designed to start a number of new EC2 instances.')
    parser.add_argument('-a', '--auth', dest='auth', action='store',
                        help='set the path to the authentication directory',
                                metavar='<auth>')
    parser.add_argument('-c', '--config', dest='config', action='store',
                        help='set the config from this file',
                        metavar='<configfile>')
    parser.add_argument('-f', '--flavour', dest='flavour', action='store',
                        help='set the new instance flavour',
                        metavar='<configfile>')
    parser.add_argument('-i', '--image', dest='image', action='store',
                        help='set the image for the new instance',
                        metavar='<image>')
    parser.add_argument('-k', '--key', dest='key', action='store',
                        help='set the key file for the new instance',
                        metavar='<key>')
    parser.add_argument('-p', '--prefix', dest='prefix', action='append',
                        help='set the prefix for the new instance name',
                        metavar='<prefix>')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true',
                        help='be quiet for scripting',
                        default=False)
    parser.add_argument('-r', '--region', dest='region', action='store',
                        help='set the region for the new instance name',
                        metavar='<region>')
    parser.add_argument('-s', '--secgroup', dest='secgroup', action='store',
                        help='set the security group for the new instance',
                        metavar='<secgroup>')
    parser.add_argument('-u', '--userdata', dest='userdata', action='store',
                        help='set the userdata file for the new instance',
                        metavar='<userdata>')
    parser.add_argument('-v', '--verbose', action='count',
                        help='make execution mot verbose', default=0)
    parser.add_argument('-V', '--version', action='version', version=VersionString,
                        help='print the version and stop')
    parser.add_argument('-z', '--zone', dest='zone', action='store',
                        help='set the zone for the new instance',
                        metavar='<zone>')
    parser.add_argument('number', metavar='N', action='store',
                        type=int, help='the number of instances to start')

    args = parser.parse_args()

    # read config file, if we have one
    # this may update the variables just set from defaults
    if args.config:
        load_config(args.config)

    # set variables to possibly modified defaults
    auth = args.auth
    flavour = args.flavour
    image = args.image
    key = args.key
    prefix = args.prefix
    quiet = args.quiet
    region = args.region
    zone = args.zone
    secgroup = args.secgroup
    userdata = args.userdata

    if args.number < 0:
        usage('Instance number must be a non-negative integer')
        sys.exit(1)

    # look at prefix - if it doesn't contain '{number' add it
    prefix_name = prefix
    if '{number' not in prefix:
        if num != 1:
            usage("Instance prefix must contain '{number...}' if number of instances > 1")
            sys.exit(1)

    if Verbose:
        log.debug('sw_start: prefix=%s' % prefix)
        log.debug('sw_start: num=%d' % num)
        log.debug('sw_start: prefix_name=%s' % prefix_name)

    # prepare security group info
    secgroup = secgroup.split(',')

    if not quiet:
        print('Starting %d worker nodes, prefix=%s' % (num, prefix_name))

    # connect to AWS
    s = swarmcore.Swarm(auth_dir=auth, verbose=Verbose)

    # get the userdata as a string
    userdata_str = None
    if userdata is not None:
        with open(userdata, 'rb') as fd:
            userdata_str = fd.read()
        if Verbose:
            log.debug('userdata:\n%s' % userdata_str)

    # start instance nodes, wait until running
    log.debug('prefix=%s' % str(prefix))
    new = s.start(num, prefix, image=image, region=region, zone=zone,
                  flavour=flavour, key=key, secgroup=secgroup,
                  userdata=userdata_str)
    if not quiet:
        print('%d new instances running' % len(new))

    if Verbose:
        log.debug('sw_start: num=%d' % num)
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

    if Verbose:
        log.debug('==============================================================')
        log.debug('=========================  FINISHED  =========================')
        log.debug('==============================================================')

    return 0
