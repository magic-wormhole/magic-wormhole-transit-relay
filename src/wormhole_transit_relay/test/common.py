#from __future__ import unicode_literals
from twisted.internet import reactor, endpoints
from twisted.internet.defer import inlineCallbacks
from ..transit_server import Transit

class ServerBase:
    log_requests = False

    @inlineCallbacks
    def setUp(self):
        self._lp = None
        if self.log_requests:
            blur_usage = None
        else:
            blur_usage = 60.0
        yield self._setup_relay(blur_usage=blur_usage)
        self._transit_server._debug_log = self.log_requests

    @inlineCallbacks
    def _setup_relay(self, blur_usage=None, log_file=None, usage_db=None):
        ep = endpoints.TCP4ServerEndpoint(reactor, 0, interface="127.0.0.1")
        self._transit_server = Transit(blur_usage=blur_usage,
                                       log_file=log_file, usage_db=usage_db)
        self._lp = yield ep.listen(self._transit_server)
        addr = self._lp.getHost()
        # ws://127.0.0.1:%d/wormhole-relay/ws
        self.transit = u"tcp:127.0.0.1:%d" % addr.port

    def tearDown(self):
        if self._lp:
            return self._lp.stopListening()
