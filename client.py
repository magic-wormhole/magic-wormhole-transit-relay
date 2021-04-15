"""
This is a test-client for the transit-relay that uses TCP. It
doesn't send any data, only prints out data that is received. Uses a
fixed token of 64 'a' characters. Always connects on localhost:4001
"""


from twisted.internet import endpoints
from twisted.internet.defer import (
    Deferred,
)
from twisted.internet.task import react
from twisted.internet.error import (
    ConnectionDone,
)
from twisted.internet.protocol import (
    Protocol,
    Factory,
)


class RelayEchoClient(Protocol):
    """
    Speaks the version1 magic wormhole transit relay protocol (as a client)
    """

    def connectionMade(self):
        print(">CONNECT")
        self.data = b""
        self.transport.write(u"please relay {}\n".format(self.factory.token).encode("ascii"))

    def dataReceived(self, data):
        print(">RECV {} bytes".format(len(data)))
        print(data.decode("ascii"))
        self.data += data
        if data == "ok\n":
            self.transport.write("ding\n")

    def connectionLost(self, reason):
        if isinstance(reason.value, ConnectionDone):
            self.factory.done.callback(None)
        else:
            print(">DISCONNCT: {}".format(reason))
            self.factory.done.callback(reason)


@react
def main(reactor):
    ep = endpoints.clientFromString(reactor, "tcp:localhost:4001")
    f = Factory.forProtocol(RelayEchoClient)
    f.token = "a" * 64
    f.done = Deferred()
    ep.connect(f)
    return f.done
