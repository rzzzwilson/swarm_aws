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
import getopt
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

Plugin = {
          'entry': 'replace',
          'version': '%d.%d' % (MajorRelease, MinorRelease),
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

    # parse the command args
    try:
        (opts, args) = getopt.getopt(args, 'a:c:f:hi:k:p:qr:s:u:vVy',
                                     ['auth=', 'config=', 'flavour=', 'help',
                                      'image=', 'key=', 'prefix=', 'quiet',
                                      'region=', 'secgroup=', 'userdata=',
                                      'verbose', 'version', 'yes', ])
    except getopt.error, e:
        usage(str(e.msg))
        return 1

    # do -c and -v now
    config = None
    Verbose = False
    for (opt, param) in opts:
        if opt in ['-c', '--config']:
            config = param
        if opt in ['-v', '--verbose']:
            Verbose = True
            log.bump_level()

    # read config file, if we have one
    # this may update the variables just set from defaults
    if config:
        load_config(config)

    # set variables to possibly modified defaults
    auth = None
    flavour = None
    image = None
    key = None
    prefix = None
    quiet = False
    region = None
    secgroup = None
    userdata = None
    y_opt = False

    # now parse the options
    # this is the users final chance to change default values
    for (opt, param) in opts:
        if opt in ['-a', '--auth']:
            auth = param
        elif opt in ['-c', '--config']:
            # done above
            pass
        elif opt in ['-f', '--flavour']:
            flavour = param
        elif opt in ['-h', '--help']:
            usage()
            return 0
        elif opt in ['-i', '--image']:
            image = param
        elif opt in ['-k', '--key']:
            key = param
        elif opt in ['-p', '--prefix']:
            prefix = param
        elif opt in ['-q', '--quiet']:
            quiet = True
        elif opt in ['-r', '--region']:
            region = param
        elif opt in ['-s', '--secgroup']:
            secgroup = param
        elif opt in ['-u', '--userdata']:
            userdata = param
        elif opt in ['-V', '--version']:
            print('%s %s' % (Plugin['command'], Plugin['version']))
            return 0
        elif opt in ['-v', '--verbose']:
            # done above
            pass
        elif opt in ['-y', '--yes']:
            y_opt = True

    instances = args
    if len(args) == 0:
        if prefix is None:
            usage('You must supply name(s) of the instances to replace.')
            return 1

    log.debug('param: instances=%s' % str(instances))
    log.debug('param: prefix=%s' % str(prefix))
    log.debug('param: image=%s' % str(image))
    log.debug('param: flavour=%s' % str(flavour))
    log.debug('param: key=%s' % str(key))
    log.debug('param: secgroup=%s' % str(secgroup))
    log.debug('param: userdata=%s' % str(userdata))
    log.debug('param: auth=%s' % str(auth))

#    if not quiet:
#        print('Replacing instance(s) %s' % str(instances))

    # connect to AWS
    s = swarmcore.Swarm(auth_dir=auth, verbose=Verbose)
    all_instances = s.instances()

    # get list of instances satisfying 'prefix' option
    replace_instances = all_instances
    if prefix:
        replace_instances = []
        for instance in all_instances:
            instance_name = utils.get_instance_name(instance)

            if instance_name.startswith(prefix):
                replace_instances.append(instance)

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
            msg = ("Sorry, didn't find any instances with names in '%s'" % str(instances))
        else:
            msg = "You must specify either the '-p' option, one or more names or both"
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

    if Verbose:
        log.debug('==============================================================')
        log.debug('=========================  FINISHED  =========================')
        log.debug('==============================================================')

    return 0
