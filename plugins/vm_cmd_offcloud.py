#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This program is just like vm_cmd.py, but it allows the user to execute a
command on all configured offcloud servers.

Usage: vm_cmd_offcloud <options> <command>

where <options> is zero or more of:
    -a   --auth     directory holding authentication keys (default is ~/.ssh)
    -h   --help     print this help and stop
    -i   --ip       show IP, not hostname, in results
    -V   --version  print version information and stop
    -v   --verbose  be verbose (cumulative)
and <command> is the command string to execute on the node.

An example:
vm_cmd_offcloud "puppet agent --test"
"""

import os
import threading
import Queue
import commands
import time

from swarm import log
log = log.Log('/tmp/vm_cmd_offcloud.log', log.Log.DEBUG)
import offcloud_servers


# program version
__program__ = 'vm_cmd_offcloud'
__version__ = '1.0'

# ssh timeout in seconds
SshTimeout = 5

# path to directory containing auth files
AuthDir = os.path.expanduser('~/.ssh')

# default values
DefaultAuthDir = os.path.expanduser('~/.ssh')

# timeout for SSH connection
SshConnectTimeout = 30


def cmd(servers, cmd):
    """Execute a command on each server in a list.

    servers  list of servers (name, key, ip)
    cmd      command to execute on each server

    Returns list of tuples:
       (name, key, ip, output)

    Runs in parallel.  May need throttling?
    """

    # thread class - execute a cmd via SSH
    class CmdThread(threading.Thread):
        def __init__(self, server, cmd, queue):
            """Prepare a copy thread.
            server  ip to copy to
            cmd     the copy command
            queue   result queue
            """

            threading.Thread.__init__(self)
            self.server = server
            self.cmd = cmd
            self.queue = queue

        def run(self):
            # execute the command, queue the result
            (status, output) = commands.getstatusoutput(self.cmd)
            result = [self.server, output, status]
            self.queue.put(result)

    # queue where results are placed
    result_queue = Queue.Queue()

    # generate SSH command, pass to thread
    cmd = ('ssh -q -i %%s -o "ConnectTimeout %d" -o "BatchMode yes" '
           '-o "CheckHostIP no" '
           '-o "PreferredAuthentications publickey" '
           '-o "StrictHostKeyChecking no" '
           'root@%%s "%s" 2>&1' % (SshTimeout, cmd))
    for (name, key, ip) in servers:
        key_file = os.path.join(AuthDir, key)
        cmd_cmd = cmd % (key_file, ip)
        CmdThread(ip, cmd_cmd, result_queue).start()
        log('Started thread to execute test file on %s' % name)
        log('cmd=%s' % cmd_cmd)

    # get results and build return string
    result = []
    while threading.active_count() > 1 or not result_queue.empty():
        while not result_queue.empty():
            result_tuple = result_queue.get()
            result.append(result_tuple)
        time.sleep(1)

    return result
                                                                                 

def vm_cmd_offcloud(query, auth_dir, name_prefix, show_ip):
    """Perform the query remotely.

    query        the command to execute remotely
    auth_dir     path to directory of authentication keys
    name_prefix  prefix of node name
    show_ip      True if we are to show server IP, not hostname
    """

    def ip_key(key):
        """Function to make a 'canonical' IP string for sorting.
        The given IP has each subfield expanded to 3 numeric digits, eg:
            given '1.255.24.6' return '001.255.014.006'

        The 'key' has the form ((status, output), ip).
        """

        ip = key[0]
        fields = ip.split('.')
        result = []
        for f in fields:
            result.append('%03d' % int(f))

        return result

    # get list of servers - (name, key, ip)
    all_servers = offcloud_servers.Servers

    # start output with command display
    print('# on %d servers: %s' % (len(all_servers), query))

    # kick off the parallel query- answer is list of (ip, output, status)
    answer = cmd(all_servers, query)


    # handle the case where user wants IP displayed
    if show_ip:
        # sort by IP
        answer = sorted(answer, key=ip_key)
    else:
        # get hostnames for display - list of (ip, hostname, status)
        hostnames = cmd(all_servers, 'hostname')
        new_answer = []
        for (ip, output, status) in answer:
            name = ip		# if no match
            for (h_ip, h, s) in hostnames:
                if h_ip == ip:
                    name = h.split('.')[0]
                    break
            new_answer.append((name, output, status))
        answer = new_answer
        answer = sorted(answer)

    # display results
    for (name, output, status) in answer:
        # display results
        output = output.split('\n')
        canonical_output = ('\n'+' '*17+' |').join(output)
        if status == 0:
            print('%-17s |%s' % (name, canonical_output))
        else:
            print('%-17s*|%s' % (name, canonical_output))


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
        name_prefix = None
        show_ip = False
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

        if len(args) < 1:
            usage()
            return 1
        query = ' '.join(args)

        # do the query
        vm_cmd_offcloud(query, auth_dir, name_prefix, show_ip)

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
