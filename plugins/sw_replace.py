#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This program is designed to replace an ailing instance or instances, gathering
as much required information from the sick instance as possible.

Usage: swarm replace <options> [<name> [, <name> ...]]

where <options> is zero or more of:
    -a  <auth>      set path to key directory (default ~/.ssh)
    -c  <config>    set the config file to use
    -f  <flavour>   set the image flavour
    -h              print this help and stop
    -i  <image>     sets image to use
    -k  <keyname>   set key to use
    -p  <prefix>    set the name prefix
    -q              be quiet for scripting
    -r  <region>    set the region to use
    -s  <secgroup>  set the security group(s) (can be: 'xyzzy,default')
    -u  <userdata>  path to a userdata script file
    -v              become verbose (cumulative)
    -V              print version and stop
    -y              answer 'y' to replace? question
and <name> is the sick instance AWS dashboard name.

Zero or more <name> values may be specified.  If both the '-p' option and one or
more <name>s are given the given <prefix> selects suitable instances and the
instances in that selection with the given <name>s are replaced.

The command line options override information from the running instance(s).
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
          'entry': 'replace',
          'version': '%s' % VersionString,
          'command': 'replace',
         }

# delay while polling status of dying instance
WaitForDyingServer = 5

# default instance values
DefaultAuthPath = os.path.expanduser('~/.ssh')
DefaultRegion = 'ap-southeast-2'
DefaultZone = 'ap-southeast-2b'
DefaultFlavour = 't2.micro'
DefaultImage = None
DefaultKey = 'ec2_sydney'
DefaultNamePrefix = None
DefaultSecgroup = 'sydney'
DefaultUserdata = None

# dictionary to map config names to global names
# the key is the name as it appears in the config file
# the value is the name of the global variable that should be changed
Config2Global = {'image': 'DefaultImage',
                 'flavor': 'DefaultFlavour',
                 'flavour': 'DefaultFlavour',
                 'key': 'DefaultKey',
                 'keypair': 'DefaultKey',
                 'nameprefix': 'DefaultNamePrefix',
                 'prefix': 'DefaultNamePrefix',
                 'name': 'DefaultNamePrefix',
                 'region': 'DefaultRegion',
                 'secgroup': 'DefaultSecgroup',
                 'security': 'DefaultSecgroup',
                 'securitygroup': 'DefaultSecgroup',
                 'prefix': 'DefaultNamePrefix',
                 'userdata': 'DefaultUserdata',
                 'auth': 'DefaultAuthPath',
                 'authdir': 'DefaultAuthPath',
                 'authpath': 'DefaultAuthPath',
                }


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
        error("Can't find config file %s" % config_file)

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
            error('Line %d of %s has bad format: %s'
                  % (l+1, config_file, orig_line))
        (name, value) = fields

        name = name.strip().lower()
        value = value.strip()

        if name not in Config2Global:
            log.warn("Line %d of %s: name '%s' is unrecognized"
                     % (l+1, config_file, name))
            errors = True
            continue

        global_name = Config2Global[name]
        if global_name in updated_globals:
            error("Line %d of %s: '%s' defined twice"
                  % (l+1, config_file, name))
            errors = True
        else:
            # add global+new value to dict - eval() removes any quotes
            updated_globals[global_name] = eval(value)

    if errors:
        sys.exit(1)

    # update globals with values from the config file
    log.debug('load_config: New globals:')
    for (key, value) in updated_globals.items():
        log.debug('    %s: %s,' % (str(key), str(value)))

    globals().update(updated_globals)

def replace(args, kwargs):
    """Replace an existing cloud instance.

    args    list of arg values to be parsed
    kwargs  a dict of default values

    Values potentially parsed from 'args' or found in 'kwargs':
        image     image for instance
        flavour   flavour of instance
        key       key for instance
        secgroup  security group(s)
        userdata  instance startup script path
        auth      path to auth directory
    """

#    -a  <auth>      set path to key directory (default ~/.ssh)
#    -c  <config>    set the config file to use
#    -f  <flavour>   set the image flavour
#    -h              print this help and stop
#    -i  <image>     sets image to use
#    -k  <keyname>   set key to use
#    -p  <prefix>    set the name prefix
#    -q              be quiet for scripting
#    -s  <secgroup>  set the security group(s) (can be: 'xyzzy,default')
#    -u  <userdata>  path to a userdata script file
#    -v              become verbose (cumulative)
#    -V              print version and stop
#    -y              answer 'y' to replace? question
#and <name> is the sick instance AWS dashboard name.

    # parse the command args
    parser = argparse.ArgumentParser(prog='swarm replace',
                                     description='This program is designed to start a number of new EC2 instances.')
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
    parser.add_argument('-v', '--verbose', dest='verbose', action='count',
                        default=0, help='make logging more verbose')
    parser.add_argument('-V', '--version', action='version', version=VersionString,
                        help='print the version and stop')
    parser.add_argument('-z', '--zone', dest='zone', action='store',
                        help='set the zone for the new instance',
                        metavar='<zone>', default=defaults.Zone)
    parser.add_argument('instances', action='store', nargs='*',
                        help='optional instance names to replace')

    args = parser.parse_args()

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
    auth = config_values.get('auth', None)
    flavour = config_values.get('flavour', args.flavour)
    image = config_values.get('image', args.image)
    key = config_values.get('args.key', args.key)
    prefix = config_values.get('args.prefix', args.prefix)
    quiet = args.quiet
    region = config_values.get('region', args.region)
    secgroup = config_values.get('secgroup', args.secgroup)
    userdata = config_values.get('userdata', args.userdata)
    zone = config_values.get('zone', args.zone)
    instances = args.instances

    log.debug('auth=%s' % str(auth))
    log.debug('flavour=%s' % str(flavour))
    log.debug('image=%s' % str(image))
    log.debug('key=%s' % str(key))
    log.debug('prefix=%s' % str(prefix))
    log.debug('region=%s' % str(region))
    log.debug('secgroup=%s' % str(secgroup))
    log.debug('userdata=%s' % str(userdata))
    log.debug('zone=%s' % str(zone))
    log.debug('instances=%s' % str(instances))

    # connect to AWS
    s = swarmcore.Swarm(auth_dir=auth, verbose=verbose)
    all_instances = s.instances()

    # get list of instances satisfying 'prefix' option
    replace_instances = all_instances   # assume we want all instances
    if prefix:
        # otherwise look for name prefix
        replace_instances = []
        for instance in all_instances:
            instance_name = utils.get_instance_name(instance)
            if instance_name.startswith(prefix):
                replace_instances.append(instance)
    log.debug('Replacing instance(s) %s' % str(replace_instances))
    if not quiet:
        print('Replacing instance(s) %s' % str(replace_instances))

    # now check if given instance names and find these in 'replace_instances'
    if instances:
        named_instances = []
        for instance in replace_instances:
            if utils.get_instance_name(instance) in instances:
                named_instances.append(instance)
        replace_instances = named_instances

    # check we have something to do
    if not replace_instances:
        if prefix and instances:
            msg = ("Sorry, didn't find any instances of '%s*' with names '%s'"
                   % (name, str(instances)))
        elif prefix:
            msg = ("Sorry, didn't find any instances of '%s*'" % name)
        elif instances:
            msg = ("Sorry, didn't find any instances with names in '%s'"
                   % str(instances))
        else:
            msg = "You must specify either the '-p' option or one or more names or both"
        log(msg)
        print(msg)
        sys.exit(10)

    # gather what info we can from the running instances
    data = s.describe_instances(replace_instances)

    # debug
    log('data=%s' % str(data))

    # replace instance info with data from parameters, this should be infrequent
    for info in data:
#        if auth:
#            info['auth'] = auth
        if flavour:
            info['instance_type'] = flavour
        if image:
            info['image_id'] = image
        if key:
            info['key_name'] = key
        if region:
            info['availability_zone'] = region
        if secgroup:
            info['security_groups'] = secgroup.split(',')
            print("secgroup.split(',')=%s" % str(secgroup.split(',')))
#        if userdata:
#            info['userdata'] = userdata

    log.debug('After replace, data=%s' % str(data))

    # stop the current instances, wait until really gone
    log.debug('Stopping %d instances %s'
              % (len(replace_instances), ', '.join([x['name'] for x in data])))
    if not quiet:
        print('Stopping %d instances %s'
              % (len(replace_instances), ', '.join([x['name'] for x in data])))

    s.terminate(replace_instances, wait=True)

    log('%d instances stopped' % len(replace_instances))

    # we must be *absolutely sure* that the instance we just terminated has gone
    log('Ensuring %d instances have really been terminated...' % len(replace_instances))
    old_names = [info['name'] for info in data]
    while True:
        all_instances = s.instances()
        log('all_instances=%s' % str(all_instances))
        none_left = True
        for s in all_instances:
            if s.name in old_names:
                log('Server %s still around, sleeping...' % new_name)
                time.sleep(WaitForDyingServer)
                none_left = False
        break
    log('%d instances have really gone now' % len(replace_instances))

    # start replacement instance
    if not quiet:
        print('Starting %d new instances' % len(replace_instances))
    log.debug('Starting %d new instances' % len(replace_instances))

    new_instances = []
    for info in data:
        new_image = info['image_id']
        new_key = info['key_name']
        new_security = info['security_groups']
        new_flavour = info['instance_type']
        new_userdata = ''
#        'tenancy': '...',
#        'availability_zone': 'ap-...',
        new_name = info['name']
        new_instance = s.start(1, new_name, image=new_image, flavour=new_flavour,
                               key=new_key, secgroup=new_security,
                               userdata=new_userdata)
        new_instances.append(new_instance)

    msg = '%d instances started' % len(new_instances)
    log.debug(msg)
    if not quiet:
        print(msg)

    if verbose:
        log.debug('==============================================================')
        log.debug('=========================  FINISHED  =========================')
        log.debug('==============================================================')

    return 0
