# magic-wormhole-transit-relay

[![Build Status](https://travis-ci.org/warner/magic-wormhole-transit-relay.svg?branch=master)](https://travis-ci.org/warner/magic-wormhole-transit-relay)
[![codecov.io](https://codecov.io/github/warner/magic-wormhole-transit-relay/coverage.svg?branch=master)](https://codecov.io/github/warner/magic-wormhole-transit-relay?branch=master)


Transit Relay server for Magic-Wormhole

This repository implements the Magic-Wormhole "Transit Relay", a server that
helps clients establish bulk-data transit connections even when both are
behind NAT boxes. Each side makes a TCP connection to this server and
presents a handshake. Two connections with identical handshakes are glued
together, allowing them to pretend they have a direct connection.

This server used to be included in the magic-wormhole repository, but was
split out into a separate repo to aid deployment and development.

See docs/running.md for instructions to launch the server.
