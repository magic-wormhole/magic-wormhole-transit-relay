from collections import defaultdict

import automat
from twisted.python import log
from zope.interface import (
    Interface,
    Attribute,
)


class ITransitClient(Interface):
    """
    Represents the client side of a connection to this transit
    relay. This is used by TransitServerState instances.
    """

    started_time = Attribute("timestamp when the connection was established")

    def send(data):
        """
        Send some byets to the client
        """

    def disconnect():
        """
        Disconnect the client transport
        """

    def connect_partner(other):
        """
        Hook up to our partner.
        :param ITransitClient other: our partner
        """

    def disconnect_partner():
        """
        Disconnect our partner's transport
        """


class ActiveConnections(object):
    """
    Tracks active connections.

    A connection is 'active' when both sides have shown up and they
    are glued together (and thus could be passing data back and forth
    if any is flowing).
    """
    def __init__(self):
        self._connections = set()

    def register(self, side0, side1):
        """
        A connection has become active so register both its sides

        :param TransitConnection side0: one side of the connection
        :param TransitConnection side1: one side of the connection
        """
        self._connections.add(side0)
        self._connections.add(side1)

    def unregister(self, side):
        """
        One side of a connection has become inactive.

        :param TransitConnection side: an inactive side of a connection
        """
        self._connections.discard(side)


class PendingRequests(object):
    """
    Tracks outstanding (non-"active") requests.

    We register client connections against the tokens we have
    received. When the other side shows up we can thus match it to the
    correct partner connection. At this point, the connection becomes
    "active" is and is thus no longer "pending" and so will no longer
    be in this collection.
    """

    def __init__(self, active_connections):
        """
        :param active_connections: an instance of ActiveConnections where
            connections are put when both sides arrive.
        """
        self._requests = defaultdict(set) # token -> set((side, TransitConnection))
        self._active = active_connections

    def unregister(self, token, side, tc):
        """
        We no longer care about a particular client (e.g. it has
        disconnected).
        """
        if token in self._requests:
            self._requests[token].discard((side, tc))
            if not self._requests[token]:
                # no more sides; token is dead
                del self._requests[token]
        self._active.unregister(tc)

    def register(self, token, new_side, new_tc):
        """
        A client has connected and successfully offered a token (and
        optional 'side' token). If this is the first one for this
        token, we merely remember it. If it is the second side for
        this token we connect them together.

        :param bytes token: the token for this connection.

        :param bytes new_side: None or the side token for this connection

        :param TransitServerState new_tc: the state-machine of the connection

        :returns bool: True if we are the first side to register this
            token
        """
        potentials = self._requests[token]
        for old in potentials:
            (old_side, old_tc) = old
            if ((old_side is None)
                or (new_side is None)
                or (old_side != new_side)):
                # we found a match

                # drop and stop tracking the rest
                potentials.remove(old)
                for (_, leftover_tc) in potentials.copy():
                    # Don't record this as errory. It's just a spare connection
                    # from the same side as a connection that got used. This
                    # can happen if the connection hint contains multiple
                    # addresses (we don't currently support those, but it'd
                    # probably be useful in the future).
                    leftover_tc.partner_connection_lost()
                self._requests.pop(token, None)

                # glue the two ends together
                self._active.register(new_tc, old_tc)
                new_tc.got_partner(old_tc)
                old_tc.got_partner(new_tc)
                return False

        potentials.add((new_side, new_tc))
        return True
        # TODO: timer


class TransitServerState(object):
    """
    Encapsulates the state-machine of the server side of a transit
    relay connection.

    Once the protocol has been told to relay (or to relay for a side)
    it starts passing all received bytes to the other side until it
    closes.
    """

    _machine = automat.MethodicalMachine()
    _client = None
    _buddy = None
    _token = None
    _side = None
    _first = None
    _mood = "empty"
    _total_sent = 0

    def __init__(self, pending_requests, usage_recorder):
        self._pending_requests = pending_requests
        self._usage = usage_recorder

    def get_token(self):
        """
        :returns str: a string describing our token. This will be "-" if
            we have no token yet, or "{16 chars}-<unsided>" if we have
            just a token or "{16 chars}-{16 chars}" if we have a token and
            a side.
        """
        d = "-"
        if self._token is not None:
            d = self._token[:16].decode("ascii")

            if self._side is not None:
                d += "-" + self._side.decode("ascii")
            else:
                d += "-<unsided>"
        return d

    @_machine.input()
    def connection_made(self, client):
        """
        A client has connected. May only be called once.

        :param ITransitClient client: our client.
        """
        # NB: the "only called once" is enforced by the state-machine;
        # this input is only valid for the "listening" state, to which
        # we never return.

    @_machine.input()
    def please_relay(self, token):
        """
        A 'please relay X' message has been received (the original version
        of the protocol).
        """

    @_machine.input()
    def please_relay_for_side(self, token, side):
        """
        A 'please relay X for side Y' message has been received (the
        second version of the protocol).
        """

    @_machine.input()
    def bad_token(self):
        """
        A bad token / relay line was received (e.g. couldn't be parsed)
        """

    @_machine.input()
    def got_partner(self, client):
        """
        The partner for this relay session has been found
        """

    @_machine.input()
    def connection_lost(self):
        """
        Our transport has failed.
        """

    @_machine.input()
    def partner_connection_lost(self):
        """
        Our partner's transport has failed.
        """

    @_machine.input()
    def got_bytes(self, data):
        """
        Some bytes have arrived (that aren't part of the handshake)
        """

    @_machine.output()
    def _remember_client(self, client):
        self._client = client

    # note that there is no corresponding "_forget_client" because we
    # may still want to access it after it is gone .. for example, to
    # get the .started_time for logging purposes

    @_machine.output()
    def _register_token(self, token):
        return self._real_register_token_for_side(token, None)

    @_machine.output()
    def _register_token_for_side(self, token, side):
        return self._real_register_token_for_side(token, side)

    @_machine.output()
    def _unregister(self):
        """
        remove us from the thing that remembers tokens and sides
        """
        return self._pending_requests.unregister(self._token, self._side, self)

    @_machine.output()
    def _send_bad(self):
        self._mood = "errory"
        self._client.send(b"bad handshake\n")
        if self._client.factory.log_requests:
            log.msg("transit handshake failure")

    @_machine.output()
    def _send_ok(self):
        self._client.send(b"ok\n")

    @_machine.output()
    def _send_impatient(self):
        self._client.send(b"impatient\n")
        if self._client.factory.log_requests:
            log.msg("transit impatience failure")

    @_machine.output()
    def _count_bytes(self, data):
        self._total_sent += len(data)

    @_machine.output()
    def _send_to_partner(self, data):
        self._buddy._client.send(data)

    @_machine.output()
    def _connect_partner(self, client):
        self._buddy = client
        self._client.connect_partner(client)

    @_machine.output()
    def _disconnect(self):
        self._client.disconnect()

    @_machine.output()
    def _disconnect_partner(self):
        self._client.disconnect_partner()

    # some outputs to record "usage" information ..
    @_machine.output()
    def _record_usage(self):
        if self._mood == "jilted":
            if self._buddy and self._buddy._mood == "happy":
                return
        self._usage.record(
            started=self._client.started_time,
            buddy_started=self._buddy._client.started_time if self._buddy is not None else None,
            result=self._mood,
            bytes_sent=self._total_sent,
            buddy_bytes=self._buddy._total_sent if self._buddy is not None else None
        )

    # some outputs to record the "mood" ..
    @_machine.output()
    def _mood_happy(self):
        self._mood = "happy"

    @_machine.output()
    def _mood_lonely(self):
        self._mood = "lonely"

    @_machine.output()
    def _mood_redundant(self):
        self._mood = "redundant"

    @_machine.output()
    def _mood_impatient(self):
        self._mood = "impatient"

    @_machine.output()
    def _mood_errory(self):
        self._mood = "errory"

    @_machine.output()
    def _mood_happy_if_first(self):
        """
        We disconnected first so we're only happy if we also connected
        first.
        """
        if self._first:
            self._mood = "happy"
        else:
            self._mood = "jilted"

    def _real_register_token_for_side(self, token, side):
        """
        A client has connected and sent a valid version 1 or version 2
        handshake. If the former, `side` will be None.

        In either case, we remember the tokens and register
        ourselves. This might result in 'got_partner' notifications to
        two state-machines if this is the second side for a given token.

        :param bytes token: the token
        :param bytes side: The side token (or None)
        """
        self._token = token
        self._side = side
        self._first = self._pending_requests.register(token, side, self)

    @_machine.state(initial=True)
    def listening(self):
        """
        Initial state, awaiting connection.
        """

    @_machine.state()
    def wait_relay(self):
        """
        Waiting for a 'relay' message
        """

    @_machine.state()
    def wait_partner(self):
        """
        Waiting for our partner to connect
        """

    @_machine.state()
    def relaying(self):
        """
        Relaying bytes to our partner
        """

    @_machine.state()
    def done(self):
        """
        Terminal state
        """

    listening.upon(
        connection_made,
        enter=wait_relay,
        outputs=[_remember_client],
    )
    listening.upon(
        connection_lost,
        enter=done,
        outputs=[_mood_errory],
    )

    wait_relay.upon(
        please_relay,
        enter=wait_partner,
        outputs=[_mood_lonely, _register_token],
    )
    wait_relay.upon(
        please_relay_for_side,
        enter=wait_partner,
        outputs=[_mood_lonely, _register_token_for_side],
    )
    wait_relay.upon(
        bad_token,
        enter=done,
        outputs=[_mood_errory, _send_bad, _disconnect, _record_usage],
    )
    wait_relay.upon(
        got_bytes,
        enter=done,
        outputs=[_count_bytes, _mood_errory, _disconnect, _record_usage],
    )
    wait_relay.upon(
        connection_lost,
        enter=done,
        outputs=[_disconnect, _record_usage],
    )

    wait_partner.upon(
        got_partner,
        enter=relaying,
        outputs=[_mood_happy, _send_ok, _connect_partner],
    )
    wait_partner.upon(
        connection_lost,
        enter=done,
        outputs=[_mood_lonely, _unregister, _record_usage],
    )
    wait_partner.upon(
        got_bytes,
        enter=done,
        outputs=[_mood_impatient, _send_impatient, _disconnect, _unregister, _record_usage],
    )
    wait_partner.upon(
        partner_connection_lost,
        enter=done,
        outputs=[_mood_redundant, _disconnect, _record_usage],
    )

    relaying.upon(
        got_bytes,
        enter=relaying,
        outputs=[_count_bytes, _send_to_partner],
    )
    relaying.upon(
        connection_lost,
        enter=done,
        outputs=[_mood_happy_if_first, _disconnect_partner, _unregister, _record_usage],
    )

    done.upon(
        connection_lost,
        enter=done,
        outputs=[],
    )
    done.upon(
        partner_connection_lost,
        enter=done,
        outputs=[],
    )

    # uncomment to turn on state-machine tracing
    # set_trace_function = _machine._setTrace
