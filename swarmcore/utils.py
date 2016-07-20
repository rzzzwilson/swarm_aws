#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
General use functions for swarm.
"""

import os
import sys


# form of hostnames, %s are IP fields
HostnameMask = 'vm-%s-%s-%s-%s'


def error(msg):
    """Print error message and quit."""

    print(msg)
    sys.exit(1)

def obj_dump(obj):
    """Debug routine.  Dump attributes of an object.

    Returns a multi-line string.
    """

    result = []

    result.append('-' * 60)
    result.append(str(obj))
    for attr in dir(obj):
        if attr[0] != '_':
            result.append('    %s: %s' % (attr, getattr(obj, attr)))
    result.append('-' * 60)

    return '\n'.join(result)


def ip2name(ip):
    """Get a hostname from an IP address."""

    ip_fields = ip.split('.')
    return HostnameMask % tuple(ip_fields)


def ip_key(key):
    """Function to make a 'canonical' IP string for sorting.
    The given IP has each subfield expanded to 3 numeric digits, eg:

        given '1.255.24.6' return '001.255.014.006'
    """

    ip = key[0]
    fields = ip.split('.')
    result = []
    for f in fields:
        result.append('%03d' % int(f))

    return result

def get_instance_name(instance):
    """Get instance name.

    Return None if the instance has no name.
    """

    if instance.tags:
        for d in instance.tags:
            if 'Key' in d and d['Key'] == 'Name':
                return d['Value']

    return None

def get_instance_info(instance):
    """Get some information about an instance.

    Returns a tuple:

        (name, flavour, key, security, image, userdata)
    """

    data = instance.describe_attribute(Attribute='instanceType')
    name = data['InstanceId']
    flavour = data['InstanceType']['Value']

    data = instance.describe_attribute(Attribute='userData')
    userdata = data['UserData'].get('Value', None)

    key = None
    security = None
    image = None

    return (name, flavour, key, security, image, userdata)

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

def load_config(config_file):
    """Set global defaults from the config file.

    Returns a dictionary with values from the config file.
    """

    # see if config file exists
    if not os.path.isfile(config_file):
        utils.error("Can't find config file '%s'" % config_file)

    result = {}

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
        if global_name in result:
            utils.error("Line %d of %s: '%s' defined twice"
                        % (l+1, config_file, name))
            errors = True
        else:
            # add global+new value to dict - eval() removes any quotes
            result[name] = eval(value)

    if errors:
        sys.exit(1)

    return result

