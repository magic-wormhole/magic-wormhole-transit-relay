from __future__ import print_function, unicode_literals
import mock
from twisted.trial import unittest
from ..transit_server import Transit

class FakeConnection(object):
    def __init__(self, token):
        self._token = token
    def describeToken(self):
        return self._token
    def buddy_connected(self, other):
        pass

class Logging(unittest.TestCase):
    def test_connection_yeslog(self):
        ts = Transit(blur_usage=None, usage_logfile=None, stats_file=None)
        c1 = FakeConnection("c1")
        c2 = FakeConnection("c2")
        expected = []
        with mock.patch("twisted.python.log.msg") as m:
            ts.connection_got_token("token1", "side1", c1)
            expected.append(mock.call("transit relay 1: c1"))
            self.assertEqual(m.mock_calls, expected)

            ts.connection_got_token("token1", "side2", c2)
            expected.append(mock.call("transit relay 2: c2"))
            self.assertEqual(m.mock_calls, expected)

            ts.transitFinished(c1, "token1", "side1", "desc1")
            expected.append(mock.call("transitFinished desc1"))
            self.assertEqual(m.mock_calls, expected)

    def test_connection_nolog(self):
        ts = Transit(blur_usage=60, usage_logfile=None, stats_file=None)
        c1 = FakeConnection("c1")
        with mock.patch("twisted.python.log.msg") as m:
            ts.connection_got_token("token1", "side1", c1)
            self.assertEqual(m.mock_calls, [])
            ts.connection_got_token("token1", "side2", c1)
            self.assertEqual(m.mock_calls, [])

