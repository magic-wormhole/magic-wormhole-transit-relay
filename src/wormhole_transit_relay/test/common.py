from twisted.test import proto_helpers
from ..transit_server import Transit
from ..server_state import create_usage_tracker

class ServerBase:
    log_requests = False

    def setUp(self):
        self._lp = None
        self._setup_relay(blur_usage=60.0 if self.log_requests else None)
        self._transit_server._debug_log = self.log_requests

    def _setup_relay(self, blur_usage=None, log_file=None, usage_db=None):
        usage = create_usage_tracker(
            blur_usage=blur_usage,
            log_file=log_file,
            usage_db=usage_db,
        )
        self._transit_server = Transit(usage, lambda: 123456789.0)

    def new_protocol(self):
        protocol = self._transit_server.buildProtocol(('127.0.0.1', 0))
        transport = proto_helpers.StringTransportWithDisconnection()
        protocol.makeConnection(transport)
        transport.protocol = protocol
        return protocol

    def tearDown(self):
        if self._lp:
            return self._lp.stopListening()
