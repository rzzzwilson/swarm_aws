Design
======

The basic low-level code is on the **swarm_core** directory.

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

Harness
-------

The harness code will be called:

    swarm <cmd> <arg1> <arg2> ...

The **<cmd>** string is supplied by the plugin.
