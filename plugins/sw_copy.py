#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This plugin is used to copy a file to many instances.

Usage: swarm copy <options> <src> <dst>

where <options> is zero or more of:
    -a   --auth     directory holding authentication keys (default is ~/.ssh)
    -h   --help     print this help and stop
    -p   --prefix   name prefix used to select nodes (default is all servers)
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)
and <src> is the source file, <dst> is the remote destination.  Note
that the <dst> must be valid as an scp destination.

To copy a file to every instance with  prefix of 'test_', do:

    swarm copy -p test_ /tmp/config /var/spool/torque/mom_priv/config
"""

import os
import sys
import getopt
import swarmcore
from swarmcore import log
log = log.Log('swarm.log', log.Log.DEBUG)


# program version
MajorRelease = 0
MinorRelease = 1

Plugin = {
          'entry': 'copy',
          'version': '%d.%d' % (MajorRelease, MinorRelease),
          'command': 'copy',
         }

# default values
DefaultAuthDir = os.path.expanduser('~/.ssh')


def error(msg):
    """Print error message and quit."""

    print(msg)
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

def copy(args, kwargs):
    """Perform the copy on required instances.

    args    list of arg values
    kwargs  a dict of default values
    """

    # parse the command params
    try:
        (opts, args) = getopt.getopt(args, 'a:hip:Vv',
                                     ['auth=', 'help', 'ip', 'prefix=',
                                      'version', 'verbose'])
    except getopt.error, msg:
        usage()
        return 1
    for (opt, param) in opts:
        if opt in ['-v', '--verbose']:
            log.bump_level()

    # now parse the options
    auth_dir = DefaultAuthDir
    show_ip = False
    name_prefix = None
    for (opt, param) in opts:
        if opt in ['-a', '--auth']:
            auth_dir = param
            if not os.path.isdir(auth_dir):
                error("Authentication directory '%s' doesn't exist"
                      % auth_dir)
        elif opt in ['-h', '--help']:
            usage()
            return 0
        elif opt in ['-i', '--ip']:
            show_ip = True
        elif opt in ['-p', '--prefix']:
            name_prefix = param
        elif opt in ['-V', '--version']:
            print('%s %s' % (__program__, __version__))
            return 0
        elif opt in ['-v', '--verbose']:
            pass        # done above

    # get 'src ' and 'dst' params
    if len(args) != 2:
        usage()
        return 1

    (src, dst) = args
    log.debug('copy: auth_dir=%s, show_ip=%s, name_prefix=%s'
              % (auth_dir, str(show_ip), str(name_prefix)))

    # get all instances
    swm = swarmcore.Swarm()
    all_instances = swm.instances()

    # get a filtered list of instances depending on name_prefix
    prefixes = []
    filtered_instances = all_instances
    if name_prefix is not None:
        prefixes = name_prefix.split(',')
        filtered_instances = []
        for prefix in prefixes:
            filter = swm.filter_name_prefix(prefix)
            s = swm.filter(all_instances, filter)
            filtered_instances = swm.union(filtered_instances, s)

    print("# doing 'copy' on %d instances named '%s*'"
          % (len(filtered_instances), '*|'.join(prefixes)))

    # kick off the parallel copy
    answer = swm.copy(filtered_instances, src, dst, swm.info_ip())

    # sort by IP
    answer = sorted(answer, key=ip_key)

    # display results
    for (output, status, ip) in answer:
        output = output.split('\n')
        canonical_output = ('\n'+' '*17+'|').join(output)
        if status == 0:
            print('%-17s |%s' % (ip, canonical_output))
        else:
            print('%-17s*|%s' % (ip, canonical_output))
