from __future__ import unicode_literals, print_function
from twisted.trial import unittest
from .. import server_tap

class Config(unittest.TestCase):
    def test_defaults(self):
        o = server_tap.Options()
        o.parseOptions([])
        self.assertEqual(o, {"blur-usage": None, "log-fd": None,
                             "usage-db": None, "port": "tcp:4001"})
    def test_blur(self):
        o = server_tap.Options()
        o.parseOptions(["--blur-usage=60"])
        self.assertEqual(o, {"blur-usage": 60, "log-fd": None,
                             "usage-db": None, "port": "tcp:4001"})

    def test_string(self):
        o = server_tap.Options()
        s = str(o)
        self.assertIn("This plugin sets up a 'Transit Relay'", s)
        self.assertIn("--blur-usage=", s)
        self.assertIn("blur timestamps and data sizes in logs", s)

