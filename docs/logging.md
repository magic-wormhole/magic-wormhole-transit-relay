# Usage Logs

The transit relay does not emit or record any logging by default. By adding
option flags to the twist/twistd command line, you can enable one of two
different kinds of logs.

To avoid collecting information which could later be used to correlate
clients with external network traces, logged information can be "blurred".
This reduces the resolution of the data, retaining enough to answer questions
about how much the server is being used, but discarding fine-grained
timestamps or exact transfer sizes. The ``--blur-usage=`` option enables
this, and it takes an integer value (in seconds) to specify the desired time
window.

## Logging JSON Upon Each Connection

If --log-fd is provided, a line will be written to the given (numeric) file
descriptor after each connection is done. These events could be delivered to
a comprehensive logging system like XXX for offline analysis.

Each line will be a complete JSON object (starting with ``{``, ending with
``}\n``, and containing no internal newlines). The keys will be:

* ``started``: number, seconds since epoch
* ``total_time``: number, seconds from open to last close
* ``waiting_time``: number, seconds from start to 2nd side appearing, or null
* ``total_bytes``: number, total bytes relayed (sum of both directions)
* ``mood``: string, one of: happy, lonely, errory

A mood of ``happy`` means both sides gave a correct handshake. ``lonely``
means a second matching side never appeared (and thus ``waiting_time`` will
be null). ``errory`` means the first side gave an invalid handshake.

If --blur-usage= is provided, then ``started`` will be rounded to the given
time interval, and ``total_bytes`` will be rounded to a fixed set of buckets:

* file sizes less than 1MB: rounded to the next largest multiple of 10kB
* less than 1GB: multiple of 1MB
* 1GB or larger: multiple of 100MB

## Usage Database

If --usage-db= is provided, the server will maintain a SQLite database in the
given file. Current, recent, and historical usage data will be written to the
database, and external tools can query the DB for metrics: the munin plugins
in misc/ may be useful. Timestamps and sizes in this file will respect
--blur-usage. The four tables are:

``current`` contains a single row, with these columns:

* connected: number of paired connections
* waiting: number of not-yet-paired connections
* partal_bytes: bytes transmitted over not-yet-complete connections

``since_reboot`` contains a single row, with these columns:

* bytes: sum of ``total_bytes``
* connections: number of completed connections
* mood_happy: count of connections that finished "happy": both sides gave correct handshake
* mood_lonely: one side gave good handshake, other side never showed up
* mood_errory: one side gave a bad handshake

``all_time`` contains a single row, with these columns:

* bytes:
* connections:
* mood_happy:
* mood_lonely:
* mood_errory:

``usage`` contains one row per closed connection, with these columns:

* started: seconds since epoch, rounded to "blur time"
* total_time: seconds from first open to last close
* waiting_time: seconds from first open to second open, or None
* bytes: total bytes relayed (in both directions)
* result: (string) the mood: happy, lonely, errory

All tables will be updated after each connection is finished. In addition,
the ``current`` table will be updated at least once every 5 minutes.

## Logfiles for twistd

If daemonized by twistd, the server will write ``twistd.pid`` and
``twistd.log`` files as usual. By default ``twistd.log`` will only contain
startup, shutdown, and exception messages.

Setting ``--log-fd=1`` (file descriptor 1 is always stdout) will cause the
per-connection JSON lines to be interleaved with any messages sent to
Twisted's logging system. It may be better to use a different file
descriptor.
