import time
import json

from twisted.python import log
from zope.interface import (
    implementer,
    Interface,
)


def create_usage_tracker(blur_usage, log_file, usage_db):
    """
    :param int blur_usage: see UsageTracker

    :param log_file: None or a file-like object to write JSON-encoded
        lines of usage information to.

    :param usage_db: None or an sqlite3 database connection

    :returns: a new UsageTracker instance configured with backends.
    """
    tracker = UsageTracker(blur_usage)
    if usage_db:
        tracker.add_backend(DatabaseUsageRecorder(usage_db))
    if log_file:
        tracker.add_backend(LogFileUsageRecorder(log_file))
    return tracker


class IUsageWriter(Interface):
    """
    Records actual usage statistics in some way
    """

    def record_usage(started=None, total_time=None, waiting_time=None, total_bytes=None, mood=None):
        """
        :param int started: timestemp when this connection began

        :param float total_time: total seconds this connection lasted

        :param float waiting_time: None or the total seconds one side
            waited for the other

        :param int total_bytes: the total bytes sent. In case the
            connection was concluded successfully, only one side will
            record the total bytes (but count both).

        :param str mood: the 'mood' of the connection
        """


@implementer(IUsageWriter)
class MemoryUsageRecorder:
    """
    Remebers usage records in memory.
    """

    def __init__(self):
        self.events = []

    def record_usage(self, started=None, total_time=None, waiting_time=None, total_bytes=None, mood=None):
        """
        IUsageWriter.
        """
        data = {
            "started": started,
            "total_time": total_time,
            "waiting_time": waiting_time,
            "total_bytes": total_bytes,
            "mood": mood,
        }
        self.events.append(data)


@implementer(IUsageWriter)
class LogFileUsageRecorder:
    """
    Writes usage records to a file. The records are written in JSON,
    one record per line.
    """

    def __init__(self, writable_file):
        self._file = writable_file

    def record_usage(self, started=None, total_time=None, waiting_time=None, total_bytes=None, mood=None):
        """
        IUsageWriter.
        """
        data = {
            "started": started,
            "total_time": total_time,
            "waiting_time": waiting_time,
            "total_bytes": total_bytes,
            "mood": mood,
        }
        self._file.write(json.dumps(data) + "\n")
        self._file.flush()


@implementer(IUsageWriter)
class DatabaseUsageRecorder:
    """
    Write usage records into a database
    """

    def __init__(self, db):
        self._db = db

    def record_usage(self, started=None, total_time=None, waiting_time=None, total_bytes=None, mood=None):
        """
        IUsageWriter.
        """
        self._db.execute(
            "INSERT INTO `usage`"
            " (`started`, `total_time`, `waiting_time`,"
            "  `total_bytes`, `result`)"
            " VALUES (?,?,?,?,?)",
            (started, total_time, waiting_time, total_bytes, mood)
        )
        # original code did "self._update_stats()" here, thus causing
        # "global" stats update on every connection update .. should
        # we repeat this behavior, or really only record every
        # 60-seconds with the timer?
        self._db.commit()


class UsageTracker(object):
    """
    Tracks usage statistics of connections
    """

    def __init__(self, blur_usage):
        """
        :param int blur_usage: None or the number of seconds to use as a
            window around which to blur time statistics (e.g. "60" means times
            will be rounded to 1 minute intervals). When blur_usage is
            non-zero, sizes will also be rounded into buckets of "one
            megabyte", "one gigabyte" or "lots"
        """
        self._backends = set()
        self._blur_usage = blur_usage
        if blur_usage:
            log.msg("blurring access times to %d seconds" % self._blur_usage)
        else:
            log.msg("not blurring access times")

    def add_backend(self, backend):
        """
        Add a new backend.

        :param IUsageWriter backend: the backend to add
        """
        self._backends.add(backend)

    def record(self, started, buddy_started, result, bytes_sent, buddy_bytes):
        """
        :param int started: timestamp when our connection started

        :param int buddy_started: None, or the timestamp when our
            partner's connection started (will be None if we don't yet
            have a partner).

        :param str result: a label for the result of the connection
            (one of the "moods").

        :param int bytes_sent: number of bytes we sent

        :param int buddy_bytes: number of bytes our partner sent
        """
        # ideally self._reactor.seconds() or similar, but ..
        finished = time.time()
        if buddy_started is not None:
            starts = [started, buddy_started]
            total_time = finished - min(starts)
            waiting_time = max(starts) - min(starts)
            total_bytes = bytes_sent + buddy_bytes
        else:
            total_time = finished - started
            waiting_time = None
            total_bytes = bytes_sent
            # note that "bytes_sent" should always be 0 here, but
            # we're recording what the state-machine remembered in any
            # case

        if self._blur_usage:
            started = self._blur_usage * (started // self._blur_usage)
            total_bytes = blur_size(total_bytes)

        # This is "a dict" instead of "kwargs" because we have to make
        # it into a dict for the log use-case and in-memory/testing
        # use-case anyway so this is less repeats of the names.
        self._notify_backends({
            "started": started,
            "total_time": total_time,
            "waiting_time": waiting_time,
            "total_bytes": total_bytes,
            "mood": result,
        })

    def update_stats(self, rebooted, updated, connected, waiting,
                     incomplete_bytes):
        """
        Update general statistics.
        """
        # in original code, this is only recorded in the database
        # .. perhaps a better way to do this, but ..
        for backend in self._backends:
            if isinstance(backend, DatabaseUsageRecorder):
                backend._db.execute("DELETE FROM `current`")
                backend._db.execute(
                    "INSERT INTO `current`"
                    " (`rebooted`, `updated`, `connected`, `waiting`,"
                    "  `incomplete_bytes`)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (int(rebooted), int(updated), connected, waiting,
                     incomplete_bytes)
                )

    def _notify_backends(self, data):
        """
        Internal helper. Tell every backend we have about a new usage record.
        """
        for backend in self._backends:
            backend.record_usage(**data)


def round_to(size, coarseness):
    return int(coarseness*(1+int((size-1)/coarseness)))


def blur_size(size):
    if size == 0:
        return 0
    if size < 1e6:
        return round_to(size, 10e3)
    if size < 1e9:
        return round_to(size, 1e6)
    return round_to(size, 100e6)
