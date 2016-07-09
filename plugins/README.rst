Plugins
=======

We want to easily add extra commands to **swarm**.
We do this with a *plugin* mechanism.

Each plugin file must be a ***.py** file.  The file must contain
a top-level dictionary called *Plugin*:

::

    Plugin = {
              'entry': 'plugin',
              'version': '%d.%d' % (MajorRelease, MinorRelease),
              'command': 'cmd',
             }

This dictionary will contain the keys:

::

    version    a version string
    command    a string holding the name of the command
    entry      a string holding the entry function name

The entry function will have the signature:

::

    def plugin(args)

where the **args** parameter holds a list of command line arguments that are
parsed by the plugin code to find options and arguments.

Caveat
------

The plugin mechanism works, but is a tad clumsy.
See if we can make it more pythonic.
