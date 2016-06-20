#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This program is used to copy a file to many server nodes.

Usage: vm_copy <options> <src> <dst>

where <options> is zero or more of:
    -a   --auth     directory holding authentication keys (default is ~/.ssh)
    -h   --help     print this help and stop
    -p   --prefix   name prefix used to select nodes (default is all servers)
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)
and <src> is the source file, <dst> is the remote destination.  Note
that the <dst> must be valid as an scp destination.

To copy a file to every new interactive node, do:
vm_copy -p cxin /tmp/config /var/spool/torque/mom_priv/config
"""

import os

import swarm
from swarm import log
log = log.Log('/tmp/vm_copy.log', log.Log.DEBUG)


# program version
__program__ = 'vm_copy'
__version__ = '1.0'


# default values
DefaultAuthDir = os.path.expanduser('~/.ssh')


def ip_key(key):
    """Function to make a 'canonical' IP string for sorting.
    The given IP has each subfield expanded to 3 numeric digits, eg:

        given '1.255.24.6' return '001.255.014.006'
    """

    (ip, _) = key
    fields = ip.split('.')
    result = []
    for f in fields:
        result.append('%03d' % int(f))

    return result


def vm_copy(auth_dir, name_prefix, src, dst):
    """Perform the copy.

    auth_dir     path to directory of authentication keys
    name_prefix  prefix of node name
    src          source file
    dst          remote destination file
    """

    def ip_key(key):
        """Function to make a 'canonical' IP string for sorting.
        The given IP has each subfield expanded to 3 numeric digits, eg:

            given '1.255.24.6' return '001.255.014.006'
        """

        (_, _, ip) = key
        fields = ip.split('.')
        result = []
        for f in fields:
            result.append('%03d' % int(f))

        return result

    # get all servers
    swm = swarm.Swarm(auth_dir)
    all_servers = swm.servers()

    # get a filtered list of servers depending on name_prefix
    prefixes = []
    filtered_servers = all_servers
    if name_prefix is not None:
        prefixes = name_prefix.split(',')
        filtered_servers = []
        for prefix in prefixes:
            filter = swm.filter_name_prefix(prefix)
            s = swm.filter(all_servers, filter)
            filtered_servers = swm.union(filtered_servers, s)

    print("# copy %s to %s on %d servers named '%s*'"
          % (src, dst, len(filtered_servers), '*|'.join(prefixes)))

    # kick off the parallel copy
    answer = swm.copy(filtered_servers, src, dst, swm.info_ip())

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


if __name__ == '__main__':
    import sys
    import getopt

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


    def main(argv=None):
        if argv is None:
            argv = sys.argv[1:]

        try:
            opts, args = getopt.getopt(argv, 'a:hp:Vv',
                                       ['auth=', 'help', 'prefix=',
                                        'version', 'verbose'])
        except getopt.error, msg:
            usage()
            return 1
        for (opt, param) in opts:
            if opt in ['-v', '--verbose']:
                log.bump_level()

        # now parse the options
        auth_dir = DefaultAuthDir
        name_prefix = None
        for (opt, param) in opts:
            if opt in ['-a', '--auth']:
                auth_dir = param
                if not os.path.isdir(auth_dir):
                    error("Authentication directory '%s' doesn't exist" % auth_dir)
            elif opt in ['-h', '--help']:
                usage()
                return 0
            elif opt in ['-p', '--prefix']:
                name_prefix = param
            elif opt in ['-V', '--version']:
                print('%s %s' % (__program__, __version__))
                return 0
            elif opt in ['-v', '--verbose']:
                pass
#                log.bump_level()

        if len(args) != 2:
            usage()
            return 1
        src = args[0]
        dst = args[1]

        # do the copy
        vm_copy(auth_dir, name_prefix, src, dst)

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
