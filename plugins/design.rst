Plugins
=======

We want to easily add extra commands to **swarm**.
We do this with a *plugin* mechanism.

Each plugin file must be a ***.py** file.  The file must contain
a top-level dictionary called *Plugin*:

    Plugin = {
              'entry': 'plugin',
              'version': '%d.%d' % (MajorRelease, MinorRelease),
              'command': 'cmd',
             }

This dictionary will contain the keys:

    version    a version string
    command    a string holding the name of the command
    entry      a string holding the entry function name

The entry function will have the signature:

    def plugin(auth_dir=<default_dir>, name_prefix=None, show_ip=False, *args)

where the **auth_dir** parameter holds the path to the authentication
credentials, **name_prefix** holds the instance name prefix, and **show_ip**
is True if the results are to show the instance IP.

The ***args** parameter is a tuple holding the command parameters.
