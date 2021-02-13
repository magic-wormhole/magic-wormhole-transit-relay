from __future__ import print_function, unicode_literals
import re
import time
from twisted.python import log
from twisted.internet import protocol
from twisted.protocols.basic import LineReceiver

SECONDS = 1.0
MINUTE = 60*SECONDS
HOUR = 60*MINUTE
DAY = 24*HOUR
MB = 1000*1000


from wormhole_transit_relay.server_state import (
    TransitServerState,
    PendingRequests,
    ActiveConnections,
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
        if self._buddy is not None:
            # print("buddy_disconnected {}".format(self._buddy.get_token()))
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
##        self._log_requests = self.factory._log_requests
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
##        if self._log_requests:
##            log.msg("buddy_disconnected %s" % self.describeToken())
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
# XXX this probably resulted in a log message we've not refactored yet
#        self.factory.transitFinished(self, self._got_token, self._got_side,
#                                     self.describeToken())



class Transit(protocol.ServerFactory):
    """
    I manage pairs of simultaneous connections to a secondary TCP port,
    both forwarded to the other. Clients must begin each connection with
    "please relay TOKEN for SIDE\n" (or a legacy form without the "for
    SIDE"). Two connections match if they use the same TOKEN and have
    different SIDEs (the redundant connections are dropped when a match is
    made). Legacy connections match any with the same TOKEN, ignoring SIDE
    (so two legacy connections will match each other).

    I will send "ok\n" when the matching connection is established, or
    disconnect if no matching connection is made within MAX_WAIT_TIME
    seconds. I will disconnect if you send data before the "ok\n". All data
    you get after the "ok\n" will be from the other side. You will not
    receive "ok\n" until the other side has also connected and submitted a
    matching token (and differing SIDE).

    In addition, the connections will be dropped after MAXLENGTH bytes have
    been sent by either side, or MAXTIME seconds have elapsed after the
    matching connections were established. A future API will reveal these
    limits to clients instead of causing mysterious spontaneous failures.

    These relay connections are not half-closeable (unlike full TCP
    connections, applications will not receive any data after half-closing
    their outgoing side). Applications must negotiate shutdown with their
    peer and not close the connection until all data has finished
    transferring in both directions. Applications which only need to send
    data in one direction can use close() as usual.
    """

    # TODO: unused
    MAX_WAIT_TIME = 30*SECONDS
    # TODO: unused
    MAXLENGTH = 10*MB
    # TODO: unused
    MAXTIME = 60*SECONDS
    protocol = TransitConnection

    def __init__(self, usage, get_timestamp):
        self.active_connections = ActiveConnections()
        self.pending_requests = PendingRequests(self.active_connections)
        self.usage = usage
        self._debug_log = False
        self._timestamp = get_timestamp
        self._rebooted = self._timestamp()

    def update_stats(self):
        # TODO: when a connection is half-closed, len(active) will be odd. a
        # moment later (hopefully) the other side will disconnect, but
        # _update_stats isn't updated until later.

        # "waiting" doesn't count multiple parallel connections from the same
        # side
        self.usage.update_stats(
            rebooted=self._rebooted,
            updated=self._timestamp(),
            connected=len(self.active_connections._connections),
            waiting=len(self.pending_requests._requests),
            incomplete_bytes=sum(
                tc._total_sent
                for tc in self.active_connections._connections
            ),
        )
