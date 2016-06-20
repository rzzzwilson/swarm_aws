#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This program is used to stop a set of VMs.

Usage: vm_stop <options>

where <options> is zero or more of:
    -h   --help     print this help and stop
    -p   --prefix   name prefix used to select nodes (required)
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)
    -w   --wait     wait until VMs actually stopped

As an example, the following will stop all VMs whose name start 'cxwn' and
will wait until the servers are actually gone:
    vm_stop -p cxwn -w
"""

import os
import swarm
from swarm import log
log = log.Log('/tmp/vm_stop.log', log.Log.DEBUG)


# program version
__program__ = 'vm_stop'
__version__ = '1.0'


def vm_stop(name_prefix, wait=False):
    """Stop a set of VMs.

    name_prefix  prefix of VM names
    wait         True if we wait until servers actually gone
    """

    # get all servers
    swm = swarm.Swarm()
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

    print("Stopping %d servers named '%s*'"
          % (len(filtered_servers), '*|'.join(prefixes)))
    log("Stopping %d servers named '%s*'"
        % (len(filtered_servers), '*|'.join(prefixes)))

    # give user a chance to bail
    if len(filtered_servers) == 0:
        print("No VMs found with prefix: '%s*'" % '*|'.join(prefixes))
        return

    answer = raw_input('Stopping %d VMs.  Proceed? (y/N): '
                       % len(filtered_servers))
    answer = answer.strip().lower()
    if len(answer) == 0 or answer[0] != 'y':
        return

    log.info('User elected to terminate %d VMs:\n%s'
             % (len(filtered_servers), str(filtered_servers)))

    # stop all the servers
    swm.stop(filtered_servers, wait)

    if Verbose > 0:
        print('Stopped %d VMs.' % len(filtered_servers))


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
        global Verbose

        if argv is None:
            argv = sys.argv[1:]

        try:
            opts, args = getopt.getopt(argv, 'hp:Vviw',
                                       ['help', 'prefix=',
                                        'version', 'verbose', 'wait'])
        except getopt.error, msg:
            usage()
            return 1

        Verbose = 0
        for (opt, param) in opts:
            if opt in ['-v', '--verbose']:
                Verbose += 1
                log.bump_level()

        # now parse the options
        name_prefix = None
        wait = False
        for (opt, param) in opts:
            if opt in ['-h', '--help']:
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
            elif opt in ['-w', '--wait']:
                wait = True

        if len(args) != 0:
            usage()
            return 1

        if name_prefix is None:
            error('You must specify a VM name prefix.')

        # do the query
        vm_stop(name_prefix, wait)

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
