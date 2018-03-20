User-visible changes in "magic-wormhole-transit-relay":

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
