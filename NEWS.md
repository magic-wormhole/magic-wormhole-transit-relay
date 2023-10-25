User-visible changes in "magic-wormhole-transit-relay":

## unreleased

* drop Python 2, Python 3.5 and 3.6 support
* add Python 3.9, 3.10, 3.11 and 3.12 to CI
* update versioneer to 0.29


## Release 0.2.1 (11-Sep-2019)

* listen on IPv4+IPv6 properly (#12)


## Release 0.2.0 (10-Sep-2019)

* listen on IPv4+IPv6 socket by default (#12)
* enable SO_KEEPALIVE on all connections (#9)
* drop support for py3.3 and py3.4
* improve munin plugins


## Release 0.1.2 (19-Mar-2018)

* Allow more simultaneous connections, by increasing the rlimits() ceiling at
  startup
* Improve munin plugins
* Get tests working on Windows


## Release 0.1.1 (14-Feb-2018)

Improve logging and munin graphing tools: previous version would count bad
handshakes twice (once as "errory", and again as "lonely"). The munin plugins
have been renamed.


## Release 0.1.0 (12-Nov-2017)

Initial release. Forked from magic-wormhole-0.10.3 (12-Sep-2017).
