from __future__ import print_function, unicode_literals
from binascii import hexlify
from twisted.trial import unittest
from twisted.internet import protocol, reactor, defer
from twisted.internet.endpoints import clientFromString, connectProtocol
from .common import ServerBase
from .. import transit_server

class Accumulator(protocol.Protocol):
    def __init__(self):
        self.data = b""
        self.count = 0
        self._wait = None
        self._disconnect = defer.Deferred()
    def waitForBytes(self, more):
        assert self._wait is None
        self.count = more
        self._wait = defer.Deferred()
        self._check_done()
        return self._wait
    def dataReceived(self, data):
        self.data = self.data + data
        self._check_done()
    def _check_done(self):
        if self._wait and len(self.data) >= self.count:
            d = self._wait
            self._wait = None
            d.callback(self)
    def connectionLost(self, why):
        if self._wait:
            self._wait.errback(RuntimeError("closed"))
        self._disconnect.callback(None)

def wait():
    d = defer.Deferred()
    reactor.callLater(0.001, d.callback, None)
    return d

class _Transit:
    def test_blur_size(self):
        blur = transit_server.blur_size
        self.failUnlessEqual(blur(0), 0)
        self.failUnlessEqual(blur(1), 10e3)
        self.failUnlessEqual(blur(10e3), 10e3)
        self.failUnlessEqual(blur(10e3+1), 20e3)
        self.failUnlessEqual(blur(15e3), 20e3)
        self.failUnlessEqual(blur(20e3), 20e3)
        self.failUnlessEqual(blur(1e6), 1e6)
        self.failUnlessEqual(blur(1e6+1), 2e6)
        self.failUnlessEqual(blur(1.5e6), 2e6)
        self.failUnlessEqual(blur(2e6), 2e6)
        self.failUnlessEqual(blur(900e6), 900e6)
        self.failUnlessEqual(blur(1000e6), 1000e6)
        self.failUnlessEqual(blur(1050e6), 1100e6)
        self.failUnlessEqual(blur(1100e6), 1100e6)
        self.failUnlessEqual(blur(1150e6), 1200e6)

    @defer.inlineCallbacks
    def test_register(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        a1.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side1) + b"\n")

        # let that arrive
        while self.count() == 0:
            yield wait()
        self.assertEqual(self.count(), 1)

        a1.transport.loseConnection()

        # let that get removed
        while self.count() > 0:
            yield wait()
        self.assertEqual(self.count(), 0)

        # the token should be removed too
        self.assertEqual(len(self._transit_server._pending_requests), 0)

    @defer.inlineCallbacks
    def test_both_unsided(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())
        a2 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        a1.transport.write(b"please relay " + hexlify(token1) + b"\n")
        a2.transport.write(b"please relay " + hexlify(token1) + b"\n")

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        yield a1.waitForBytes(len(exp))
        self.assertEqual(a1.data, exp)
        s1 = b"data1"
        a1.transport.write(s1)

        exp = b"ok\n"
        yield a2.waitForBytes(len(exp))
        self.assertEqual(a2.data, exp)

        # all data they sent after the handshake should be given to us
        exp = b"ok\n"+s1
        yield a2.waitForBytes(len(exp))
        self.assertEqual(a2.data, exp)

        a1.transport.loseConnection()
        a2.transport.loseConnection()

    @defer.inlineCallbacks
    def test_sided_unsided(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())
        a2 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        a1.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side1) + b"\n")
        a2.transport.write(b"please relay " + hexlify(token1) + b"\n")

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        yield a1.waitForBytes(len(exp))
        self.assertEqual(a1.data, exp)
        s1 = b"data1"
        a1.transport.write(s1)

        exp = b"ok\n"
        yield a2.waitForBytes(len(exp))
        self.assertEqual(a2.data, exp)

        # all data they sent after the handshake should be given to us
        exp = b"ok\n"+s1
        yield a2.waitForBytes(len(exp))
        self.assertEqual(a2.data, exp)

        a1.transport.loseConnection()
        a2.transport.loseConnection()

    @defer.inlineCallbacks
    def test_unsided_sided(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())
        a2 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        a1.transport.write(b"please relay " + hexlify(token1) + b"\n")
        a2.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side1) + b"\n")

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        yield a1.waitForBytes(len(exp))
        self.assertEqual(a1.data, exp)
        s1 = b"data1"
        a1.transport.write(s1)

        exp = b"ok\n"
        yield a2.waitForBytes(len(exp))
        self.assertEqual(a2.data, exp)

        # all data they sent after the handshake should be given to us
        exp = b"ok\n"+s1
        yield a2.waitForBytes(len(exp))
        self.assertEqual(a2.data, exp)

        a1.transport.loseConnection()
        a2.transport.loseConnection()

    @defer.inlineCallbacks
    def test_both_sided(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())
        a2 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        side2 = b"\x02"*8
        a1.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side1) + b"\n")
        a2.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side2) + b"\n")

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        yield a1.waitForBytes(len(exp))
        self.assertEqual(a1.data, exp)
        s1 = b"data1"
        a1.transport.write(s1)

        exp = b"ok\n"
        yield a2.waitForBytes(len(exp))
        self.assertEqual(a2.data, exp)

        # all data they sent after the handshake should be given to us
        exp = b"ok\n"+s1
        yield a2.waitForBytes(len(exp))
        self.assertEqual(a2.data, exp)

        a1.transport.loseConnection()
        a2.transport.loseConnection()

    def count(self):
        return sum([len(potentials)
                    for potentials
                    in self._transit_server._pending_requests.values()])

    @defer.inlineCallbacks
    def test_ignore_same_side(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())
        a2 = yield connectProtocol(ep, Accumulator())
        a3 = yield connectProtocol(ep, Accumulator())
        disconnects = []
        a1._disconnect.addCallback(disconnects.append)
        a2._disconnect.addCallback(disconnects.append)

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        a1.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side1) + b"\n")
        # let that arrive
        while self.count() == 0:
            yield wait()
        a2.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side1) + b"\n")
        # let that arrive
        while self.count() == 1:
            yield wait()
        self.assertEqual(self.count(), 2) # same-side connections don't match

        # when the second side arrives, the spare first connection should be
        # closed
        side2 = b"\x02"*8
        a3.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side2) + b"\n")
        # let that arrive
        while self.count() != 0:
            yield wait()
        self.assertEqual(len(self._transit_server._pending_requests), 0)
        self.assertEqual(len(self._transit_server._active_connections), 2)
        # That will trigger a disconnect on exactly one of (a1 or a2). Wait
        # until our client notices it.
        while not disconnects:
            yield wait()
        # the other connection should still be connected
        self.assertEqual(sum([int(t.transport.connected) for t in [a1, a2]]), 1)

        a1.transport.loseConnection()
        a2.transport.loseConnection()
        a3.transport.loseConnection()

    @defer.inlineCallbacks
    def test_bad_handshake_old(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        # the server waits for the exact number of bytes in the expected
        # handshake message. to trigger "bad handshake", we must match.
        a1.transport.write(b"please DELAY " + hexlify(token1) + b"\n")

        exp = b"bad handshake\n"
        yield a1.waitForBytes(len(exp))
        self.assertEqual(a1.data, exp)

        a1.transport.loseConnection()

    @defer.inlineCallbacks
    def test_bad_handshake_old_slow(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())

        a1.transport.write(b"please DELAY ")
        # As in test_impatience_new_slow, the current state machine has code
        # that can only be reached if we insert a stall here, so dataReceived
        # gets called twice. Hopefully we can delete this test once
        # dataReceived is refactored to remove that state.
        d = defer.Deferred()
        reactor.callLater(0.1, d.callback, None)
        yield d

        token1 = b"\x00"*32
        # the server waits for the exact number of bytes in the expected
        # handshake message. to trigger "bad handshake", we must match.
        a1.transport.write(hexlify(token1) + b"\n")

        exp = b"bad handshake\n"
        yield a1.waitForBytes(len(exp))
        self.assertEqual(a1.data, exp)

        a1.transport.loseConnection()

    @defer.inlineCallbacks
    def test_bad_handshake_new(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        # the server waits for the exact number of bytes in the expected
        # handshake message. to trigger "bad handshake", we must match.
        a1.transport.write(b"please DELAY " + hexlify(token1) +
                           b" for side " + hexlify(side1) + b"\n")

        exp = b"bad handshake\n"
        yield a1.waitForBytes(len(exp))
        self.assertEqual(a1.data, exp)

        a1.transport.loseConnection()

    @defer.inlineCallbacks
    def test_binary_handshake(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())

        binary_bad_handshake = b"\x00\x01\xe0\x0f\n\xff"
        # the embedded \n makes the server trigger early, before the full
        # expected handshake length has arrived. A non-wormhole client
        # writing non-ascii junk to the transit port used to trigger a
        # UnicodeDecodeError when it tried to coerce the incoming handshake
        # to unicode, due to the ("\n" in buf) check. This was fixed to use
        # (b"\n" in buf). This exercises the old failure.
        a1.transport.write(binary_bad_handshake)

        exp = b"bad handshake\n"
        yield a1.waitForBytes(len(exp))
        self.assertEqual(a1.data, exp)

        a1.transport.loseConnection()

    @defer.inlineCallbacks
    def test_impatience_old(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        # sending too many bytes is impatience.
        a1.transport.write(b"please relay " + hexlify(token1) + b"\nNOWNOWNOW")

        exp = b"impatient\n"
        yield a1.waitForBytes(len(exp))
        self.assertEqual(a1.data, exp)

        a1.transport.loseConnection()

    @defer.inlineCallbacks
    def test_impatience_new(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        # sending too many bytes is impatience.
        a1.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side1) + b"\nNOWNOWNOW")

        exp = b"impatient\n"
        yield a1.waitForBytes(len(exp))
        self.assertEqual(a1.data, exp)

        a1.transport.loseConnection()

    @defer.inlineCallbacks
    def test_impatience_new_slow(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())
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
        a1.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side1) + b"\n")

        d = defer.Deferred()
        reactor.callLater(0.1, d.callback, None)
        yield d

        a1.transport.write(b"NOWNOWNOW")

        exp = b"impatient\n"
        yield a1.waitForBytes(len(exp))
        self.assertEqual(a1.data, exp)

        a1.transport.loseConnection()

class TransitWithLogs(_Transit, ServerBase, unittest.TestCase):
    log_requests = True

class TransitWithoutLogs(_Transit, ServerBase, unittest.TestCase):
    log_requests = False

class Usage(ServerBase, unittest.TestCase):
    @defer.inlineCallbacks
    def setUp(self):
        yield super(Usage, self).setUp()
        self._usage = []
        def record(started, result, total_bytes, total_time, waiting_time):
            self._usage.append((started, result, total_bytes,
                                total_time, waiting_time))
        self._transit_server.recordUsage = record

    @defer.inlineCallbacks
    def test_errory(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())

        a1.transport.write(b"this is a very bad handshake\n")
        # that will log the "errory" usage event, then drop the connection
        yield a1._disconnect
        self.assertEqual(len(self._usage), 1, self._usage)
        (started, result, total_bytes, total_time, waiting_time) = self._usage[0]
        self.assertEqual(result, "errory", self._usage)

    @defer.inlineCallbacks
    def test_lonely(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        a1.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side1) + b"\n")
        while not self._transit_server._pending_requests:
            yield wait() # wait for the server to see the connection
        # now we disconnect before the peer connects
        a1.transport.loseConnection()
        yield a1._disconnect
        while self._transit_server._pending_requests:
            yield wait() # wait for the server to see the disconnect too

        self.assertEqual(len(self._usage), 1, self._usage)
        (started, result, total_bytes, total_time, waiting_time) = self._usage[0]
        self.assertEqual(result, "lonely", self._usage)
        self.assertIdentical(waiting_time, None)

    @defer.inlineCallbacks
    def test_one_happy_one_jilted(self):
        ep = clientFromString(reactor, self.transit)
        a1 = yield connectProtocol(ep, Accumulator())
        a2 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        side2 = b"\x02"*8
        a1.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side1) + b"\n")
        while not self._transit_server._pending_requests:
            yield wait() # make sure a1 connects first
        a2.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side2) + b"\n")
        while not self._transit_server._active_connections:
            yield wait() # wait for the server to see the connection
        self.assertEqual(len(self._transit_server._pending_requests), 0)
        self.assertEqual(self._usage, []) # no events yet
        a1.transport.write(b"\x00" * 13)
        yield a2.waitForBytes(13)
        a2.transport.write(b"\xff" * 7)
        yield a1.waitForBytes(7)

        a1.transport.loseConnection()
        yield a1._disconnect
        while self._transit_server._active_connections:
            yield wait()
        yield a2._disconnect
        self.assertEqual(len(self._usage), 1, self._usage)
        (started, result, total_bytes, total_time, waiting_time) = self._usage[0]
        self.assertEqual(result, "happy", self._usage)
        self.assertEqual(total_bytes, 20)
        self.assertNotIdentical(waiting_time, None)

    @defer.inlineCallbacks
    def test_redundant(self):
        ep = clientFromString(reactor, self.transit)
        a1a = yield connectProtocol(ep, Accumulator())
        a1b = yield connectProtocol(ep, Accumulator())
        a1c = yield connectProtocol(ep, Accumulator())
        a2 = yield connectProtocol(ep, Accumulator())

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        side2 = b"\x02"*8
        a1a.transport.write(b"please relay " + hexlify(token1) +
                            b" for side " + hexlify(side1) + b"\n")
        def count_requests():
            return sum([len(v)
                        for v in self._transit_server._pending_requests.values()])
        while count_requests() < 1:
            yield wait()
        a1b.transport.write(b"please relay " + hexlify(token1) +
                            b" for side " + hexlify(side1) + b"\n")
        while count_requests() < 2:
            yield wait()

        # connect and disconnect a third client (for side1) to exercise the
        # code that removes a pending connection without removing the entire
        # token
        a1c.transport.write(b"please relay " + hexlify(token1) +
                            b" for side " + hexlify(side1) + b"\n")
        while count_requests() < 3:
            yield wait()
        a1c.transport.loseConnection()
        yield a1c._disconnect
        while count_requests() > 2:
            yield wait()
        self.assertEqual(len(self._usage), 1, self._usage)
        (started, result, total_bytes, total_time, waiting_time) = self._usage[0]
        self.assertEqual(result, "lonely", self._usage)

        a2.transport.write(b"please relay " + hexlify(token1) +
                           b" for side " + hexlify(side2) + b"\n")
        # this will claim one of (a1a, a1b), and close the other as redundant
        while not self._transit_server._active_connections:
            yield wait() # wait for the server to see the connection
        self.assertEqual(count_requests(), 0)
        self.assertEqual(len(self._usage), 2, self._usage)
        (started, result, total_bytes, total_time, waiting_time) = self._usage[1]
        self.assertEqual(result, "redundant", self._usage)

        # one of the these is unecessary, but probably harmless
        a1a.transport.loseConnection()
        a1b.transport.loseConnection()
        yield a1a._disconnect
        yield a1b._disconnect
        while self._transit_server._active_connections:
            yield wait()
        yield a2._disconnect
        self.assertEqual(len(self._usage), 3, self._usage)
        (started, result, total_bytes, total_time, waiting_time) = self._usage[2]
        self.assertEqual(result, "happy", self._usage)

