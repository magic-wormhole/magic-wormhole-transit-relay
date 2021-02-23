from __future__ import print_function

from twisted.internet import endpoints
from twisted.internet.defer import (
    Deferred,
    inlineCallbacks,
)
from twisted.internet.task import react
from twisted.internet.error import (
    ConnectionDone,
)
from twisted.internet.protocol import (
    Protocol,
    Factory,
)
from twisted.protocols.basic import LineReceiver
from twisted.application.internet import StreamServerEndpointService

from autobahn.twisted.websocket import (
    WebSocketClientProtocol,
    WebSocketClientFactory,
)
from autobahn.websocket import types


class RelayEchoClient(WebSocketClientProtocol):

    def onOpen(self):
        self.data = b""
        self.sendMessage(u"please relay {}".format(self.factory.token).encode("ascii"), True)

    def onConnecting(self, details):
        return types.ConnectingRequest(
            protocols=["transit_relay"],
        )

    def onMessage(self, data, isBinary):
        print(">onMessage: {} bytes".format(len(data)))
        print(data, isBinary)
        if data == b"ok\n":
            self.factory.ready.callback(None)
        else:
            self.data += data
        return True

    def onClose(self, wasClean, code, reason):
        print(">onClose", wasClean, code, reason)
        self.factory.done.callback(reason)


@react
@inlineCallbacks
def main(reactor):
    ep = endpoints.clientFromString(reactor, "tcp:localhost:4002")
    f = WebSocketClientFactory("ws://127.0.0.1:4002/")
    f.protocol = RelayEchoClient
    # NB: write our own factory, probably..
    f.token = "a" * 64
    f.done = Deferred()
    f.ready = Deferred()
    proto = yield ep.connect(f)
    # proto_d = ep.connect(f)
    # print("proto_d", proto_d)
    # proto = yield proto_d
    print("proto", proto, f.done)
    yield f.ready
    print("ready")
    import sys
    if len(sys.argv) > 2:
        proto.sendMessage(b"it's a message", True)
        yield proto.sendClose()
    yield f.done
    print("relayed {} bytes:".format(len(proto.data)))
    print(proto.data.decode("utf8"))
