import os
from twisted.internet import reactor
from twisted.python import usage
from twisted.application.service import MultiService
from twisted.application.internet import (TimerService,
                                          StreamServerEndpointService)
from twisted.internet import endpoints
from twisted.internet import protocol

from autobahn.twisted.websocket import WebSocketServerFactory

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
    tcp_ep = endpoints.serverFromString(reactor, config["port"]) # to listen
    # XXX FIXME proper websocket option
    ws_ep = endpoints.serverFromString(reactor, "tcp:4002") # to listen
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
    transit = transit_server.Transit(usage, reactor.seconds)
    tcp_factory = protocol.ServerFactory()
    tcp_factory.protocol = transit_server.TransitConnection

    ws_factory = WebSocketServerFactory("ws://localhost:4002")  # FIXME: url
    ws_factory.protocol = transit_server.WebSocketTransitConnection
    ws_factory.websocket_protocols = ["transit_relay"]

    tcp_factory.transit = transit
    ws_factory.transit = transit
    parent = MultiService()
    StreamServerEndpointService(tcp_ep, tcp_factory).setServiceParent(parent)
    StreamServerEndpointService(ws_ep, ws_factory).setServiceParent(parent)
    TimerService(5*60.0, transit.update_stats).setServiceParent(parent)
    return parent
