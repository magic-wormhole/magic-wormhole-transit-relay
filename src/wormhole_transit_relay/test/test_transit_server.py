from binascii import hexlify
from twisted.trial import unittest
from twisted.test import iosim
from autobahn.twisted.websocket import (
    WebSocketServerFactory,
    WebSocketClientFactory,
    WebSocketClientProtocol,
)
from autobahn.twisted.testing import (
    create_pumper,
    MemoryReactorClockResolver,
)
from autobahn.exception import Disconnected
from zope.interface import implementer
from .common import (
    ServerBase,
    IRelayTestClient,
)
from ..usage import (
    MemoryUsageRecorder,
    blur_size,
)
from ..transit_server import (
    WebSocketTransitConnection,
    TransitServerState,
)


def handshake(token, side=None):
    hs = b"please relay " + hexlify(token)
    if side is not None:
        hs += b" for side " + hexlify(side)
    hs += b"\n"
    return hs

class _Transit:
    def count(self):
        return sum([
            len(potentials)
            for potentials
            in self._transit_server.pending_requests._requests.values()
        ])

    def test_blur_size(self):
        self.failUnlessEqual(blur_size(0), 0)
        self.failUnlessEqual(blur_size(1), 10e3)
        self.failUnlessEqual(blur_size(10e3), 10e3)
        self.failUnlessEqual(blur_size(10e3+1), 20e3)
        self.failUnlessEqual(blur_size(15e3), 20e3)
        self.failUnlessEqual(blur_size(20e3), 20e3)
        self.failUnlessEqual(blur_size(1e6), 1e6)
        self.failUnlessEqual(blur_size(1e6+1), 2e6)
        self.failUnlessEqual(blur_size(1.5e6), 2e6)
        self.failUnlessEqual(blur_size(2e6), 2e6)
        self.failUnlessEqual(blur_size(900e6), 900e6)
        self.failUnlessEqual(blur_size(1000e6), 1000e6)
        self.failUnlessEqual(blur_size(1050e6), 1100e6)
        self.failUnlessEqual(blur_size(1100e6), 1100e6)
        self.failUnlessEqual(blur_size(1150e6), 1200e6)

    def test_register(self):
        p1 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8

        p1.send(handshake(token1, side1))
        self.flush()
        self.assertEqual(self.count(), 1)

        p1.disconnect()
        self.flush()
        self.assertEqual(self.count(), 0)

        # the token should be removed too
        self.assertEqual(len(self._transit_server.pending_requests._requests), 0)

    def test_both_unsided(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()

        token1 = b"\x00"*32
        p1.send(handshake(token1, side=None))
        self.flush()
        p2.send(handshake(token1, side=None))
        self.flush()

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        self.assertEqual(p1.get_received_data(), exp)
        self.assertEqual(p2.get_received_data(), exp)

        p1.reset_received_data()
        p2.reset_received_data()

        s1 = b"data1"
        p1.send(s1)
        self.flush()
        self.assertEqual(p2.get_received_data(), s1)

        p1.disconnect()
        self.flush()

    def test_sided_unsided(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        p1.send(handshake(token1, side=side1))
        self.flush()
        p2.send(handshake(token1, side=None))
        self.flush()

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        self.assertEqual(p1.get_received_data(), exp)
        self.assertEqual(p2.get_received_data(), exp)

        p1.reset_received_data()
        p2.reset_received_data()

        # all data they sent after the handshake should be given to us
        s1 = b"data1"
        p1.send(s1)
        self.flush()
        self.assertEqual(p2.get_received_data(), s1)

        p1.disconnect()
        self.flush()

    def test_unsided_sided(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        p1.send(handshake(token1, side=None))
        p2.send(handshake(token1, side=side1))
        self.flush()

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        self.assertEqual(p1.get_received_data(), exp)
        self.assertEqual(p2.get_received_data(), exp)

        p1.reset_received_data()
        p2.reset_received_data()

        # all data they sent after the handshake should be given to us
        s1 = b"data1"
        p1.send(s1)
        self.flush()
        self.assertEqual(p2.get_received_data(), s1)

        p1.disconnect()
        p2.disconnect()

    def test_both_sided(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        side2 = b"\x02"*8
        p1.send(handshake(token1, side=side1))
        self.flush()
        p2.send(handshake(token1, side=side2))
        self.flush()

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        self.assertEqual(p1.get_received_data(), exp)
        self.assertEqual(p2.get_received_data(), exp)

        p1.reset_received_data()
        p2.reset_received_data()

        # all data they sent after the handshake should be given to us
        s1 = b"data1"
        p1.send(s1)
        self.flush()
        self.assertEqual(p2.get_received_data(), s1)

        p1.disconnect()
        p2.disconnect()

    def test_ignore_same_side(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()
        p3 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8

        p1.send(handshake(token1, side=side1))
        self.flush()
        self.assertEqual(self.count(), 1)

        p2.send(handshake(token1, side=side1))
        self.flush()
        self.flush()
        self.assertEqual(self.count(), 2) # same-side connections don't match

        # when the second side arrives, the spare first connection should be
        # closed
        side2 = b"\x02"*8
        p3.send(handshake(token1, side=side2))
        self.flush()
        self.assertEqual(self.count(), 0)
        self.assertEqual(len(self._transit_server.pending_requests._requests), 0)
        self.assertEqual(len(self._transit_server.active_connections._connections), 2)
        # That will trigger a disconnect on exactly one of (p1 or p2).
        # The other connection should still be connected
        self.assertEqual(sum([int(t.connected) for t in [p1, p2]]), 1)

        p1.disconnect()
        p2.disconnect()
        p3.disconnect()

    def test_bad_handshake_old(self):
        p1 = self.new_protocol()

        token1 = b"\x00"*32
        p1.send(b"please DELAY " + hexlify(token1) + b"\n")
        self.flush()

        exp = b"bad handshake\n"
        self.assertEqual(p1.get_received_data(), exp)
        p1.disconnect()

    def test_bad_handshake_old_slow(self):
        p1 = self.new_protocol()

        p1.send(b"please DELAY ")
        self.flush()
        # As in test_impatience_new_slow, the current state machine has code
        # that can only be reached if we insert a stall here, so dataReceived
        # gets called twice. Hopefully we can delete this test once
        # dataReceived is refactored to remove that state.

        token1 = b"\x00"*32
        # the server waits for the exact number of bytes in the expected
        # handshake message. to trigger "bad handshake", we must match.
        p1.send(hexlify(token1) + b"\n")
        self.flush()

        exp = b"bad handshake\n"
        self.assertEqual(p1.get_received_data(), exp)

        p1.disconnect()

    def test_bad_handshake_new(self):
        p1 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        # the server waits for the exact number of bytes in the expected
        # handshake message. to trigger "bad handshake", we must match.
        p1.send(b"please DELAY " + hexlify(token1) +
                b" for side " + hexlify(side1) + b"\n")
        self.flush()

        exp = b"bad handshake\n"
        self.assertEqual(p1.get_received_data(), exp)

        p1.disconnect()

    def test_binary_handshake(self):
        p1 = self.new_protocol()

        binary_bad_handshake = b"\x00\x01\xe0\x0f\n\xff"
        # the embedded \n makes the server trigger early, before the full
        # expected handshake length has arrived. A non-wormhole client
        # writing non-ascii junk to the transit port used to trigger a
        # UnicodeDecodeError when it tried to coerce the incoming handshake
        # to unicode, due to the ("\n" in buf) check. This was fixed to use
        # (b"\n" in buf). This exercises the old failure.
        p1.send(binary_bad_handshake)
        self.flush()

        exp = b"bad handshake\n"
        self.assertEqual(p1.get_received_data(), exp)

        p1.disconnect()

    def test_impatience_old(self):
        p1 = self.new_protocol()

        token1 = b"\x00"*32
        # sending too many bytes is impatience.
        p1.send(b"please relay " + hexlify(token1))
        p1.send(b"\nNOWNOWNOW")
        self.flush()

        exp = b"impatient\n"
        self.assertEqual(p1.get_received_data(), exp)

        p1.disconnect()

    def test_impatience_new(self):
        p1 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        # sending too many bytes is impatience.
        p1.send(b"please relay " + hexlify(token1) +
                b" for side " + hexlify(side1))
        p1.send(b"\nNOWNOWNOW")
        self.flush()

        exp = b"impatient\n"
        self.assertEqual(p1.get_received_data(), exp)

        p1.disconnect()

    def test_impatience_new_slow(self):
        p1 = self.new_protocol()
        # For full coverage, we need dataReceived to see a particular framing
        # of these two pieces of data, and ITCPTransport doesn't have flush()
        # (which probably wouldn't work anyways). For now, force a 100ms
        # stall between the two writes. I tried setTcpNoDelay(True) but it
        # didn't seem to help without the stall. The long-term fix is to
        # rewrite dataReceived() to remove the multiple "impatient"
        # codepaths, deleting the particular clause that this test exercises,
        # then remove this test.

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        # sending too many bytes is impatience.
        p1.send(b"please relay " + hexlify(token1) +
                b" for side " + hexlify(side1) + b"\n")
        self.flush()

        p1.send(b"NOWNOWNOW")
        self.flush()

        exp = b"impatient\n"
        self.assertEqual(p1.get_received_data(), exp)

        p1.disconnect()

    def test_short_handshake(self):
        p1 = self.new_protocol()
        # hang up before sending a complete handshake
        p1.send(b"short")
        self.flush()
        p1.disconnect()

    def test_empty_handshake(self):
        p1 = self.new_protocol()
        # hang up before sending anything
        p1.disconnect()


class TransitWithLogs(_Transit, ServerBase, unittest.TestCase):
    log_requests = True

    def new_protocol(self):
        return self.new_protocol_tcp()


class TransitWithoutLogs(_Transit, ServerBase, unittest.TestCase):
    log_requests = False

    def new_protocol(self):
        return self.new_protocol_tcp()


def _new_protocol_ws(transit_server, log_requests):
    """
    Internal helper for test-suites that need to provide WebSocket
    client/server pairs.

    :returns: a 2-tuple: (iosim.IOPump, protocol)
    """
    ws_factory = WebSocketServerFactory("ws://localhost:4002")
    ws_factory.protocol = WebSocketTransitConnection
    ws_factory.transit = transit_server
    ws_factory.log_requests = log_requests
    ws_protocol = ws_factory.buildProtocol(('127.0.0.1', 0))

    @implementer(IRelayTestClient)
    class TransitWebSocketClientProtocol(WebSocketClientProtocol):
        _received = b""
        connected = False

        def connectionMade(self):
            self.connected = True
            return super(TransitWebSocketClientProtocol, self).connectionMade()

        def connectionLost(self, reason):
            self.connected = False
            return super(TransitWebSocketClientProtocol, self).connectionLost(reason)

        def onMessage(self, data, isBinary):
            self._received = self._received + data

        def send(self, data):
            self.sendMessage(data, True)

        def get_received_data(self):
            return self._received

        def reset_received_data(self):
            self._received = b""

        def disconnect(self):
            self.sendClose(1000, True)

    client_factory = WebSocketClientFactory()
    client_factory.protocol = TransitWebSocketClientProtocol
    client_protocol = client_factory.buildProtocol(('127.0.0.1', 31337))
    client_protocol.disconnect = client_protocol.dropConnection

    pump = iosim.connect(
        ws_protocol,
        iosim.makeFakeServer(ws_protocol),
        client_protocol,
        iosim.makeFakeClient(client_protocol),
    )
    return pump, client_protocol



class TransitWebSockets(_Transit, ServerBase, unittest.TestCase):

    def new_protocol(self):
        return self.new_protocol_ws()

    def new_protocol_ws(self):
        pump, proto = _new_protocol_ws(self._transit_server, self.log_requests)
        self._pumps.append(pump)
        return proto

    def test_websocket_to_tcp(self):
        """
        One client is WebSocket and one is TCP
        """
        p1 = self.new_protocol_ws()
        p2 = self.new_protocol_tcp()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        side2 = b"\x02"*8
        p1.send(handshake(token1, side=side1))
        self.flush()
        p2.send(handshake(token1, side=side2))
        self.flush()

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        self.assertEqual(p1.get_received_data(), exp)
        self.assertEqual(p2.get_received_data(), exp)

        p1.reset_received_data()
        p2.reset_received_data()

        # all data they sent after the handshake should be given to us
        s1 = b"data1"
        p1.send(s1)
        self.flush()
        self.assertEqual(p2.get_received_data(), s1)

        p1.disconnect()
        p2.disconnect()
        self.flush()

    def test_bad_handshake_old_slow(self):
        """
        This test only makes sense for TCP
        """

    def test_send_closed_partner(self):
        """
        Sending data to a closed partner causes an error that propogates
        to the sender.
        """
        p1 = self.new_protocol()
        p2 = self.new_protocol()

        # set up a successful connection
        token = b"a" * 32
        p1.send(handshake(token))
        p2.send(handshake(token))
        self.flush()

        # p2 loses connection, then p1 sends a message
        p2.transport.loseConnection()
        self.flush()

        # at this point, p1 learns that p2 is disconnected (because it
        # tried to relay "a message" but failed)

        # try to send more (our partner p2 is gone now though so it
        # should be an immediate error)
        with self.assertRaises(Disconnected):
            p1.send(b"more message")
            self.flush()


class Usage(ServerBase, unittest.TestCase):
    log_requests = True

    def setUp(self):
        super(Usage, self).setUp()
        self._usage = MemoryUsageRecorder()
        self._transit_server.usage.add_backend(self._usage)

    def new_protocol(self):
        return self.new_protocol_tcp()

    def test_empty(self):
        p1 = self.new_protocol()
        # hang up before sending anything
        p1.disconnect()
        self.flush()

        # that will log the "empty" usage event
        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual(self._usage.events[0]["mood"], "empty", self._usage)

    def test_short(self):
        # Note: this test only runs on TCP clients because WebSockets
        # already does framing (so it's either "a bad handshake" or
        # there's no handshake at all yet .. you can't have a "short"
        # one).
        p1 = self.new_protocol()
        # hang up before sending a complete handshake
        p1.send(b"short")
        p1.disconnect()
        self.flush()

        # that will log the "empty" usage event
        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual("empty", self._usage.events[0]["mood"])

    def test_errory(self):
        p1 = self.new_protocol()

        p1.send(b"this is a very bad handshake\n")
        self.flush()
        # that will log the "errory" usage event, then drop the connection
        p1.disconnect()
        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual(self._usage.events[0]["mood"], "errory", self._usage)

    def test_lonely(self):
        p1 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        p1.send(handshake(token1, side=side1))
        self.flush()
        # now we disconnect before the peer connects
        p1.disconnect()
        self.flush()

        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual(self._usage.events[0]["mood"], "lonely", self._usage)
        self.assertIdentical(self._usage.events[0]["waiting_time"], None)

    def test_one_happy_one_jilted(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        side2 = b"\x02"*8
        p1.send(handshake(token1, side=side1))
        self.flush()
        p2.send(handshake(token1, side=side2))
        self.flush()

        self.assertEqual(self._usage.events, []) # no events yet

        p1.send(b"\x00" * 13)
        self.flush()
        p2.send(b"\xff" * 7)
        self.flush()

        p1.disconnect()
        self.flush()

        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual(self._usage.events[0]["mood"], "happy", self._usage)
        self.assertEqual(self._usage.events[0]["total_bytes"], 20)
        self.assertNotIdentical(self._usage.events[0]["waiting_time"], None)

    def test_redundant(self):
        p1a = self.new_protocol()
        p1b = self.new_protocol()
        p1c = self.new_protocol()
        p2 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        side2 = b"\x02"*8
        p1a.send(handshake(token1, side=side1))
        self.flush()
        p1b.send(handshake(token1, side=side1))
        self.flush()

        # connect and disconnect a third client (for side1) to exercise the
        # code that removes a pending connection without removing the entire
        # token
        p1c.send(handshake(token1, side=side1))
        p1c.disconnect()
        self.flush()

        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual(self._usage.events[0]["mood"], "lonely")

        p2.send(handshake(token1, side=side2))
        self.flush()
        self.assertEqual(len(self._transit_server.pending_requests._requests), 0)
        self.assertEqual(len(self._usage.events), 2, self._usage)
        self.assertEqual(self._usage.events[1]["mood"], "redundant")

        # one of the these is unecessary, but probably harmless
        p1a.disconnect()
        p1b.disconnect()
        self.flush()
        self.assertEqual(len(self._usage.events), 3, self._usage)
        self.assertEqual(self._usage.events[2]["mood"], "happy")


class UsageWebSockets(Usage):
    """
    All the tests of 'Usage' except with a WebSocket (instead of TCP)
    transport.

    This overrides ServerBase.new_protocol to achieve this. It might
    be nicer to parametrize these tests in a way that doesn't use
    inheritance .. but all the support etc classes are set up that way
    already.
    """

    def setUp(self):
        super(UsageWebSockets, self).setUp()
        self._pump = create_pumper()
        self._reactor = MemoryReactorClockResolver()
        return self._pump.start()

    def tearDown(self):
        return self._pump.stop()

    def new_protocol(self):
        return self.new_protocol_ws()

    def new_protocol_ws(self):
        pump, proto = _new_protocol_ws(self._transit_server, self.log_requests)
        self._pumps.append(pump)
        return proto

    def test_short(self):
        """
        This test essentially just tests the framing of the line-oriented
        TCP protocol; it doesnt' make sense for the WebSockets case
        because WS handles frameing: you either sent a 'bad handshake'
        because it is semantically invalid or no handshake (yet).
        """

    def test_send_non_binary_message(self):
        """
        A non-binary WebSocket message is an error
        """
        ws_factory = WebSocketServerFactory("ws://localhost:4002")
        ws_factory.protocol = WebSocketTransitConnection
        ws_protocol = ws_factory.buildProtocol(('127.0.0.1', 0))
        with self.assertRaises(ValueError):
            ws_protocol.onMessage(u"foo", isBinary=False)


class State(unittest.TestCase):
    """
    Tests related to server_state.TransitServerState
    """

    def setUp(self):
        self.state = TransitServerState(None, None)

    def test_empty_token(self):
        self.assertEqual(
            "-",
            self.state.get_token(),
        )
