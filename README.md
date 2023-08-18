# magic-wormhole-transit-relay

[![PyPI](http://img.shields.io/pypi/v/magic-wormhole-transit-relay.svg)](https://pypi.python.org/pypi/magic-wormhole-transit-relay)
![Tests](https://github.com/magic-wormhole/magic-wormhole-transit-relay/workflows/Tests/badge.svg)
[![codecov.io](https://codecov.io/github/magic-wormhole/magic-wormhole-transit-relay/coverage.svg?branch=master)](https://codecov.io/github/magic-wormhole/magic-wormhole-transit-relay?branch=master)


Transit Relay server for Magic-Wormhole

This repository implements the Magic-Wormhole "Transit Relay", a server that
helps clients establish bulk-data transit connections even when both are
behind NAT boxes. Each side makes a TCP connection to this server and
presents a handshake. Two connections with identical handshakes are glued
together, allowing them to pretend they have a direct connection.

This server used to be included in the magic-wormhole repository, but was
split out into a separate repo to aid deployment and development.

## Quick Example (running on a VPS)

If you would like to set up a transit server on a VPS or other publicly-accessible server running Ubuntu:

```
# Install Python 3 pip and twist
apt install python3-pip python3-twisted

# Install magic-wormhole-transit-relay
pip3 install magic-wormhole-transit-relay

# Run transit-relay in the background
twistd3 transitrelay

# Check on logs
cat twistd.log  # or `tail -f twistd.log`

# Kill transit-relay
kill `cat twistd.pid`
```

Assuming you _haven't_ killed transit-relay, when you do `wormhole send`, make sure you add the `--transit-helper` argument, like:

```
wormhole send --transit-helper=tcp:[server ip here]:4001 file-to-send
```

On the receiving end, paste in the command output by `wormhole send`.

## Further Instructions

See docs/running.md for instructions to launch the server.
