from __future__ import print_function, unicode_literals
import re, time, json
from collections import defaultdict
from twisted.python import log
from twisted.internet import protocol
from twisted.protocols.basic import LineReceiver
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


from wormhole_transit_relay.server_state import (
    TransitServerState,
    PendingRequests,
    ActiveConnections,
    UsageRecorder,
    ITransitClient,
)
from zope.interface import implementer


@implementer(ITransitClient)
class TransitConnection(LineReceiver):
    delimiter = b'\n'
    # maximum length of a line we will accept before the handshake is complete.
    # This must be >= to the longest possible handshake message.

    MAX_LENGTH = 1024
    started_time = None

    def send(self, data):
        """
        ITransitClient API
        """
        self.transport.write(data)

    def disconnect(self):
        """
        ITransitClient API
        """
        self.transport.loseConnection()

    def connect_partner(self, other):
        """
        ITransitClient API
        """
        self._buddy = other

    def disconnect_partner(self):
        """
        ITransitClient API
        """
        self._buddy._client.transport.loseConnection()
        self._buddy = None

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
        # ideally more like self._reactor.seconds() ... but Twisted
        # doesn't have a good way to get the reactor for a protocol
        # (besides "use the global one")
        self.started_time = time.time()
        self._state = TransitServerState(
            self.factory.pending_requests,
            self.factory.usage,
        )
        self._state.connection_made(self)
        self._log_requests = self.factory._log_requests
        try:
            self.transport.setTcpKeepAlive(True)
        except AttributeError:
            pass

    def lineReceived(self, line):
        # old: "please relay {64}\n"
        old = re.search(br"^please relay (\w{64})$", line)
        if old:
            token = old.group(1)
            return self._got_handshake(token, None)

        # new: "please relay {64} for side {16}\n"
        new = re.search(br"^please relay (\w{64}) for side (\w{16})$", line)
        if new:
            token = new.group(1)
            side = new.group(2)
            return self._got_handshake(token, side)

        # we should have been switched to "raw data" mode on the first
        # line received (after which rawDataReceived() is called for
        # all bytes) so getting here means a bad handshake.
        return self._state.bad_token()

    def rawDataReceived(self, data):
        # We are an IPushProducer to our buddy's IConsumer, so they'll
        # throttle us (by calling pauseProducing()) when their outbound
        # buffer is full (e.g. when their downstream pipe is full). In
        # practice, this buffers about 10MB per connection, after which
        # point the sender will only transmit data as fast as the
        # receiver can handle it.
        self._state.got_bytes(data)

    def _got_handshake(self, token, side):
        self._state.please_relay_for_side(token, side)
        # self._mood = "lonely" # until buddy connects
        self.setRawMode()

    def __buddy_connected(self, them):
        self._buddy = them
        self._mood = "happy"
        self.sendLine(b"ok")
        self._sent_ok = True
        # Connect the two as a producer/consumer pair. We use streaming=True,
        # so this expects the IPushProducer interface, and uses
        # pauseProducing() to throttle, and resumeProducing() to unthrottle.
        self._buddy.transport.registerProducer(self.transport, True)
        # The Transit object calls buddy_connected() on both protocols, so
        # there will be two producer/consumer pairs.

    def __buddy_disconnected(self):
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
        self._state.connection_lost()

        # XXX FIXME record usage

        if False:
            # Record usage. There are eight cases:
            # * n0: we haven't gotten a full handshake yet (empty)
            # * n1: the handshake failed, not a real client (errory)
            # * n2: real client disconnected before any buddy appeared (lonely)
            # * n3: real client closed as redundant after buddy appears (redundant)
            # * n4: real client connected first, buddy closes first (jilted)
            # * n5: real client connected first, buddy close last (happy)
            # * n6: real client connected last, buddy closes first (jilted)
            # * n7: real client connected last, buddy closes last (happy)

            # * non-connected clients (0,1,2,3) always write a usage record
            # * for connected clients, whoever disconnects first gets to write the
            #   usage record (5, 7). The last disconnect doesn't write a record.

            if self._mood == "empty": # 0
                assert not self._buddy
                self.factory.recordUsage(self._started, "empty", 0,
                                         total_time, None)
            elif self._mood == "errory": # 1
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
                assert self._mood == "happy", self._mood
                assert self._buddy
                starts = [self._started, self._buddy._started]
                total_time = finished - min(starts)
                waiting_time = max(starts) - min(starts)
                total_bytes = self._total_sent + self._buddy._total_sent
                self.factory.recordUsage(self._started, "happy", total_bytes,
                                         total_time, waiting_time)

            if self._buddy:
                self._buddy.buddy_disconnected()
    #        self.factory.transitFinished(self, self._got_token, self._got_side,
    #                                     self.describeToken())



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
        self.active_connections = ActiveConnections()
        self.pending_requests = PendingRequests(self.active_connections)
        self.usage = UsageRecorder()
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
##        self._pending_requests = defaultdict(set) # token -> set((side, TransitConnection))
##        self._active_connections = set() # TransitConnection

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
