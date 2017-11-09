import os
from . import transit_server
from twisted.internet import reactor
from twisted.python import usage
from twisted.application.service import MultiService
from twisted.application.internet import (TimerService,
                                          StreamServerEndpointService)
from twisted.internet import endpoints

LONGDESC = """\
This plugin sets up a 'Transit Relay' server for magic-wormhole. This service
listens for TCP connections, finds pairs which present the same handshake, and
glues the two TCP sockets together.
"""

class Options(usage.Options):
    synopsis = "[--port=] [--log-fd] [--blur-usage=] [--usage-db=]"
    longdesc = LONGDESC

    optParameters = [
        ("port", "p", "tcp:4001", "endpoint to listen on"),
        ("blur-usage", None, None, "blur timestamps and data sizes in logs"),
        ("log-fd", None, None, "write JSON usage logs to this file descriptor"),
        ("usage-db", None, None, "record usage data (SQLite)"),
        ]

    def opt_blur_usage(self, arg):
        self["blur-usage"] = int(arg)


def makeService(config, reactor=reactor):
    ep = endpoints.serverFromString(reactor, config["port"]) # to listen
    log_file = (os.fdopen(int(config["log-fd"]), "w")
                if config["log-fd"] is not None
                else None)
    f = transit_server.Transit(blur_usage=config["blur-usage"],
                               log_file=log_file,
                               usage_db=config["usage-db"])
    parent = MultiService()
    StreamServerEndpointService(ep, f).setServiceParent(parent)
    TimerService(5*60.0, f.timerUpdateStats).setServiceParent(parent)
    return parent
