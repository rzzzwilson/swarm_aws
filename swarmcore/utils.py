#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
General use functions for swarm.
"""

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

