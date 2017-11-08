from __future__ import unicode_literals, print_function
from twisted.trial import unittest
import mock
from twisted.application.service import MultiService
from .. import server_tap

class Service(unittest.TestCase):
    def test_defaults(self):
        o = server_tap.Options()
        o.parseOptions([])
        with mock.patch("wormhole_transit_relay.server_tap.transit_server.Transit") as t:
            s = server_tap.makeService(o)
        self.assertEqual(t.mock_calls,
                         [mock.call(blur_usage=None,
                                    log_file=None, usage_db=None)])
        self.assertIsInstance(s, MultiService)

    def test_blur(self):
        o = server_tap.Options()
        o.parseOptions(["--blur-usage=60"])
        with mock.patch("wormhole_transit_relay.server_tap.transit_server.Transit") as t:
            server_tap.makeService(o)
        self.assertEqual(t.mock_calls,
                         [mock.call(blur_usage=60,
                                    log_file=None, usage_db=None)])

    def test_log_fd(self):
        o = server_tap.Options()
        o.parseOptions(["--log-fd=99"])
        fd = object()
        with mock.patch("wormhole_transit_relay.server_tap.transit_server.Transit") as t:
            with mock.patch("wormhole_transit_relay.server_tap.os.fdopen",
                            return_value=fd) as f:
                server_tap.makeService(o)
        self.assertEqual(f.mock_calls, [mock.call(99, "w")])
        self.assertEqual(t.mock_calls,
                         [mock.call(blur_usage=None,
                                    log_file=fd, usage_db=None)])

