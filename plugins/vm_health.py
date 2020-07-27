"""
This program is used to check the health of VMs.  Things like:
 . can we SSH to the VM?
 . is the VM hostname correct?
 . does the console log show any problem?
 . etc
The health checks are performed on all running VMs, filtered by any
criteria the user wants.

Usage: vm_health <options>

where <options> is zero or more of:
    -a   --auth     directory holding authentication keys (default is ~/.ssh)
    -h   --help     print this help and stop
    -i   --ip       show source as IP address, not VM name
    -p   --prefix   name prefix used to select nodes (default is all servers)
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)

An example:
    vm_health -p at3-wn
this checks the health of all VMs whose names start with "at3-wn".
"""

import os

import swarm
from swarm import utils
from swarm import log
log = log.Log('/tmp/vm_health.log', log.Log.DEBUG)


# program version
__program__ = 'vm_health'
__version__ = '1.0'

# default values
DefaultAuthDir = os.path.expanduser('~/.ssh')


def name_key(key):
    """Function to sort data by name (field 1)."""

    return key[0]


def vm_health(auth_dir, name_prefix, show_ip):
    """Perform the health check on required VMs.

    auth_dir     path to directory of authentication keys
    name_prefix  prefix of node name, if None do all servers
    show_ip      if True show server IP, else show openstack name
    """

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

    print("# health of %d servers with name starting '%s*'"
          % (len(filtered_servers), '*|'.join(prefixes)))
    log("# health of %d servers with name starting '%s*'"
        % (len(filtered_servers), '*|'.join(prefixes)))

    print('server            E hostname                                       status')
    print('-----------------+-+----------------------------------------------+------')

    # kick off the parallel hostname and classify check
    answer = swm.info(filtered_servers,
                    swm.info_ip(), swm.info_hostname(), swm.info_classify())

    # handle the case where user wants IP displayed
    if show_ip:
        # add name field that is just the IP
        new_answer = [(ip, ip, h, c) for (ip, h, c) in answer]
        answer = sorted(new_answer, key=utils.ip_key)
    else:
        # get openstack names, make new answer
        ip_names = swm.info(filtered_servers, swm.info_ip(), swm.info_name())
        new_answer = []
        for (os_ip, os_name) in ip_names:
            name = os_ip                # if no match
            for (ip, h, c) in answer:
                if ip == os_ip:
                    name = os_name
                    break
            new_answer.append((name, ip, h, c))
        answer = sorted(new_answer, key=name_key)

    # display results
    bad_hostname_count = 0
    bad_ssh_count = 0
    bad_class_count = 0
    for (name, ip, hostname, classification) in answer:
        expected_name = utils.ip2name(ip)
        if hostname != expected_name:
            print('%-17s *|%-46s| %s' % (name, hostname, classification))
            if hostname == '':
                bad_ssh_count += 1
            else:
                bad_hostname_count += 1
        else:
            print('%-17s  |%-46s| %s' % (name, hostname, classification))
        if classification != 'OK':
            bad_class_count += 1
    print('-----------------+-+----------------------------------------------+------')
    print('%d VMs with a bad hostname' % bad_hostname_count)
    print("%d VMs probably 'autistic'" % bad_ssh_count)
    print('%d VMs with a bad classification' % bad_class_count)


if __name__ == '__main__':
    import sys
    import getopt
    import traceback

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
            opts, args = getopt.getopt(argv, 'a:hip:Vv',
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
                pass
#                log.bump_level()

        if len(args) > 0:
            usage()
            return 1

        # do the query
        vm_health(auth_dir, name_prefix, show_ip)

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
