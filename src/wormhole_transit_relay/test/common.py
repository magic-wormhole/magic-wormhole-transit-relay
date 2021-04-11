from twisted.internet.protocol import (
    ClientFactory,
    Protocol,
)
from twisted.test import iosim
from zope.interface import (
    Interface,
    Attribute,
    implementer,
)
from ..transit_server import (
    Transit,
)


class IRelayTestClient(Interface):
    """
    The client interface used by tests.
    """

    connected = Attribute("True if we are currently connected else False")

    def send(data):
        """
        Send some bytes.
        :param bytes data: the data to send
        """

    def disconnect():
        """
        Terminate the connection.
        """

    def get_received_data():
        """
        :returns: all the bytes received from the server on this
        connection.
        """

    def reset_data():
        """
        Erase any received data to this point.
        """

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
        """
        Create a new client protocol connected to the server.
        :returns: a IRelayTestClient implementation
        """
        server_protocol = self._transit_server.buildProtocol(('127.0.0.1', 0))

        @implementer(IRelayTestClient)
        class TransitClientProtocolTcp(Protocol):
            """
            Speak the transit client protocol used by the tests over TCP
            """
            _received = b""
            connected = False

            # override Protocol callbacks

            def connectionMade(self):
                self.connected = True
                return Protocol.connectionMade(self)

            def connectionLost(self, reason):
                self.connected = False
                return Protocol.connectionLost(self, reason)

            def dataReceived(self, data):
                self._received = self._received + data

            # IRelayTestClient

            def send(self, data):
                self.transport.write(data)

            def disconnect(self):
                self.transport.loseConnection()

            def reset_received_data(self):
                self._received = b""

            def get_received_data(self):
                return self._received

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
