# Transit Protocol

The Transit protocol is responsible for establishing an encrypted
bidirectional record stream between two programs. It must be given a "transit
key" and a set of "hints" which help locate the other end (which are both
delivered by Wormhole).

The protocol tries hard to create a **direct** connection between the two
ends, but if that fails, it uses a centralized relay server to ferry data
between two separate TCP streams (one to each client).

This repository provides that centralized relay server. For details of the
protocol spoken by the clients, and the client-side API, please see
``transit.md`` in the magic-wormhole repository.

## Relay

The **Transit Relay** is a host which offers TURN-like services for
magic-wormhole instances. It uses a TCP-based protocol with a handshake to
determine which connection wants to be connected to which.

When connecting to a relay, the Transit client first writes RELAY-HANDSHAKE
to the socket, which is `please relay %s\n`, where `%s` is the hex-encoded
32-byte HKDF derivative of the transit key, using `transit_relay_token` as
the context. The client then waits for `ok\n`.

The relay waits for a second connection that uses the same token. When this
happens, the relay sends `ok\n` to both, then wires the connections together,
so that everything received after the token on one is written out (after the
ok) on the other. When either connection is lost, the other will be closed
(the relay does not support "half-close").

When clients use a relay connection, they perform the usual sender/receiver
handshake just after the `ok\n` is received: until that point they pretend
the connection doesn't even exist.

Direct connections are better, since they are faster and less expensive for
the relay operator. If there are any potentially-viable direct connection
hints available, the Transit instance will wait a few seconds before
attempting to use the relay. If it has no viable direct hints, it will start
using the relay right away. This prefers direct connections, but doesn't
introduce completely unnecessary stalls.
