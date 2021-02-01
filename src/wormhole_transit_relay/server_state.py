from collections import defaultdict

import automat
from zope.interface import (
    Interface,
    implementer,
)


class ITransitClient(Interface):
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


@implementer(ITransitClient)
class TestClient(object):
    _partner = None
    _data = b""

    def send_to_partner(self, data):
        print("{} GOT:{}".format(id(self), repr(data)))
        if self._partner:
            self._partner._client.send(data)

    def send(self, data):
        print("{} SEND:{}".format(id(self), repr(data)))
        self._data += data

    def disconnect(self):
        print("disconnect")

    def connect_partner(self, other):
        print("connect_partner: {} <--> {}".format(id(self), id(other)))
        assert self._partner is None, "double partner"
        self._partner = other

    def disconnect_partner(self):
        assert self._partner is not None, "no partner"
        print("disconnect_partner: {}".format(id(self._partner)))


class ActiveConnections(object):
    """
    Tracks active connections. A connection is 'active' when both
    sides have shown up and they are glued together.
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
    Tracks the tokens we have received from client connections and
    maps them to their partner connections for requests that haven't
    yet been 'glued together' (that is, one side hasn't yet shown up).
    """

    def __init__(self, active_connections):
        self._requests = defaultdict(set) # token -> set((side, TransitConnection))
        self._active = active_connections

    def unregister(self, token, side, tc):
        if token in self._requests:
            self._requests[token].discard((side, tc))
        self._active.unregister(tc)

    def register_token(self, token, new_side, new_tc):
        """
        A client has connected and successfully offered a token (and
        optional 'side' token). If this is the first one for this
        token, we merely remember it. If it is the second side for
        this token we connect them together.

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
                # FIXME: debug-log this
                # print("transit relay 2: %s" % new_tc.get_token())

                # drop and stop tracking the rest
                potentials.remove(old)
                for (_, leftover_tc) in potentials.copy():
                    # Don't record this as errory. It's just a spare connection
                    # from the same side as a connection that got used. This
                    # can happen if the connection hint contains multiple
                    # addresses (we don't currently support those, but it'd
                    # probably be useful in the future).
                    leftover_tc.disconnect_redundant()
                self._requests.pop(token, None)

                # glue the two ends together
                self._active.register(new_tc, old_tc)
                new_tc.got_partner(old_tc)
                old_tc.got_partner(new_tc)
                return False

        # FIXME: debug-log this
        # print("transit relay 1: %s" % new_tc.get_token())
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

    def __init__(self, pending_requests):
        self._pending_requests = pending_requests

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

    def get_mood(self):
        """
        :returns str: description of the current 'mood' of the connection
        """
        return self._mood

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

    @_machine.output()
    def _send_ok(self):
        self._client.send(b"ok\n")

    @_machine.output()
    def _send_impatient(self):
        self._client.send(b"impatient\n")

    @_machine.output()
    def _count_bytes(self, data):
        self._total_sent += len(data)

    @_machine.output()
    def _send(self, data):
        self._client.send(data)

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

    # some outputs to record the "mood" ..
    @_machine.output()
    def _mood_happy(self):
        self._mood = "happy"

    @_machine.output()
    def _mood_lonely(self):
        self._mood = "lonely"

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

    @_machine.output()
    def _mood_happy_if_second(self):
        """
        We disconnected second so we're only happy if we also connected
        second.
        """
        if self._first:
            self._mood = "jilted"
        else:
            self._mood = "happy"

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
        self._first = self._pending_requests.register_token(token, side, self)

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
        outputs=[_mood_errory, _send_bad, _disconnect],
    )
    wait_relay.upon(
        got_bytes,
        enter=done,
        outputs=[_count_bytes, _mood_errory, _disconnect],
    )
    wait_relay.upon(
        connection_lost,
        enter=done,
        outputs=[_disconnect],
    )

    wait_partner.upon(
        got_partner,
        enter=relaying,
        outputs=[_mood_happy, _send_ok, _connect_partner],
    )
    wait_partner.upon(
        connection_lost,
        enter=done,
        outputs=[_mood_lonely, _unregister],
    )
    wait_partner.upon(
        got_bytes,
        enter=done,
        outputs=[_mood_impatient, _send_impatient, _disconnect, _unregister],
    )

    relaying.upon(
        got_bytes,
        enter=relaying,
        outputs=[_send_to_partner],
    )
    relaying.upon(
        connection_lost,
        enter=done,
        outputs=[_mood_happy_if_first, _disconnect_partner, _unregister],
    )
    relaying.upon(
        partner_connection_lost,
        enter=done,
        outputs=[_mood_happy_if_second, _disconnect, _unregister],
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




# actions:
# - send("ok")
# - send("bad handshake")
# - disconnect
# - ...

if __name__ == "__main__":
    active = ActiveConnections()
    pending = PendingRequests(active)

    server0 = TransitServerState(pending)
    client0 =  TestClient()
    server1 = TransitServerState(pending)
    client1 =  TestClient()
    server0.connection_made(client0)
    server0.please_relay(b"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    # this would be an error, because our partner hasn't shown up yet
    # print(server0.got_bytes(b"asdf"))

    print("about to relay client1")
    server1.connection_made(client1)
    server1.please_relay(b"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    print("done")

    # XXX the PendingRequests stuff should do this, going "by hand" for now
#    server0.got_partner(client1)
#    server1.got_partner(client0)

    # should be connected now
    server0.got_bytes(b"asdf")
    # client1 should receive b"asdf"

    server0.connection_lost()
    print("----[ received data on both sides ]----")
    print("client0:{}".format(repr(client0._data)))
    print("client1:{}".format(repr(client1._data)))
