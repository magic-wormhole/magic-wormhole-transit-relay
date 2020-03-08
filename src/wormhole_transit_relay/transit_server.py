from __future__ import print_function, unicode_literals
import re, time, json
from collections import defaultdict
from twisted.python import log
from twisted.internet import protocol
from .database import get_db

SECONDS = 1.0
MINUTE = 60*SECONDS
HOUR = 60*MINUTE
DAY = 24*HOUR
MB = 1000*1000

def round_to(size, coarseness):
    return int(coarseness*(1+int((size-1)/coarseness)))

def blur_size(size):
    if size == 0:
        return 0
    if size < 1e6:
        return round_to(size, 10e3)
    if size < 1e9:
        return round_to(size, 1e6)
    return round_to(size, 100e6)

class TransitConnection(protocol.Protocol):
    def __init__(self):
        self._got_token = False
        self._got_side = False
        self._token_buffer = b""
        self._sent_ok = False
        self._mood = None
        self._buddy = None
        self._total_sent = 0

    def describeToken(self):
        d = "-"
        if self._got_token:
            d = self._got_token[:16].decode("ascii")
        if self._got_side:
            d += "-" + self._got_side.decode("ascii")
        else:
            d += "-<unsided>"
        return d

    def connectionMade(self):
        self._started = time.time()
        self._log_requests = self.factory._log_requests
        try:
            self.transport.setTcpKeepAlive(True)
        except AttributeError:
            pass

    def dataReceived(self, data):
        if self._sent_ok:
            # We are an IPushProducer to our buddy's IConsumer, so they'll
            # throttle us (by calling pauseProducing()) when their outbound
            # buffer is full (e.g. when their downstream pipe is full). In
            # practice, this buffers about 10MB per connection, after which
            # point the sender will only transmit data as fast as the
            # receiver can handle it.
            self._total_sent += len(data)
            self._buddy.transport.write(data)
            return

        if self._got_token: # but not yet sent_ok
            self.transport.write(b"impatient\n")
            if self._log_requests:
                log.msg("transit impatience failure")
            return self.disconnect_error() # impatience yields failure

        # else this should be (part of) the token
        self._token_buffer += data
        buf = self._token_buffer

        # old: "please relay {64}\n"
        # new: "please relay {64} for side {16}\n"
        (old, handshake_len, token) = self._check_old_handshake(buf)
        assert old in ("yes", "waiting", "no")
        if old == "yes":
            # remember they aren't supposed to send anything past their
            # handshake until we've said go
            if len(buf) > handshake_len:
                self.transport.write(b"impatient\n")
                if self._log_requests:
                    log.msg("transit impatience failure")
                return self.disconnect_error() # impatience yields failure
            return self._got_handshake(token, None)
        (new, handshake_len, token, side) = self._check_new_handshake(buf)
        assert new in ("yes", "waiting", "no")
        if new == "yes":
            if len(buf) > handshake_len:
                self.transport.write(b"impatient\n")
                if self._log_requests:
                    log.msg("transit impatience failure")
                return self.disconnect_error() # impatience yields failure
            return self._got_handshake(token, side)
        if (old == "no" and new == "no"):
            self.transport.write(b"bad handshake\n")
            if self._log_requests:
                log.msg("transit handshake failure")
            return self.disconnect_error() # incorrectness yields failure
        # else we'll keep waiting

    def _check_old_handshake(self, buf):
        # old: "please relay {64}\n"
        # return ("yes", handshake, token) if buf contains an old-style handshake
        # return ("waiting", None, None) if it might eventually contain one
        # return ("no", None, None) if it could never contain one
        wanted = len("please relay \n")+32*2
        if len(buf) < wanted-1 and b"\n" in buf:
            return ("no", None, None)
        if len(buf) < wanted:
            return ("waiting", None, None)

        mo = re.search(br"^please relay (\w{64})\n", buf, re.M)
        if mo:
            token = mo.group(1)
            return ("yes", wanted, token)
        return ("no", None, None)

    def _check_new_handshake(self, buf):
        # new: "please relay {64} for side {16}\n"
        wanted = len("please relay  for side \n")+32*2+8*2
        if len(buf) < wanted-1 and b"\n" in buf:
            return ("no", None, None, None)
        if len(buf) < wanted:
            return ("waiting", None, None, None)

        mo = re.search(br"^please relay (\w{64}) for side (\w{16})\n", buf, re.M)
        if mo:
            token = mo.group(1)
            side = mo.group(2)
            return ("yes", wanted, token, side)
        return ("no", None, None, None)

    def _got_handshake(self, token, side):
        self._got_token = token
        self._got_side = side
        self._mood = "lonely" # until buddy connects
        self.factory.connection_got_token(token, side, self)

    def buddy_connected(self, them):
        self._buddy = them
        self._mood = "happy"
        self.transport.write(b"ok\n")
        self._sent_ok = True
        # Connect the two as a producer/consumer pair. We use streaming=True,
        # so this expects the IPushProducer interface, and uses
        # pauseProducing() to throttle, and resumeProducing() to unthrottle.
        self._buddy.transport.registerProducer(self.transport, True)
        # The Transit object calls buddy_connected() on both protocols, so
        # there will be two producer/consumer pairs.

    def buddy_disconnected(self):
        if self._log_requests:
            log.msg("buddy_disconnected %s" % self.describeToken())
        self._buddy = None
        self._mood = "jilted"
        self.transport.loseConnection()

    def disconnect_error(self):
        # we haven't finished the handshake, so there are no tokens tracking
        # us
        self._mood = "errory"
        self.transport.loseConnection()
        if self.factory._debug_log:
            log.msg("transitFailed %r" % self)

    def disconnect_redundant(self):
        # this is called if a buddy connected and we were found unnecessary.
        # Any token-tracking cleanup will have been done before we're called.
        self._mood = "redundant"
        self.transport.loseConnection()

    def connectionLost(self, reason):
        finished = time.time()
        total_time = finished - self._started

        # Record usage. There are seven cases:
        # * n1: the handshake failed, not a real client (errory)
        # * n2: real client disconnected before any buddy appeared (lonely)
        # * n3: real client closed as redundant after buddy appears (redundant)
        # * n4: real client connected first, buddy closes first (jilted)
        # * n5: real client connected first, buddy close last (happy)
        # * n6: real client connected last, buddy closes first (jilted)
        # * n7: real client connected last, buddy closes last (happy)

        # * non-connected clients (1,2,3) always write a usage record
        # * for connected clients, whoever disconnects first gets to write the
        #   usage record (5, 7). The last disconnect doesn't write a record.

        if self._mood == "errory": # 1
            assert not self._buddy
            self.factory.recordUsage(self._started, "errory", 0,
                                     total_time, None)
        elif self._mood == "redundant": # 3
            assert not self._buddy
            self.factory.recordUsage(self._started, "redundant", 0,
                                     total_time, None)
        elif self._mood == "jilted": # 4 or 6
            # we were connected, but our buddy hung up on us. They record the
            # usage event, we do not
            pass
        elif self._mood == "lonely": # 2
            assert not self._buddy
            self.factory.recordUsage(self._started, "lonely", 0,
                                     total_time, None)
        else: # 5 or 7
            # we were connected, we hung up first. We record the event.
            assert self._mood == "happy", self._mood # TODO: mood==None
            assert self._buddy
            starts = [self._started, self._buddy._started]
            total_time = finished - min(starts)
            waiting_time = max(starts) - min(starts)
            total_bytes = self._total_sent + self._buddy._total_sent
            self.factory.recordUsage(self._started, "happy", total_bytes,
                                     total_time, waiting_time)

        if self._buddy:
            self._buddy.buddy_disconnected()
        self.factory.transitFinished(self, self._got_token, self._got_side,
                                     self.describeToken())

class Transit(protocol.ServerFactory):
    # I manage pairs of simultaneous connections to a secondary TCP port,
    # both forwarded to the other. Clients must begin each connection with
    # "please relay TOKEN for SIDE\n" (or a legacy form without the "for
    # SIDE"). Two connections match if they use the same TOKEN and have
    # different SIDEs (the redundant connections are dropped when a match is
    # made). Legacy connections match any with the same TOKEN, ignoring SIDE
    # (so two legacy connections will match each other).

    # I will send "ok\n" when the matching connection is established, or
    # disconnect if no matching connection is made within MAX_WAIT_TIME
    # seconds. I will disconnect if you send data before the "ok\n". All data
    # you get after the "ok\n" will be from the other side. You will not
    # receive "ok\n" until the other side has also connected and submitted a
    # matching token (and differing SIDE).

    # In addition, the connections will be dropped after MAXLENGTH bytes have
    # been sent by either side, or MAXTIME seconds have elapsed after the
    # matching connections were established. A future API will reveal these
    # limits to clients instead of causing mysterious spontaneous failures.

    # These relay connections are not half-closeable (unlike full TCP
    # connections, applications will not receive any data after half-closing
    # their outgoing side). Applications must negotiate shutdown with their
    # peer and not close the connection until all data has finished
    # transferring in both directions. Applications which only need to send
    # data in one direction can use close() as usual.

    MAX_WAIT_TIME = 30*SECONDS
    MAXLENGTH = 10*MB
    MAXTIME = 60*SECONDS
    protocol = TransitConnection

    def __init__(self, blur_usage, log_file, usage_db):
        self._blur_usage = blur_usage
        self._log_requests = blur_usage is None
        if self._blur_usage:
            log.msg("blurring access times to %d seconds" % self._blur_usage)
            log.msg("not logging Transit connections to Twisted log")
        else:
            log.msg("not blurring access times")
        self._debug_log = False
        self._log_file = log_file
        self._db = None
        if usage_db:
            self._db = get_db(usage_db)
        self._rebooted = time.time()
        # we don't track TransitConnections until they submit a token
        self._pending_requests = defaultdict(set) # token -> set((side, TransitConnection))
        self._active_connections = set() # TransitConnection

    def connection_got_token(self, token, new_side, new_tc):
        potentials = self._pending_requests[token]
        for old in potentials:
            (old_side, old_tc) = old
            if ((old_side is None)
                or (new_side is None)
                or (old_side != new_side)):
                # we found a match
                if self._debug_log:
                    log.msg("transit relay 2: %s" % new_tc.describeToken())

                # drop and stop tracking the rest
                potentials.remove(old)
                for (_, leftover_tc) in potentials.copy():
                    # Don't record this as errory. It's just a spare connection
                    # from the same side as a connection that got used. This
                    # can happen if the connection hint contains multiple
                    # addresses (we don't currently support those, but it'd
                    # probably be useful in the future).
                    leftover_tc.disconnect_redundant()
                self._pending_requests.pop(token, None)

                # glue the two ends together
                self._active_connections.add(new_tc)
                self._active_connections.add(old_tc)
                new_tc.buddy_connected(old_tc)
                old_tc.buddy_connected(new_tc)
                return
        if self._debug_log:
            log.msg("transit relay 1: %s" % new_tc.describeToken())
        potentials.add((new_side, new_tc))
        # TODO: timer

    def transitFinished(self, tc, token, side, description):
        if token in self._pending_requests:
            side_tc = (side, tc)
            self._pending_requests[token].discard(side_tc)
            if not self._pending_requests[token]: # set is now empty
                del self._pending_requests[token]
        if self._debug_log:
            log.msg("transitFinished %s" % (description,))
        self._active_connections.discard(tc)
        # we could update the usage database "current" row immediately, or wait
        # until the 5-minute timer updates it. If we update it now, just after
        # losing a connection, we should probably also update it just after
        # establishing one (at the end of connection_got_token). For now I'm
        # going to omit these, but maybe someday we'll turn them both on. The
        # consequence is that a manual execution of the munin scripts ("munin
        # run wormhole_transit_active") will give the wrong value just after a
        # connect/disconnect event. Actual munin graphs should accurately
        # report connections that last longer than the 5-minute sampling
        # window, which is what we actually care about.
        #self.timerUpdateStats()

    def recordUsage(self, started, result, total_bytes,
                    total_time, waiting_time):
        if self._debug_log:
            log.msg(format="Transit.recordUsage {bytes}B", bytes=total_bytes)
        if self._blur_usage:
            started = self._blur_usage * (started // self._blur_usage)
            total_bytes = blur_size(total_bytes)
        if self._log_file is not None:
            data = {"started": started,
                    "total_time": total_time,
                    "waiting_time": waiting_time,
                    "total_bytes": total_bytes,
                    "mood": result,
                    }
            self._log_file.write(json.dumps(data)+"\n")
            self._log_file.flush()
        if self._db:
            self._db.execute("INSERT INTO `usage`"
                             " (`started`, `total_time`, `waiting_time`,"
                             "  `total_bytes`, `result`)"
                             " VALUES (?,?,?, ?,?)",
                             (started, total_time, waiting_time,
                              total_bytes, result))
            self._update_stats()
            self._db.commit()

    def timerUpdateStats(self):
        if self._db:
            self._update_stats()
            self._db.commit()

    def _update_stats(self):
        # current status: should be zero when idle
        rebooted = self._rebooted
        updated = time.time()
        connected = len(self._active_connections) / 2
        # TODO: when a connection is half-closed, len(active) will be odd. a
        # moment later (hopefully) the other side will disconnect, but
        # _update_stats isn't updated until later.
        waiting = len(self._pending_requests)
        # "waiting" doesn't count multiple parallel connections from the same
        # side
        incomplete_bytes = sum(tc._total_sent
                               for tc in self._active_connections)
        self._db.execute("DELETE FROM `current`")
        self._db.execute("INSERT INTO `current`"
                         " (`rebooted`, `updated`, `connected`, `waiting`,"
                         "  `incomplete_bytes`)"
                         " VALUES (?, ?, ?, ?, ?)",
                         (rebooted, updated, connected, waiting,
                          incomplete_bytes))
