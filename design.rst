Design
======

The basic low-level code is in the **swarmcore** directory.

The **plugins** directory holds the command plugins.

Plugins
-------

Each plugin implements one simple command.

Each plugin is designed to be imported and has introspection code that
allows the harness to find:

* the command used to call the plugin code
* version of the plugin
* the command name (<cmd>)
* ???

The harness will look in the **plugins** directory at startup looking for
plugins and populating the plugin environment.

~~Each plugin will also be a standalone executable.~~

Plugin Introspection
____________________

Each plugin will have a top-level dictionary **Plugin**.

Each dictionary contains information for the plugin.  The dictionary
will contain:

* plugin code name (**name**)
* plugin entry function (**entry**)
* plugin version string (**version**)
* plugin command string (**command**)
* ???


If the dictionary doesn't exist the file isn't a swarm_ams plugin.

As of 3 July 2016, the **Plugin** dictionary in *sw_start.py* contains:

::

    # program version
    MajorRelease = 0
    MinorRelease = 1

    Plugin = {
              'entry': 'start',
              'version': '%d.%d' % (MajorRelease, MinorRelease),
              'command': 'start',
             }


Harness
-------

The harness code will be called:

    swarm <cmd> <arg1> <arg2> ...

The **<cmd>** string determines which plugin the args are passed to.
The plugin code will see a **sys.argv** that contains:

    <cmd> <arg1> <arg2> ...
