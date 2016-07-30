swarm_aws
=========

**swarm_aws** is a set of simple tools to create/maintain/destroy AWS instances.

The requirements for **swarm_aws** are boto3 and python2.

Examples
========

Some small examples of current functionality.

To stop all instances, start three new instances, copy a file to /tmp,
list the copied files and then stop the instances::

    swarm stop -p "" -y
    swarm wait -p "" terminated
    swarm start -c instance_config -p "test_swarm_{number}" 3
    swarm wait -p "test_swarm" ssh
    swarm copy -p "test_swarm" README.rst "/tmp"
    swarm cmd -p "test_swarm" "ls -lrt /tmp"
    swarm stop -p "test_swarm" -y

Note: after the "swarm start" we need to wait until the instances can accept
SSH connections.

Another example is the script **periscope** which uses **sshuttle** to create
a poor man's VPN.

Directories
-----------

**swarmcore** - the basic core code

**plugins** - the command plugins for **swarm_aws**

See the README files in each directory for more information.

