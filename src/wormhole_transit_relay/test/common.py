from twisted.test import proto_helpers
from ..transit_server import Transit

class ServerBase:
    log_requests = False

    def setUp(self):
        self._lp = None
        if self.log_requests:
            blur_usage = None
        else:
            blur_usage = 60.0
        self._setup_relay(blur_usage=blur_usage)
        self._transit_server._debug_log = self.log_requests

    def _setup_relay(self, blur_usage=None, log_file=None, usage_db=None):
        self._transit_server = Transit(blur_usage=blur_usage,
                                       log_file=log_file, usage_db=usage_db)

    def new_protocol(self):
        protocol = self._transit_server.buildProtocol(('127.0.0.1', 0))
        transport = proto_helpers.StringTransportWithDisconnection()
        protocol.makeConnection(transport)
        transport.protocol = protocol
        return protocol

    def tearDown(self):
        if self._lp:
            return self._lp.stopListening()
