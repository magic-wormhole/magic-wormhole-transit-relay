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
from .usage import create_usage_tracker
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
        ("websocket", "w", None, "endpoint to listen for WebSocket connections"),
        ("websocket-url", "u", None, "WebSocket URL (derived from endpoint if not provided)"),
        ("blur-usage", None, None, "blur timestamps and data sizes in logs"),
        ("log-fd", None, None, "write JSON usage logs to this file descriptor"),
        ("usage-db", None, None, "record usage data (SQLite)"),
        ]

    def opt_blur_usage(self, arg):
        self["blur-usage"] = int(arg)


def makeService(config, reactor=reactor):
    increase_rlimits()
    tcp_ep = endpoints.serverFromString(reactor, config["port"]) # to listen
    ws_ep = (
        endpoints.serverFromString(reactor, config["websocket"])
        if config["websocket"] is not None
        else None
    )
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
    tcp_factory.log_requests = False

    if ws_ep is not None:
        ws_url = config["websocket-url"]
        if ws_url is None:
            # we're using a "private" attribute here but I don't see
            # any useful alternative unless we also want to parse
            # Twisted endpoint-strings.
            ws_url = "ws://localhost:{}/".format(ws_ep._port)
            print("Using WebSocket URL '{}'".format(ws_url))
        ws_factory = WebSocketServerFactory(ws_url)
        ws_factory.protocol = transit_server.WebSocketTransitConnection
        ws_factory.transit = transit
        ws_factory.log_requests = False

    tcp_factory.transit = transit
    parent = MultiService()
    StreamServerEndpointService(tcp_ep, tcp_factory).setServiceParent(parent)
    if ws_ep is not None:
        StreamServerEndpointService(ws_ep, ws_factory).setServiceParent(parent)
    TimerService(5*60.0, transit.update_stats).setServiceParent(parent)
    return parent
