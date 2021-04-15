"""
This is a test-client for the transit-relay that uses WebSockets.

If an additional command-line argument (anything) is added, it will
send 5 messages upon connection. Otherwise, it just prints out what is
received. Uses a fixed token of 64 'a' characters. Always connects on
localhost:4002
"""

import sys

from twisted.internet import endpoints
from twisted.internet.defer import (
    Deferred,
    inlineCallbacks,
)
from twisted.internet.task import react, deferLater

from autobahn.twisted.websocket import (
    WebSocketClientProtocol,
    WebSocketClientFactory,
)


class RelayEchoClient(WebSocketClientProtocol):

    def onOpen(self):
        self._received = b""
        self.sendMessage(
            u"please relay {} for side {}".format(
                self.factory.token,
                self.factory.side,
            ).encode("ascii"),
            True,
        )

    def onMessage(self, data, isBinary):
        print(">onMessage: {} bytes".format(len(data)))
        print(data, isBinary)
        if data == b"ok\n":
            self.factory.ready.callback(None)
        else:
            self._received += data
            if False:
                # test abrupt hangup from receiving side
                self.transport.loseConnection()

    def onClose(self, wasClean, code, reason):
        print(">onClose", wasClean, code, reason)
        self.factory.done.callback(reason)
        if not self.factory.ready.called:
            self.factory.ready.errback(RuntimeError(reason))


@react
@inlineCallbacks
def main(reactor):
    will_send_message = len(sys.argv) > 1
    ep = endpoints.clientFromString(reactor, "tcp:localhost:4002")
    f = WebSocketClientFactory("ws://127.0.0.1:4002/")
    f.reactor = reactor
    f.protocol = RelayEchoClient
    f.token = "a" * 64
    f.side = "0" * 16 if will_send_message else "1" * 16
    f.done = Deferred()
    f.ready = Deferred()

    proto = yield ep.connect(f)
    print("proto", proto)
    yield f.ready

    print("ready")
    if will_send_message:
        for _ in range(5):
            print("sending message")
            proto.sendMessage(b"it's a message", True)
            yield deferLater(reactor, 0.2)
        yield proto.sendClose()
        print("closing")
    yield f.done
    print("relayed {} bytes:".format(len(proto._received)))
    print(proto._received.decode("utf8"))
