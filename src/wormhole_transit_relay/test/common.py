from twisted.internet.protocol import (
    ClientFactory,
    Protocol,
)
from twisted.test import iosim
from ..transit_server import (
    Transit,
)


class ServerBase:
    log_requests = False

    def setUp(self):
        self._pumps = []
        self._lp = None
        if self.log_requests:
            blur_usage = None
        else:
            blur_usage = 60.0
        self._setup_relay(blur_usage=blur_usage)

    def flush(self):
        for pump in self._pumps:
            pump.flush()

    def _setup_relay(self, blur_usage=None, log_file=None, usage_db=None):
        self._transit_server = Transit(
            blur_usage=blur_usage,
            log_file=log_file,
            usage_db=usage_db,
        )
        self._transit_server._debug_log = self.log_requests

    def new_protocol(self):
        server_protocol = self._transit_server.buildProtocol(('127.0.0.1', 0))

        # XXX interface?
        class TransitClientProtocolTcp(Protocol):
            """
            Speak the transit client protocol used by the tests over TCP
            """
            received = b""
            connected = False

            def connectionMade(self):
                self.connected = True

            def connectionLost(self, reason):
                self.connected = False

            def send(self, data):
                self.transport.write(data)

            def disconnect(self):
                self.transport.loseConnection()

            def dataReceived(self, data):
                self.received = self.received + data


        client_factory = ClientFactory()
        client_factory.protocol = TransitClientProtocolTcp
        client_protocol = client_factory.buildProtocol(('127.0.0.1', 31337))

        pump = iosim.connect(
            server_protocol,
            iosim.makeFakeServer(server_protocol),
            client_protocol,
            iosim.makeFakeClient(client_protocol),
        )
        pump.flush()
        self._pumps.append(pump)
        return client_protocol

    def tearDown(self):
        if self._lp:
            return self._lp.stopListening()
