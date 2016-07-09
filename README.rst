swarm_aws
=========

**swarm_aws** is a set of simple tools to create/maintain/destroy AWS instances.

The requirements for **swarm_aws** are boto3 and python2.

Examples
========

Some small examples of current functionality.

To stop all instances, start three new instances, copy a file to /tmp,
list the copied files and then stop the instances::

    swarm stop -p ""
    swarm start -c instance_config -p "example_{number}" 3
    swarm wait -p example ssh
    swarm copy -p example README.rst "/tmp"
    swarm cmd -p example "ls -lrt /tmp"
    swarm stop -p ""

Note: after the "swarm start" we need to wait until the instances can accept
SSH connections.

Directories
-----------

**swarm** - the basic core code

**plugins** - the command plugins for **swarm_aws**

See the README files in each directory for more information.

