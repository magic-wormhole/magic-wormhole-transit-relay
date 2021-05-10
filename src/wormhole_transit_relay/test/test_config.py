from twisted.trial import unittest
from .. import server_tap

PORT = "tcp:4001:interface=\:\:"

class Config(unittest.TestCase):
    def test_defaults(self):
        o = server_tap.Options()
        o.parseOptions([])
        self.assertEqual(o, {"blur-usage": None, "log-fd": None,
                             "usage-db": None, "port": PORT,
                             "websocket": None, "websocket-url": None})
    def test_blur(self):
        o = server_tap.Options()
        o.parseOptions(["--blur-usage=60"])
        self.assertEqual(o, {"blur-usage": 60, "log-fd": None,
                             "usage-db": None, "port": PORT,
                             "websocket": None, "websocket-url": None})

    def test_websocket(self):
        o = server_tap.Options()
        o.parseOptions(["--websocket=tcp:4004"])
        self.assertEqual(o, {"blur-usage": None, "log-fd": None,
                             "usage-db": None, "port": PORT,
                             "websocket": "tcp:4004", "websocket-url": None})

    def test_websocket_url(self):
        o = server_tap.Options()
        o.parseOptions(["--websocket=tcp:4004", "--websocket-url=ws://example.com/"])
        self.assertEqual(o, {"blur-usage": None, "log-fd": None,
                             "usage-db": None, "port": PORT,
                             "websocket": "tcp:4004",
                             "websocket-url": "ws://example.com/"})

    def test_string(self):
        o = server_tap.Options()
        s = str(o)
        self.assertIn("This plugin sets up a 'Transit Relay'", s)
        self.assertIn("--blur-usage=", s)
        self.assertIn("blur timestamps and data sizes in logs", s)

