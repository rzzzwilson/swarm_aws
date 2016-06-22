#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This program is designed to start a number of new cloud Instances.

Usage: sw_start <options> <number>

where <options> is zero or more of:
    -a  <auth>      set path to key directory (default ~/.ssh)
    -c  <config>    set the config file to use
    -f  <flavour>   set the image flavour
    -h              print this help and stop
    -i  <image>     sets image to use
    -k  <keyname>   set key to use
    -p  <prefix>    set the name prefix
    -s  <secgroup>  set the security group(s) (can be: 'xyzzy,default')
    -u  <userdata>  path to a userdata script file
    -v              become verbose (cumulative)
    -V              print version and stop
and <number> is the number of additional instances to start.
This program only adds new Instances.

The config file overrides any built-in defaults, and the options
can override any config file values.
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

log = log.Log('sw_start.log', log.Log.DEBUG)


# program version
MajorRelease = 0
MinorRelease = 1

Plugin = {
          'entry': 'start',
          'version': '%d.%d' % (MajorRelease, MinorRelease),
          'command': 'start',
         }

# default instance  values
DefaultAuthPath = os.path.expanduser('~/.ssh')
DefaultRegion = 'ap-southeast-2'
DefaultFlavour = 't2.micro'
DefaultImage = None
DefaultKey = 'ec2-sydney'
DefaultNamePrefix = 'instance{number}'
DefaultSecgroup = 'xyzzy'
DefaultUserdata = None

# dictionary to map config names to global names
# the key is the name as it appears in the config file
# the value is the name of the global variable that should be changed
Config2Global = {'image': 'DefaultImage',
                 'region': 'DefaultRegion',
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


def warn(msg):
    """Print error message and continue."""

    log.warn(msg)
    print(msg)

def usage(msg=None):
    """Print help for the befuddled user."""

    if msg:
        print(msg+'\n')
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
            warn("Line %d of %s: name '%s' is unrecognized"
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
    try:
        (opts, args) = getopt.getopt(args, 'a:c:f:hi:k:p:s:u:vV',
                                     ['auth=', 'config=', 'flavour=', 'help',
                                      'image=', 'key=', 'prefix=',
                                      'secgroup=', 'userdata=', 'verbose',
                                      'version', ])
    except getopt.error, msg:
        print('Point 0')
        usage()
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
    # this updates the globals like DefaultAuthPath
    if config:
        load_config(config)

    # set defaults from 'kwargs'
    auth = DefaultAuthPath
    flavour = DefaultFlavour
    image = DefaultImage
    key = DefaultKey
    name = DefaultNamePrefix
    secgroup = DefaultSecgroup
    userdata = DefaultUserdata

    # now parse the options
    ConfigUpdate = True
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
            name = param
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

    if len(args) != 1:
        print('Point 1')
        usage()
        return 1
    try:
        num = int(args[0])
    except ValueError:
        error('Instance number must be a non-negative integer')
    if num < 0:
        error('Instance number must be a non-negative integer')

    log.debug('sw_start: num=%d' % num)
    log.debug('sw_start: name=%s' % name)
    log.debug('sw_start: image=%s' % image)
    log.debug('sw_start: flavour=%s' % flavour)
    log.debug('sw_start: key=%s' % key)
    log.debug('sw_start: secgroup=%s' % str(secgroup))
    log.debug('sw_start: userdata=%s' % str(userdata))
    log.debug('sw_start: auth=%s' % auth)

    # look at prefix - if it doesn't contain '{number' add it
    prefix_name = name
    if '{number:' not in name:
        name = name + '{number:03d}'

    log.debug('sw_start: name=%s' % name)
    log.debug('sw_start: prefix_name=%s' % prefix_name)

    print('Starting %d worker nodes, prefix=%s' % (num, prefix_name))

    # connect to AWS
    s = swarmcore.Swarm(auth_dir=auth)

    # get the userdata as a string
    userdata_str = None
    if userdata is not None:
        with open(userdata, 'rb') as fd:
            userdata_str = fd.read()
        log.debug('userdata:\n%s' % userdata_str)

    # start instance nodes, wait until running
    new = s.start(num, name, image=image, flavour=flavour, key=key,
                  secgroup=secgroup, userdata=userdata_str)
    log.debug('Total of %d new worker nodes, waiting for connection'
              % len(new))
    #    if Verbose:
    #    print('Total of %d new worker nodes, waiting until sane' % len(new))
#
#    s.wait_connect(new)
#    log.debug('%d new worker nodes now connected' % num)
    if Verbose:
        print('%d new worker nodes booted and sane' % len(new))

    if Verbose:
        print('Finished!')

    log.debug('==============================================================')
    log.debug('=========================  FINISHED  =========================')
    log.debug('==============================================================')



if __name__ == '__main__':
    import swarm.log as log
    log = log.Log('/tmp/sw_start.log', log.Log.DEBUG)

    def error(msg):
        """Print error message and quit."""

        print(msg)
        sys.exit(1)



    def expand_path(path):
        """Expand path into absolute form."""

        if path is not None:
            path = os.path.expanduser(path)
        return path

    def check_everything(auth, flavour, image, key, name, secgroup, userdata):
        """Check that params are correct."""

        msg = []

        # check that the NeCTAR environment is available
        for env_var in ['OS_USERNAME', 'OS_PASSWORD',
                        'OS_TENANT_NAME', 'OS_AUTH_URL']:
            try:
                os.environ[env_var]
            except KeyError:
                msg.append("You must set the '%s' environment variable"
                           % env_var)

        # check auth
        if auth is None:
            msg.append('You must specify an auth directory.')
        else:
            if not os.path.isdir(auth):
                msg.append("Auth directory '%s' doesn't exist"
                           % auth)

        # check flavour
        # can't really check anything yet

        # check image
        if image is None:
            msg.append('You must specify an image name')

        # check key
        # can't really check anything yet

        # check name
        # can't really check anything yet

        # check secgroup
        # can't really check anything yet

        # check userdata
        if userdata and not os.path.isfile(userdata):
            msg.append("Userdata file '%s' is not a file"
                       % userdata)

        # if we have errors, crash here
        if msg:
            error('\n'.join(msg))


    def main(argv=None):
        import os

        global ConfigUpdate, Verbose

        if argv is None:
            argv = sys.argv[1:]

        try:
            opts, args = getopt.getopt(argv, 'a:c:f:hi:k:p:s:u:vV',
                                       ['auth=', 'config=', 'flavour=', 'help',
                                        'image=', 'key=', 'prefix=',
                                        'secgroup=', 'userdata=', 'verbose',
                                        'version', ])
        except getopt.error, msg:
            usage()
            return 1

        # ensure anything with a path in it is expanded
        auth = expand_path(auth)
        userdata = expand_path(userdata)

        # check we have everything we need
        check_everything(auth, flavour, image, key, name, secgroup, userdata)

        # start the process
        secgroup = secgroup.split(',')
        sw_start(vm_num, name, image, flavour, key, secgroup, userdata, auth)

        return 0


    # our own handler for uncaught exceptions
    def excepthook(type, value, tb):
        msg = '\n' + '=' * 80
        msg += '\nUncaught exception:\n'
        msg += ''.join(traceback.format_exception(type, value, tb))
        msg += '=' * 80 + '\n'

        print msg
        log.critical(msg)
        sys.exit(1)

    # plug our handler into the python system
    sys.excepthook = excepthook


    sys.exit(main(sys.argv[1:]))
