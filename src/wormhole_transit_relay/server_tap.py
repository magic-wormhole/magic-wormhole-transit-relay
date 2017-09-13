from . import transit_server
from twisted.internet import reactor
from twisted.python import usage
from twisted.application.internet import StreamServerEndpointService
from twisted.internet import endpoints

LONGDESC = """\
This plugin sets up a 'Transit Relay' server for magic-wormhole. This service
listens for TCP connections, finds pairs which present the same handshake, and
glues the two TCP sockets together.

If --usage-logfile= is provided, a line will be written to the given file after
each connection is done. This line will be a complete JSON object (starting
with "{" and ending with "}\n"). The keys will be:

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

If --stats-file is provided, the server will periodically write a simple JSON
dictionary to that file (atomically), with cumulative usage data (since last
reboot, and all-time). This information is *not* blurred (the assumption is
that it will be overwritten on a regular basis, and is aggregated anyways). The
keys are:

* active.connected: number of paired connections
* active.waiting: number of not-yet-paired connections
* since_reboot.bytes: sum of 'total_bytes'
* since_reboot.total: number of completed connections
* since_reboot.moods: dict mapping mood string to number of connections
* all_time.bytes: same
* all_time.total
* all_time.moods

The server will write twistd.pid and twistd.log files as usual, if daemonized
by twistd. twistd.log will only contain startup, shutdown, and exception
messages. To record information about each connection, use --usage-logfile.
"""

class Options(usage.Options):
    #synopsis = "[--port=] [--usage-logfile=] [--blur-usage=] [--stats-json=]"
    longdesc = LONGDESC

    optParameters = [
        ("port", "p", "tcp:4001", "endpoint to listen on"),
        ("blur-usage", None, None, "blur timestamps and data sizes in logs"),
        ("usage-logfile", None, None, "record usage data (JSON lines)"),
        ("stats-file", None, None, "record usage in JSON format"),
        ]

    def opt_blur_usage(self, arg):
        self["blur_usage"] = int(arg)


def makeService(config, reactor=reactor):
    ep = endpoints.serverFromString(reactor, config["port"]) # to listen
    f = transit_server.Transit(blur_usage=config["blur-usage"],
                               usage_logfile=config["usage-logfile"],
                               stats_file=config["stats-file"])
    return StreamServerEndpointService(ep, f)
