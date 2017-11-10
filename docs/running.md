# Running the Transit Relay

First off, you probably don't need to run a relay. The ``wormhole`` command,
as shipped from magic-wormhole.io, is configured to use a default Transit
Relay operated by the author of Magic-Wormhole. This can be changed with the
``--transit-helper=`` argument, and other applications that import the
Wormhole library might point elsewhere.

The only reasons to run a separate relay are:

* You are a kind-hearted server admin who wishes to support the project by
  paying the bandwidth costs incurred by your friends, who you instruct in
  the use of ``--transit-helper=``.
* You publish a different application, and want to provide your users with a
  relay that fails at different times than the official one

## Installation

To run a transit relay, first you need an environment to install it.

* create a virtualenv
* ``pip install magic-wormhole-transit-relay`` into this virtualenv

```
% virtualenv tr-venv
...
% tr-venv/bin/pip install magic-wormhole-transit-relay
...
```

## Running

The transit relay is not a standalone program: rather it is a plugin for the
Twisted application-running tools named ``twist`` (which only runs in the
foreground) and ``twistd`` (which daemonizes). To run the relay for testing,
use something like this:

```
% tr-venv/bin/twist transitrelay [ARGS]
2017-11-09T17:07:28-0800 [-] not blurring access times
2017-11-09T17:07:28-0800 [-] Transit starting on 4001
2017-11-09T17:07:28-0800 [wormhole_transit_relay.transit_server.Transit#info] Starting factory <wormhole_transit_relay.transit_server.Transit object at 0x7f01164b4550>
...
```

The relevant arguments are:

* ``--port=``: the endpoint to listen on, like ``tcp:4001``
* ``--log-fd=``: writes JSON lines to the given file descriptor for each connection
* ``--usage-db=``: maintains a SQLite database with current and historical usage data
* ``--blur-usage=``: if provided, logs are rounded to the given number of
  seconds, and data sizes are rounded too

When you use ``twist``, the relay runs in the foreground, so it will
generally exit as soon as the controlling terminal exits. For persistent
environments, you should daemonize the server.

## Daemonization

A production installation will want to daemonize the server somehow. One
option is to use ``twistd`` (the daemonizing version of ``twist``). This
takes the same plugin name and arguments as ``twist``, but forks into the
background, detaches from the controlling terminal, and writes all output
into a logfile:

```
% tr-venv/bin/twistd transitrelay [ARGS]
% cat twistd.log
2017-11-09T17:07:28-0800 [-] not blurring access times
2017-11-09T17:07:28-0800 [-] Transit starting on 4001
2017-11-09T17:07:28-0800 [wormhole_transit_relay.transit_server.Transit#info] Starting factory <wormhole_transit_relay.transit_server.Transit object at 0x7f01164b4550>
...
% cat twistd.pid; echo
18985
```

To shut down a ``twistd``-based server, you'll need to look in the
``twistd.pid`` file for the process id, and kill it:

```
% kill `cat twistd.pid`
```

To start the server each time the host reboots, you might use a crontab
"@reboot" job, or a systemd unit.

Another option is to run ``twist`` underneath a daemonization tool like
``daemontools`` or ``start-stop-daemon``. Since ``twist`` is just a regular
program, this leaves the daemonization tool in charge of issues like
restarting a process that exits unexpectedly, limiting the rate of
respawning, and switching to the correct user-id and base directory.

Packagers who create an installable transit-relay server package should
choose a suitable daemonization tool that matches the practices of the target
operating system. For example, Debian/Ubuntu packages should probably include
a systemd unit that runs ``twist transitrelay`` in some
``/var/run/magic-wormhole-transit-relay/`` directory.

Production environments that want to monitor the server for capacity
management can use the ``--log-fd=`` option to emit logs, then route those
logs into a suitable analysis tool. Other environments might be content to
use ``--usage-db=`` and run the included Munin plugins to monitor usage.

## Configuring Clients

The transit relay will listen on an "endpoint" (usually a TCP port, but it
could be a unix-domain socket or any other Endpoint that Twisted knows how to
listen on). By default this is ``tcp:4001``. The relay does not know what
hostname or IP address might point at it.

Clients are configured with a "Transit Helper" setting that includes both the
hostname and the port number, like the default
``tcp:transit.magic-wormhole.io:4001``. The standard ``wormhole`` tool takes
a ``--transit-helper=`` argument to override this. Other applications that
use ``wormhole`` as a library will have internal means to configure which
transit relay they use.

If you run your own transit relay, you will need to provide the new settings
to your clients for it to be used.

The standard ``wormhole`` tool is used by two sides: the sender and the
receiver. Both sides exchange their configured transit relay with their
partner. So if the sender overrides ``--transit-helper=`` but the receiver
does not, they might wind up using either relay server, depending upon which
one gets an established connection first.
