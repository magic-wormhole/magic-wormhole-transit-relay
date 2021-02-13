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
        p2.disconnect()
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
        p2.disconnect()
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
        p1.send(b"please relay " + hexlify(token1) + b"\nNOWNOWNOW")
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
                b" for side " + hexlify(side1) + b"\nNOWNOWNOW")
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


class TransitWithoutLogs(_Transit, ServerBase, unittest.TestCase):
    log_requests = False


class Usage(ServerBase, unittest.TestCase):
    log_requests = True

    def setUp(self):
        super(Usage, self).setUp()
        self._usage = MemoryUsageRecorder()
        self._transit_server.usage.add_backend(self._usage)
##        self._transit_server.usage._blur_usage = None

    def test_empty(self):
        p1 = self.new_protocol()
        # hang up before sending anything
        p1.disconnect()
        self.flush()

        # that will log the "empty" usage event
        self.assertEqual(len(self._usage.events), 1, self._usage)
        self.assertEqual(self._usage.events[0]["mood"], "empty", self._usage)

    def test_short(self):
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
