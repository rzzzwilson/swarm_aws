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

The harness will look in the **plugins** directory at startup looking for
plugins and populating the plugin environment.

Plugin Introspection
____________________

Each plugin will have a function: **swarm_plugin()**.

Calling this function gets information for that plugin.  The returned dictionary
will contain:

* plugin code name (**name**)
* plugin entry function (**entry**)
* plugin version string (**version**)
* ???


If the function doesn't exist the file isn't a swarm_ams plugin.

Harness
-------

The harness code will be called:

    swarm <cmd> <arg1> <arg2> ...

The **<cmd>** string is supplied by the plugin.
