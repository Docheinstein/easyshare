from typing import Optional, Callable

from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.sockets import SocketUdpIn
from easyshare.tracing import trace_in
from easyshare.utils.types import bytes_to_int

log = get_logger(__name__)


# =============================================
# ============== DISCOVER DAEMON ==============
# =============================================


class DiscoverDaemon:

    def __init__(self, port: int):
        self._sock = SocketUdpIn(
            port=port
        )
        self._callbacks = set()


    def add_callback(self, callback: Callable[[Endpoint, bytes], None]):
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[Endpoint, bytes], None]):
        self._callbacks.remove(callback)

    def endpoint(self):
        return self._sock.endpoint()

    def run(self):
        while True:
            log.d("Waiting for DISCOVER request to handle on port %d...", self._sock.endpoint()[1])
            data, client_endpoint = self._sock.recv()

            trace_in(
                "DISCOVER {} ({})".format(str(data),  bytes_to_int(data)),
                ip=client_endpoint[0],
                port=client_endpoint[1]
            )

            log.i("Received DISCOVER request from: %s", client_endpoint)
            for cb in self._callbacks:
                cb(client_endpoint, data)


def init_discover_daemon(port: int):
    global _discover_daemon
    _discover_daemon = DiscoverDaemon(port)


def get_discover_daemon() -> Optional[DiscoverDaemon]:
    return _discover_daemon
