from twisted.trial import unittest
from unittest import mock
from twisted.application.service import MultiService
from autobahn.twisted.websocket import WebSocketServerFactory
from .. import server_tap

class Service(unittest.TestCase):
    def test_defaults(self):
        o = server_tap.Options()
        o.parseOptions([])
        with mock.patch("wormhole_transit_relay.server_tap.create_usage_tracker") as t:
            s = server_tap.makeService(o)
        self.assertEqual(t.mock_calls,
                         [mock.call(blur_usage=None,
                                    log_file=None, usage_db=None)])
        self.assertIsInstance(s, MultiService)

    def test_blur(self):
        o = server_tap.Options()
        o.parseOptions(["--blur-usage=60"])
        with mock.patch("wormhole_transit_relay.server_tap.create_usage_tracker") as t:
            server_tap.makeService(o)
        self.assertEqual(t.mock_calls,
                         [mock.call(blur_usage=60,
                                    log_file=None, usage_db=None)])

    def test_log_fd(self):
        o = server_tap.Options()
        o.parseOptions(["--log-fd=99"])
        fd = object()
        with mock.patch("wormhole_transit_relay.server_tap.create_usage_tracker") as t:
            with mock.patch("wormhole_transit_relay.server_tap.os.fdopen",
                            return_value=fd) as f:
                server_tap.makeService(o)
        self.assertEqual(f.mock_calls, [mock.call(99, "w")])
        self.assertEqual(t.mock_calls,
                         [mock.call(blur_usage=None,
                                    log_file=fd, usage_db=None)])

    def test_websocket(self):
        """
        A websocket factory is created when passing --websocket
        """
        o = server_tap.Options()
        o.parseOptions(["--websocket=tcp:4004"])
        services = server_tap.makeService(o)
        self.assertTrue(
            any(
                isinstance(s.factory, WebSocketServerFactory)
                for s in services.services
            )
        )

    def test_websocket_explicit_url(self):
        """
        A websocket factory is created with --websocket and
        --websocket-url
        """
        o = server_tap.Options()
        o.parseOptions([
            "--websocket=tcp:4004",
            "--websocket-url=ws://example.com:4004",
        ])
        services = server_tap.makeService(o)
        self.assertTrue(
            any(
                isinstance(s.factory, WebSocketServerFactory)
                for s in services.services
            )
        )
