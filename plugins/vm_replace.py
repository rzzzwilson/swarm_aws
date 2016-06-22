#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This program is designed to replace an ailing VM, gathering as much required
information from the unsane VM as possible.

Usage: vm_replace <options> <ip_or_name>

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
and <ip_or_name> is either the IP address of the unsane VM or its OpenStack
dashboard name.

The config and/or command line options are used only if information cannot be
obtained from the running server.
"""

import os
import sys
import shutil
import time
import commands
import tempfile
import traceback

import swarm
import swarm.utils as utils
from novaclient import exceptions

# program version
__program__ = 'vm_replace'
__version__ = '1.0'


# delay while polling status of dying server
WaitForDyingServer = 5

# default instance  values
DefaultAuthPath = os.path.expanduser('~/.ssh')
DefaultFlavour = 'm1.small'
DefaultImage = None
DefaultKey = 'nectarkey'
DefaultNamePrefix = 'cxwn'
DefaultSecgroup = 'xyzzy'
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


# if this module imported, turn off logging
def log(*args, **kwargs):
    pass


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


def vm_replace(vm_id, name, image, flavour, key, secgroup, userdata, auth):
    """Replace an existing cloud VM.

    vm_id     name or IP of VM to replace
    name      WN name prefix
    image     image for WN
    flavour   flavour of WN
    key       key for WN
    secgroup  security group(s)
    userdata  WN startup script path
    auth      path to auth directory
    """

    log.debug('param: vm_id=%s' % vm_id)
    log.debug('param: name=%s' % str(name))
    log.debug('param: image=%s' % str(image))
    log.debug('param: flavour=%s' % str(flavour))
    log.debug('param: key=%s' % str(key))
    log.debug('param: secgroup=%s' % str(secgroup))
    log.debug('param: userdata=%s' % str(userdata))
    log.debug('param: auth=%s' % str(auth))

    if Verbose:
        print('Replacing server %s' % vm_id)

    # connect to NeCTAR, get list of all servers
    swm = swarm.Swarm(auth_dir=auth)
    all_servers = swm.servers()

#    # debug
#    for s in all_servers:
#        if s.name.startswith(vm_id):
#            print(utils.obj_dump(s))

    # now look for the server to replace
    replace_srv = None
    for s in all_servers:
        s_ip = s.networks.items()[0][1][0]
        s_name = s.name
        if vm_id == s_ip or vm_id == s_name:
            replace_srv = s
            break
    if replace_srv is None:
        msg = "Sorry, didn't find server '%s' in running servers" % vm_id
        log(msg)
        print(msg)
        sys.exit(10)

    # gather what info we can from the running server
    srv_name = replace_srv.name
    srv_flavour_id = replace_srv.flavor['id']
    srv_flavour = swm.flavour_index_to_type(srv_flavour_id)
    srv_key = replace_srv.key_name
    srv_security = [d['name'] for d in replace_srv.security_groups]    
    srv_image = replace_srv.image['id']
    srv_userdata = None

    # debug
    log('srv_name=%s' % str(srv_name))
    log('srv_flavour=%s' % str(srv_flavour))
    log('srv_key=%s' % str(srv_key))
    log('srv_security=%s' % str(srv_security))
    log('srv_image=%s' % str(srv_image))

    # if we don't have some required information, get it from the config
    # this will probably never happen
    msg = []
    if not srv_name:
        srv_name = name
        msg.append('Getting server name from parameters: %s' % srv_name)
    if not srv_image:
        srv_image = image
        msg.append('Getting server image from parameters: %s' % srv_image)
    if not srv_flavour:
        srv_flavour = flavour
        msg.append('Getting server flavour from parameters: %s' % srv_flavour)
    if not srv_key:
        srv_key = key
        msg.append('Getting server key from parameters: %s' % srv_key)
    if not srv_security:
        srv_security = secgroup
        msg.append('Getting server security from parameters: %s' % srv_security)
    if not srv_userdata:
        srv_userdata = userdata
        msg.append('Getting server userdata from parameters: %s' % srv_userdata)
    if msg:
        log("Couldn't get some data from running server:\n%s" % '\n'.join(msg))

    # stop the unsane server, wait until its really gone
    log('Stopping server %s' % srv_name)
    if Verbose:
        print('Stopping server %s' % srv_name)

    swm.stop([replace_srv], wait=True)

    log('Server %s stopped' % srv_name)

    # we must be *absolutely sure* that the server we just terminated has gone
    log('Ensuring server %s has really been terminated...' % srv_name)
    while True:
        all_servers = swm.servers()
        for s in all_servers:
            if s.name == srv_name:
                log('Server %s still around, sleeping...' % srv_name)
                time.sleep(1.0)
                continue
        break
    log('Server %s has really gone now' % srv_name)

    # start replacement server
    if Verbose:
        print('Starting new server %s' % srv_name)
    log('Starting 1 server')

    new = swm.start(1, srv_name, image=srv_image, flavour=srv_flavour, key=srv_key,
                    secgroup=srv_security, userdata=srv_userdata)

    msg = 'Server %s started, waiting for connection' % srv_name
    log.debug(msg)
    if Verbose:
        print(msg)

    swm.wait_connect(new)

    msg = 'New server %s now connected' % srv_name
    log.debug(msg)
    if Verbose:
        print(msg)

    if Verbose:
        print('Finished!')

    log.debug('==============================================================')
    log.debug('=========================  FINISHED  =========================')
    log.debug('==============================================================')


if __name__ == '__main__':
    import swarm.log as log
    log = log.Log('/tmp/vm_replace.log', log.Log.DEBUG)

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
        if not os.path.isdir(auth):
            msg.append("Auth directory '%s' doesn't exist"
                       % auth)

        # check userdata
        if not userdata:
            msg.append("You must use the '-u' option")
        elif not os.path.isfile(userdata):
            msg.append("Userdata file '%s' is not a file"
                       % userdata)

        # if we have errors, crash here
        if msg:
            error('\n'.join(msg))


    def main(argv=None):
        import os
        import getopt

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

        # now parse the options
        auth = DefaultAuthPath
        flavour = DefaultFlavour
        image = DefaultImage
        key = DefaultKey
        prefix = DefaultNamePrefix
        secgroup = DefaultSecgroup
        userdata = DefaultUserdata
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
                prefix = param
            elif opt in ['-s', '--secgroup']:
                secgroup = param
            elif opt in ['-u', '--userdata']:
                userdata = param
            elif opt in ['-V', '--version']:
                print('%s %s' % (__program__, __version__))
                return 0
            elif opt in ['-v', '--verbose']:
                # done above
                pass

        if len(args) != 1:
            usage()
            return 1

        vm_id = args[0]

        # ensure anything with a path in it is expanded
        auth = expand_path(auth)
        userdata = expand_path(userdata)
 
        # check we have everything we need
        check_everything(auth, flavour, image, key, prefix, secgroup, userdata)

        # start the process
        secgroup = secgroup.split(',')
        vm_replace(vm_id, prefix, image, flavour, key, secgroup, userdata, auth)

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
