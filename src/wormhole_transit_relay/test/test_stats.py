import os, io, json
from unittest import mock
from twisted.trial import unittest
from ..transit_server import Transit
from ..usage import create_usage_tracker
from .. import database

class DB(unittest.TestCase):

    def test_db(self):

        T = 1519075308.0

        class Timer:
            t = T
            def __call__(self):
                return self.t
        get_time = Timer()

        d = self.mktemp()
        os.mkdir(d)
        usage_db = os.path.join(d, "usage.sqlite")
        db = database.get_db(usage_db)
        t = Transit(
            create_usage_tracker(blur_usage=None, log_file=None, usage_db=db),
            get_time,
        )
        self.assertEqual(len(t.usage._backends), 1)
        usage = list(t.usage._backends)[0]

        get_time.t = T + 1
        usage.record_usage(started=123, mood="happy", total_bytes=100,
                           total_time=10, waiting_time=2)
        t.update_stats()

        self.assertEqual(db.execute("SELECT * FROM `usage`").fetchall(),
                         [dict(result="happy", started=123,
                               total_bytes=100, total_time=10, waiting_time=2),
                          ])
        self.assertEqual(db.execute("SELECT * FROM `current`").fetchone(),
                         dict(rebooted=T+0, updated=T+1,
                              incomplete_bytes=0,
                              waiting=0, connected=0))

        get_time.t = T + 2
        usage.record_usage(started=150, mood="errory", total_bytes=200,
                           total_time=11, waiting_time=3)
        t.update_stats()
        self.assertEqual(db.execute("SELECT * FROM `usage`").fetchall(),
                         [dict(result="happy", started=123,
                               total_bytes=100, total_time=10, waiting_time=2),
                          dict(result="errory", started=150,
                               total_bytes=200, total_time=11, waiting_time=3),
                          ])
        self.assertEqual(db.execute("SELECT * FROM `current`").fetchone(),
                         dict(rebooted=T+0, updated=T+2,
                              incomplete_bytes=0,
                              waiting=0, connected=0))

        get_time.t = T + 3
        t.update_stats()
        self.assertEqual(db.execute("SELECT * FROM `current`").fetchone(),
                         dict(rebooted=T+0, updated=T+3,
                              incomplete_bytes=0,
                              waiting=0, connected=0))

    def test_no_db(self):
        t = Transit(
            create_usage_tracker(blur_usage=None, log_file=None, usage_db=None),
            lambda: 0,
        )
        self.assertEqual(0, len(t.usage._backends))


class LogToStdout(unittest.TestCase):
    def test_log(self):
        # emit lines of JSON to log_file, if set
        log_file = io.StringIO()
        t = Transit(
            create_usage_tracker(blur_usage=None, log_file=log_file, usage_db=None),
            lambda: 0,
        )
        with mock.patch("time.time", return_value=133):
            t.usage.record(
                started=123,
                buddy_started=125,
                result="happy",
                bytes_sent=100,
                buddy_bytes=0,
            )
        self.assertEqual(json.loads(log_file.getvalue()),
                         {"started": 123, "total_time": 10,
                          "waiting_time": 2, "total_bytes": 100,
                          "mood": "happy"})

    def test_log_blurred(self):
        # if blurring is enabled, timestamps should be rounded to the
        # requested amount, and sizes should be rounded up too
        log_file = io.StringIO()
        t = Transit(
            create_usage_tracker(blur_usage=60, log_file=log_file, usage_db=None),
            lambda: 0,
        )

        with mock.patch("time.time", return_value=123 + 10):
            t.usage.record(
                started=123,
                buddy_started=125,
                result="happy",
                bytes_sent=11999,
                buddy_bytes=0,
            )
        print(log_file.getvalue())
        self.assertEqual(json.loads(log_file.getvalue()),
                         {"started": 120, "total_time": 10,
                          "waiting_time": 2, "total_bytes": 20000,
                          "mood": "happy"})

    def test_do_not_log(self):
        t = Transit(
            create_usage_tracker(blur_usage=60, log_file=None, usage_db=None),
            lambda: 0,
        )
        t.usage.record(
            started=123,
            buddy_started=124,
            result="happy",
            bytes_sent=11999,
            buddy_bytes=12,
        )
