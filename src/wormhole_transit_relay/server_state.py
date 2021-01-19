
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

    def disconnect(reason):
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
            self._partner.send(data)

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


class PendingRequests(object):
    """
    Tracks the tokens we have received from client connections and
    maps them to their partner connections
    """

    def register_token(self, *args):
        """
        """


class TransitServer(object):
    """
    Encapsulates the state-machine of the server side of a transit
    relay connection.

    Once the protocol has been told to relay (or to relay for a side)
    it starts passing all received bytes to the other side until it
    closes.
    """

    _machine = automat.MethodicalMachine()
    _client = None

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
        pass

    @_machine.input()
    def please_relay_for_side(self, token, side):
        pass

    @_machine.input()
    def bad_token(self):
        """
        A bad token / relay line was received
        """

    @_machine.input()
    def got_partner(self, client):
        """
        The partner for this relay session has been found
        """

    @_machine.input()
    def connection_lost(self):
        pass

    @_machine.input()
    def partner_connection_lost(self):
        pass

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

    @_machine.output()
    def _send_bad(self):
        self._client.send("bad handshake\n")

    @_machine.output()
    def _send_ok(self):
        self._client.send("ok\n")

    @_machine.output()
    def _send(self, data):
        self._client.send(data)

    @_machine.output()
    def _send_to_partner(self, data):
        self._client.send_to_partner(data)

    @_machine.output()
    def _connect_partner(self, client):
        self._client.connect_partner(client)

    @_machine.output()
    def _disconnect(self):
        self._client.disconnect()

    @_machine.output()
    def _disconnect_partner(self):
        self._client.disconnect_partner()

    def _real_register_token_for_side(self, token, side):
        """
        basically, _got_handshake() + connection_got_token() from "real"
        code ...and if this is the "second" side, hook them up and
        pass .got_partner() input to both
        """

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
        outputs=[_register_token],
    )
    wait_relay.upon(
        please_relay_for_side,
        enter=wait_partner,
        outputs=[_register_token_for_side],
    )
    wait_relay.upon(
        bad_token,
        enter=done,
        outputs=[_send_bad, _disconnect],
    )
    wait_relay.upon(
        connection_lost,
        enter=done,
        outputs=[_disconnect],
    )

    wait_partner.upon(
        got_partner,
        enter=relaying,
        outputs=[_send_ok, _connect_partner],
    )
    wait_partner.upon(
        connection_lost,
        enter=done,
        outputs=[_unregister],
    )

    relaying.upon(
        got_bytes,
        enter=relaying,
        outputs=[_send_to_partner],
    )
    relaying.upon(
        connection_lost,
        enter=done,
        outputs=[_disconnect_partner, _unregister],
    )
    relaying.upon(
        partner_connection_lost,
        enter=done,
        outputs=[_disconnect, _unregister],
    )




# actions:
# - send("ok")
# - send("bad handshake")
# - disconnect
# - ...

if __name__ == "__main__":
    server0 = TransitServer()
    client0 =  TestClient()
    server1 = TransitServer()
    client1 =  TestClient()
    server0.connection_made(client0)
    server0.please_relay(b"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    # this would be an error, because our partner hasn't shown up yet
    # print(server0.got_bytes(b"asdf"))

    server1.connection_made(client1)
    server1.please_relay(b"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    # XXX the PendingRequests stuff should do this, going "by hand" for now
    server0.got_partner(client1)
    server1.got_partner(client0)

    # should be connected now
    server0.got_bytes(b"asdf")
    # client1 should receive b"asdf"

    server0.connection_lost()
    print("----[ received data on both sides ]----")
    print("client0:{}".format(repr(client0._data)))
    print("client1:{}".format(repr(client1._data)))
