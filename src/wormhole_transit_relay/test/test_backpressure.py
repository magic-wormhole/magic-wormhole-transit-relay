from io import (
    StringIO,
)
import sys
import shutil

from twisted.trial import unittest
from twisted.internet.interfaces import (
    IPullProducer,
)
from twisted.internet.protocol import (
    ProcessProtocol,
)
from twisted.internet.defer import (
    inlineCallbacks,
    Deferred,
)
from autobahn.twisted.websocket import (
    WebSocketClientProtocol,
    create_client_agent,
)
from zope.interface import implementer


class _CollectOutputProtocol(ProcessProtocol):
    """
    Internal helper. Collects all output (stdout + stderr) into
    self.output, and callback's on done with all of it after the
    process exits (for any reason).
    """
    def __init__(self):
        self.done = Deferred()
        self.running = Deferred()
        self.output = StringIO()

    def processEnded(self, reason):
        if not self.done.called:
            self.done.callback(self.output.getvalue())

    def outReceived(self, data):
        print(data.decode(), end="", flush=True)
        self.output.write(data.decode(sys.getfilesystemencoding()))
        if not self.running.called:
            if "on 8088" in self.output.getvalue():
                self.running.callback(None)

    def errReceived(self, data):
        print("ERR: {}".format(data.decode(sys.getfilesystemencoding())))
        self.output.write(data.decode(sys.getfilesystemencoding()))


def run_transit(reactor, proto, tcp_port=None, websocket_port=None):
    exe = shutil.which("twistd")
    args = [
        exe, "-n", "transitrelay",
    ]
    if tcp_port is not None:
        args.append("--port")
        args.append(tcp_port)
    if websocket_port is not None:
        args.append("--websocket")
        args.append(websocket_port)
    proc = reactor.spawnProcess(proto, exe, args)
    return proc



class Sender(WebSocketClientProtocol):
    """
    """

    def __init__(self, *args, **kw):
        WebSocketClientProtocol.__init__(self, *args, **kw)
        self.done = Deferred()
        self.got_ok = Deferred()

    def onMessage(self, payload, is_binary):
        print("onMessage")
        if not self.got_ok.called:
            if payload == b"ok\n":
                self.got_ok.callback(None)
        print("send: {}".format(payload.decode("utf8")))

    def onClose(self, clean, code, reason):
        print(f"close: {clean} {code} {reason}")
        self.done.callback(None)


class Receiver(WebSocketClientProtocol):
    """
    """

    def __init__(self, *args, **kw):
        WebSocketClientProtocol.__init__(self, *args, **kw)
        self.done = Deferred()
        self.first_message = Deferred()
        self.received = 0

    def onMessage(self, payload, is_binary):
        print("recv: {}".format(len(payload)))
        self.received += len(payload)
        if not self.first_message.called:
            self.first_message.callback(None)

    def onClose(self, clean, code, reason):
        print(f"close: {clean} {code} {reason}")
        self.done.callback(None)


class TransitWebSockets(unittest.TestCase):
    """
    Integration-style tests of the transit WebSocket relay, using the
    real reactor (and running transit as a subprocess).
    """

    @inlineCallbacks
    def test_buffer_fills(self):
        """
        A running transit relay stops accepting incoming data at a
        reasonable amount if the peer isn't reading. This test defines
        that as 'less than 100MiB' although in practice Twisted seems
        to stop before 10MiB.
        """
        from twisted.internet import reactor
        transit_proto = _CollectOutputProtocol()
        transit_proc = run_transit(reactor, transit_proto, websocket_port="tcp:8088")

        def cleanup_process():
            transit_proc.signalProcess("HUP")
            return transit_proto.done
        self.addCleanup(cleanup_process)

        yield transit_proto.running
        print("Transit running")

        agent = create_client_agent(reactor)
        side_a = yield agent.open("ws://localhost:8088", {}, lambda: Sender())
        side_b = yield agent.open("ws://localhost:8088", {}, lambda: Receiver())

        side_a.sendMessage(b"please relay aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa for side aaaaaaaaaaaaaaaa", True)
        side_b.sendMessage(b"please relay aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa for side bbbbbbbbbbbbbbbb", True)

        yield side_a.got_ok
        yield side_b.first_message

        # remove side_b's filedescriptor from the reactor .. this
        # means it will not read any more data
        reactor.removeReader(side_b.transport)

        # attempt to send up to 100MiB through side_a .. we should get
        # backpressure before that works which only manifests itself
        # as this producer not being asked to produce more
        max_data = 1024*1024*100 # 100MiB

        @implementer(IPullProducer)
        class ProduceMessages:
            def __init__(self, ws, on_produce):
                self._ws = ws
                self._sent = 0
                self._max = max_data
                self._on_produce = on_produce

            def resumeProducing(self):
                self._on_produce()
                if self._sent >= self._max:
                    self._ws.sendClose()
                    return
                data = b"a" * 1024*1024
                self._ws.sendMessage(data, True)
                self._sent += len(data)
                print("sent {}, total {}".format(len(data), self._sent))

        # our only signal is, "did our producer get asked to produce
        # more data" which it should do periodically. We want to stop
        # if we haven't seen a new data request for a while -- defined
        # as "more than 5 seconds".

        done = Deferred()
        last_produce = None
        timeout = 2  # seconds

        def asked_for_data():
            nonlocal last_produce
            last_produce = reactor.seconds()

        data = ProduceMessages(side_a, asked_for_data)
        side_a.transport.registerProducer(data, False)
        data.resumeProducing()

        def check_if_done():
            if last_produce is not None:
                if reactor.seconds() - last_produce > timeout:
                    done.callback(None)
                    return
            # recursive call to ourselves to check again soon
            reactor.callLater(.1, check_if_done)
        check_if_done()

        yield done

        mib = 1024*1024.0
        print("Sent {}MiB of {}MiB before backpressure".format(data._sent / mib, max_data / mib))
        self.assertTrue(data._sent < max_data, "Too much data sent")

        side_a.sendClose()
        side_b.sendClose()
        yield side_a.done
        yield side_b.done
