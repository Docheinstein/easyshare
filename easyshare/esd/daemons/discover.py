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


_discover_daemon: Optional['DiscoverDaemon'] = None


class DiscoverDaemon:
    """
    Daemon that listens to discover requests from the client (by default on port 12019)
    and notifies the listeners about it.
    """

    def __init__(self, port: int):
        self._sock = SocketUdpIn(
            port=port
        )
        self._callbacks = set()


    def add_callback(self, callback: Callable[[Endpoint, bytes], None]):
        """ Adds a callback to invoke when a discover request is received """
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[Endpoint, bytes], None]):
        """ Removes a callback from the set of callbacks """
        self._callbacks.remove(callback)

    def endpoint(self):
        return self._sock.endpoint()

    def address(self):
        return self._sock.address()

    def port(self):
        return self._sock.port()

    def run(self):
        while True:
            log.d("Waiting for DISCOVER request to handle on port %d...", self._sock.port())
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
    """ Initializes the global discover daemon on the given port """
    global _discover_daemon
    _discover_daemon = DiscoverDaemon(port)


def get_discover_daemon() -> Optional[DiscoverDaemon]:
    """ Get the global discover daemon instance """
    return _discover_daemon
