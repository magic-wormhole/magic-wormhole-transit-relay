import os
from twisted.internet import reactor
from twisted.python import usage
from twisted.application.service import MultiService
from twisted.application.internet import (TimerService,
                                          StreamServerEndpointService)
from twisted.internet import endpoints
from . import transit_server
from .server_state import create_usage_tracker
from .increase_rlimits import increase_rlimits
from .database import get_db

LONGDESC = """\
This plugin sets up a 'Transit Relay' server for magic-wormhole. This service
listens for TCP connections, finds pairs which present the same handshake, and
glues the two TCP sockets together.
"""

class Options(usage.Options):
    synopsis = "[--port=] [--log-fd] [--blur-usage=] [--usage-db=]"
    longdesc = LONGDESC

    optParameters = [
        ("port", "p", "tcp:4001:interface=\:\:", "endpoint to listen on"),
        ("blur-usage", None, None, "blur timestamps and data sizes in logs"),
        ("log-fd", None, None, "write JSON usage logs to this file descriptor"),
        ("usage-db", None, None, "record usage data (SQLite)"),
        ]

    def opt_blur_usage(self, arg):
        self["blur-usage"] = int(arg)


def makeService(config, reactor=reactor):
    increase_rlimits()
    ep = endpoints.serverFromString(reactor, config["port"]) # to listen
    log_file = (
        os.fdopen(int(config["log-fd"]), "w")
        if config["log-fd"] is not None
        else None
    )
    db = None if config["usage-db"] is None else get_db(config["usage-db"])
    usage = create_usage_tracker(
        blur_usage=config["blur-usage"],
        log_file=log_file,
        usage_db=db,
    )
    ##factory = transit_server.Transit(usage, reactor.seconds)
    factory = transit_server.WebSocketTransit(usage, reactor.seconds)
    parent = MultiService()
    StreamServerEndpointService(ep, factory).setServiceParent(parent)
    TimerService(5*60.0, factory.update_stats).setServiceParent(parent)
    return parent
