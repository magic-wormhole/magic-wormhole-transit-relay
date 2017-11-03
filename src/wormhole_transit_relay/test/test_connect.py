from __future__ import print_function, unicode_literals
import mock
from twisted.trial import unittest
from ..transit_server import Transit

class Connection(unittest.TestCase):
    def test_connection(self):
        ts = Transit(blur_usage=60, usage_logfile=None, stats_file=None)
        c1 = mock.Mock()
        c2 = mock.Mock()
        ts.connection_got_token("token1", "side1", c1)
        self.assertEqual(c1.mock_calls, [])

        ts.connection_got_token("token1", "side2", c2)
        self.assertEqual(c1.mock_calls, [mock.call.buddy_connected(c2)])
        self.assertEqual(c2.mock_calls, [mock.call.buddy_connected(c1)])

        ts.transitFinished(c1, "token1", "side1", "desc1")
        ts.transitFinished(c2, "token1", "side2", "desc2")
        

    def test_lonely(self):
        ts = Transit(blur_usage=60, usage_logfile=None, stats_file=None)
        c1 = mock.Mock()
        ts.connection_got_token("token1", "side1", c1)
        self.assertEqual(c1.mock_calls, [])

        ts.transitFinished(c1, "token1", "side1", "desc1")
