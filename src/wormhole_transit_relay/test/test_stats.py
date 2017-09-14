from __future__ import print_function, unicode_literals
import os, json
import mock
from twisted.trial import unittest
from ..transit_server import Transit

class UsageLog(unittest.TestCase):
    def test_log(self):
        d = self.mktemp()
        os.mkdir(d)
        usage_logfile = os.path.join(d, "usage.log")
        def read():
            with open(usage_logfile, "r") as f:
                return [json.loads(line) for line in f.readlines()]
        t = Transit(None, usage_logfile, None)
        t.recordUsage(started=123, result="happy", total_bytes=100,
                      total_time=10, waiting_time=2)
        self.assertEqual(read(), [dict(started=123, mood="happy",
                                       total_time=10, waiting_time=2,
                                       total_bytes=100)])

        t.recordUsage(started=150, result="errory", total_bytes=200,
                      total_time=11, waiting_time=3)
        self.assertEqual(read(), [dict(started=123, mood="happy",
                                       total_time=10, waiting_time=2,
                                       total_bytes=100),
                                  dict(started=150, mood="errory",
                                       total_time=11, waiting_time=3,
                                       total_bytes=200),
                                      ])

        if False:
            # the current design opens the logfile exactly once, at process
            # start, in the faint hopes of surviving an exhaustion of available
            # file descriptors. This should be rethought.
            os.unlink(usage_logfile)

            t.recordUsage(started=200, result="lonely", total_bytes=300,
                          total_time=12, waiting_time=4)
            self.assertEqual(read(), [dict(started=200, mood="lonely",
                                           total_time=12, waiting_time=4,
                                           total_bytes=300)])

class StandardLogfile(unittest.TestCase):
    def test_log(self):
        # the default, when _blur_usage is None, will log to twistd.log
        t = Transit(blur_usage=None, usage_logfile=None, stats_file=None)
        with mock.patch("twisted.python.log.msg") as m:
            t.recordUsage(started=123, result="happy", total_bytes=100,
                        total_time=10, waiting_time=2)
        self.assertEqual(m.mock_calls, [mock.call(format="Transit.recordUsage {bytes}B", bytes=100)])

    def test_do_not_log(self):
        # the default, when _blur_usage is None, will log to twistd.log
        t = Transit(blur_usage=60, usage_logfile=None, stats_file=None)
        with mock.patch("twisted.python.log.msg") as m:
            t.recordUsage(started=123, result="happy", total_bytes=100,
                          total_time=10, waiting_time=2)
        self.assertEqual(m.mock_calls, [])
