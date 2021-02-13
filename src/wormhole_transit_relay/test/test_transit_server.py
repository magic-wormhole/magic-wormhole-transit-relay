from __future__ import print_function, unicode_literals
from binascii import hexlify
from twisted.trial import unittest
from .common import ServerBase
from ..server_state import (
    MemoryUsageRecorder,
    blur_size,
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

        p1.dataReceived(handshake(token1, side1))
        self.assertEqual(self.count(), 1)

        p1.transport.loseConnection()
        self.assertEqual(self.count(), 0)

        # the token should be removed too
        self.assertEqual(len(self._transit_server.pending_requests._requests), 0)

    def test_both_unsided(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()

        token1 = b"\x00"*32
        p1.dataReceived(handshake(token1, side=None))
        p2.dataReceived(handshake(token1, side=None))

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        self.assertEqual(p1.transport.value(), exp)
        self.assertEqual(p2.transport.value(), exp)

        p1.transport.clear()
        p2.transport.clear()

        s1 = b"data1"
        p1.dataReceived(s1)
        self.assertEqual(p2.transport.value(), s1)

        p1.transport.loseConnection()
        p2.transport.loseConnection()

    def test_sided_unsided(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        p1.dataReceived(handshake(token1, side=side1))
        p2.dataReceived(handshake(token1, side=None))

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        self.assertEqual(p1.transport.value(), exp)
        self.assertEqual(p2.transport.value(), exp)

        p1.transport.clear()
        p2.transport.clear()

        # all data they sent after the handshake should be given to us
        s1 = b"data1"
        p1.dataReceived(s1)
        self.assertEqual(p2.transport.value(), s1)

        p1.transport.loseConnection()
        p2.transport.loseConnection()

    def test_unsided_sided(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        p1.dataReceived(handshake(token1, side=None))
        p2.dataReceived(handshake(token1, side=side1))

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        self.assertEqual(p1.transport.value(), exp)
        self.assertEqual(p2.transport.value(), exp)

        p1.transport.clear()
        p2.transport.clear()

        # all data they sent after the handshake should be given to us
        s1 = b"data1"
        p1.dataReceived(s1)
        self.assertEqual(p2.transport.value(), s1)

        p1.transport.loseConnection()
        p2.transport.loseConnection()

    def test_both_sided(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        side2 = b"\x02"*8
        p1.dataReceived(handshake(token1, side=side1))
        p2.dataReceived(handshake(token1, side=side2))

        # a correct handshake yields an ack, after which we can send
        exp = b"ok\n"
        self.assertEqual(p1.transport.value(), exp)
        self.assertEqual(p2.transport.value(), exp)

        p1.transport.clear()
        p2.transport.clear()

        # all data they sent after the handshake should be given to us
        s1 = b"data1"
        p1.dataReceived(s1)
        self.assertEqual(p2.transport.value(), s1)

        p1.transport.loseConnection()
        p2.transport.loseConnection()

    def test_ignore_same_side(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()
        p3 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8

        p1.dataReceived(handshake(token1, side=side1))
        self.assertEqual(self.count(), 1)

        p2.dataReceived(handshake(token1, side=side1))
        self.assertEqual(self.count(), 2) # same-side connections don't match

        # when the second side arrives, the spare first connection should be
        # closed
        side2 = b"\x02"*8
        p3.dataReceived(handshake(token1, side=side2))
        self.assertEqual(self.count(), 0)
        self.assertEqual(len(self._transit_server.pending_requests._requests), 0)
        self.assertEqual(len(self._transit_server.active_connections._connections), 2)
        # That will trigger a disconnect on exactly one of (p1 or p2).
        # The other connection should still be connected
        self.assertEqual(sum([int(t.transport.connected) for t in [p1, p2]]), 1)

        p1.transport.loseConnection()
        p2.transport.loseConnection()
        p3.transport.loseConnection()

    def test_bad_handshake_old(self):
        p1 = self.new_protocol()

        token1 = b"\x00"*32
        p1.dataReceived(b"please DELAY " + hexlify(token1) + b"\n")

        exp = b"bad handshake\n"
        self.assertEqual(p1.transport.value(), exp)
        p1.transport.loseConnection()

    def test_bad_handshake_old_slow(self):
        p1 = self.new_protocol()

        p1.dataReceived(b"please DELAY ")
        # As in test_impatience_new_slow, the current state machine has code
        # that can only be reached if we insert a stall here, so dataReceived
        # gets called twice. Hopefully we can delete this test once
        # dataReceived is refactored to remove that state.

        token1 = b"\x00"*32
        # the server waits for the exact number of bytes in the expected
        # handshake message. to trigger "bad handshake", we must match.
        p1.dataReceived(hexlify(token1) + b"\n")

        exp = b"bad handshake\n"
        self.assertEqual(p1.transport.value(), exp)

        p1.transport.loseConnection()

    def test_bad_handshake_new(self):
        p1 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        # the server waits for the exact number of bytes in the expected
        # handshake message. to trigger "bad handshake", we must match.
        p1.dataReceived(b"please DELAY " + hexlify(token1) +
                        b" for side " + hexlify(side1) + b"\n")

        exp = b"bad handshake\n"
        self.assertEqual(p1.transport.value(), exp)

        p1.transport.loseConnection()

    def test_binary_handshake(self):
        p1 = self.new_protocol()

        binary_bad_handshake = b"\x00\x01\xe0\x0f\n\xff"
        # the embedded \n makes the server trigger early, before the full
        # expected handshake length has arrived. A non-wormhole client
        # writing non-ascii junk to the transit port used to trigger a
        # UnicodeDecodeError when it tried to coerce the incoming handshake
        # to unicode, due to the ("\n" in buf) check. This was fixed to use
        # (b"\n" in buf). This exercises the old failure.
        p1.dataReceived(binary_bad_handshake)

        exp = b"bad handshake\n"
        self.assertEqual(p1.transport.value(), exp)

        p1.transport.loseConnection()

    def test_impatience_old(self):
        p1 = self.new_protocol()

        token1 = b"\x00"*32
        # sending too many bytes is impatience.
        p1.dataReceived(b"please relay " + hexlify(token1) + b"\nNOWNOWNOW")

        exp = b"impatient\n"
        self.assertEqual(p1.transport.value(), exp)

        p1.transport.loseConnection()

    def test_impatience_new(self):
        p1 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        # sending too many bytes is impatience.
        p1.dataReceived(b"please relay " + hexlify(token1) +
                        b" for side " + hexlify(side1) + b"\nNOWNOWNOW")

        exp = b"impatient\n"
        self.assertEqual(p1.transport.value(), exp)

        p1.transport.loseConnection()

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
        p1.dataReceived(b"please relay " + hexlify(token1) +
                        b" for side " + hexlify(side1) + b"\n")


        p1.dataReceived(b"NOWNOWNOW")

        exp = b"impatient\n"
        self.assertEqual(p1.transport.value(), exp)

        p1.transport.loseConnection()

    def test_short_handshake(self):
        p1 = self.new_protocol()
        # hang up before sending a complete handshake
        p1.dataReceived(b"short")
        p1.transport.loseConnection()

    def test_empty_handshake(self):
        p1 = self.new_protocol()
        # hang up before sending anything
        p1.transport.loseConnection()


class TransitWithLogs(_Transit, ServerBase, unittest.TestCase):
    log_requests = True


class TransitWithoutLogs(_Transit, ServerBase, unittest.TestCase):
    log_requests = False


class Usage(ServerBase, unittest.TestCase):

    def setUp(self):
        super(Usage, self).setUp()
        self._usage = MemoryUsageRecorder()
        self._transit_server.usage.add_backend(self._usage)

    def test_empty(self):
        p1 = self.new_protocol()
        # hang up before sending anything
        p1.transport.loseConnection()

        # that will log the "empty" usage event
        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual(self._usage.events[0]["mood"], "empty", self._usage)

    def test_short(self):
        p1 = self.new_protocol()
        # hang up before sending a complete handshake
        p1.transport.write(b"short")
        p1.transport.loseConnection()

        # that will log the "empty" usage event
        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual("empty", self._usage.events[0]["mood"])

    def test_errory(self):
        p1 = self.new_protocol()

        p1.dataReceived(b"this is a very bad handshake\n")
        # that will log the "errory" usage event, then drop the connection
        p1.transport.loseConnection()
        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual(self._usage.events[0]["mood"], "errory", self._usage)

    def test_lonely(self):
        p1 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        p1.dataReceived(handshake(token1, side=side1))
        # now we disconnect before the peer connects
        p1.transport.loseConnection()

        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual(self._usage.events[0]["mood"], "lonely", self._usage)
        self.assertIdentical(self._usage.events[0]["waiting_time"], None)

    def test_one_happy_one_jilted(self):
        p1 = self.new_protocol()
        p2 = self.new_protocol()

        token1 = b"\x00"*32
        side1 = b"\x01"*8
        side2 = b"\x02"*8
        p1.dataReceived(handshake(token1, side=side1))
        p2.dataReceived(handshake(token1, side=side2))

        self.assertEqual(self._usage.events, []) # no events yet

        p1.dataReceived(b"\x00" * 13)
        p2.dataReceived(b"\xff" * 7)

        p1.transport.loseConnection()

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
        p1a.dataReceived(handshake(token1, side=side1))
        p1b.dataReceived(handshake(token1, side=side1))

        # connect and disconnect a third client (for side1) to exercise the
        # code that removes a pending connection without removing the entire
        # token
        p1c.dataReceived(handshake(token1, side=side1))
        p1c.transport.loseConnection()

        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual(self._usage.events[0]["mood"], "lonely")

        p2.dataReceived(handshake(token1, side=side2))
        self.assertEqual(len(self._transit_server.pending_requests._requests), 0)
        self.assertEqual(len(self._usage.events), 2, self._usage)
        self.assertEqual(self._usage.events[1]["mood"], "redundant")

        # one of the these is unecessary, but probably harmless
        p1a.transport.loseConnection()
        p1b.transport.loseConnection()
        self.assertEqual(len(self._usage.events), 3, self._usage)
        self.assertEqual(self._usage.events[2]["mood"], "happy")
