from . import transit_server
from twisted.internet import reactor
from twisted.python import usage
from twisted.application.internet import (TimerService,
                                          StreamServerEndpointService)
from twisted.internet import endpoints

LONGDESC = """\
This plugin sets up a 'Transit Relay' server for magic-wormhole. This service
listens for TCP connections, finds pairs which present the same handshake, and
glues the two TCP sockets together.

If --log-stdout is provided, a line will be written to stdout after each
connection is done. This line will be a complete JSON object (starting with
"{", ending with "}\n", and containing no internal newlines). The keys will
be:

* 'started': number, seconds since epoch
* 'total_time': number, seconds from open to last close
* 'waiting_time': number, seconds from start to 2nd side appearing, or null
* 'total_bytes': number, total bytes relayed (sum of both directions)
* 'mood': string, one of: happy, lonely, errory

A mood of "happy" means both sides gave a correct handshake. "lonely" means a
second matching side never appeared (and thus 'waiting_time' will be null).
"errory" means the first side gave an invalid handshake.

If --blur-usage= is provided, then 'started' will be rounded to the given time
interval, and 'total_bytes' will be rounded as well.

If --usage-db= is provided, the server will maintain a SQLite database in the
given file. Current, recent, and historical usage data will be written to the
database, and external tools can query the DB for metrics: the munin plugins
in misc/ may be useful. Timestamps and sizes in this file will respect
--blur-usage. The four tables are:

"current" contains a single row, with these columns:

* connected: number of paired connections
* waiting: number of not-yet-paired connections
* partal_bytes: bytes transmitted over not-yet-complete connections

"since_reboot" contains a single row, with these columns:

* bytes: sum of 'total_bytes'
* connections: number of completed connections
* mood_happy: count of connections that finished "happy": both sides gave correct handshake
* mood_lonely: one side gave good handshake, other side never showed up
* mood_errory: one side gave a bad handshake

"all_time" contains a single row, with these columns:

* bytes:
* connections:
* mood_happy:
* mood_lonely:
* mood_errory:

"usage" contains one row per closed connection, with these columns:

* started: seconds since epoch, rounded to "blur time"
* total_time: seconds from first open to last close
* waiting_time: seconds from first open to second open, or None
* bytes: total bytes relayed (in both directions)
* result: (string) the mood: happy, lonely, errory

All tables will be updated after each connection is finished. In addition,
the "current" table will be updated at least once every 5 minutes.

If daemonized by twistd, the server will write twistd.pid and twistd.log
files as usual. By default twistd.log will only contain startup, shutdown,
and exception messages. Adding --log-stdout will add per-connection JSON
lines to twistd.log.
"""

class Options(usage.Options):
    #synopsis = "[--port=] [--log-stdout] [--blur-usage=] [--usage-db=]"
    longdesc = LONGDESC

    optFlags = {
        ("log-stdout", None, "write JSON usage logs to stdout"),
        }
    optParameters = [
        ("port", "p", "tcp:4001", "endpoint to listen on"),
        ("blur-usage", None, None, "blur timestamps and data sizes in logs"),
        ("usage-db", None, None, "record usage data (SQLite)"),
        ]

    def opt_blur_usage(self, arg):
        self["blur_usage"] = int(arg)


def makeService(config, reactor=reactor):
    ep = endpoints.serverFromString(reactor, config["port"]) # to listen
    f = transit_server.Transit(blur_usage=config["blur-usage"],
                               log_stdout=config["log-stdout"],
                               usage_db=config["usage-db"])
    parent = service.MultiService()
    StreamServerEndpointService(ep, f).setServiceParent(parent)
    TimerService(5.0, f.timerUpdateStats).setServiceParent(parent)
    return parent
