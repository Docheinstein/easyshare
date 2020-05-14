from typing import Optional, Any, Tuple, Callable

import Pyro5.api as pyro
from Pyro5 import socketutil

from easyshare.logging import get_logger
from easyshare.ssl import get_ssl_context
from easyshare.utils.str import uuid
from easyshare.consts.net import ADDR_ANY
from easyshare.logging import get_logger
from easyshare.endpoint import Endpoint
from easyshare.tracing import trace_in
from easyshare.sockets import SocketUdpIn, SocketTcpAcceptor, SocketTcpIn
from easyshare.utils.types import bytes_to_int

log = get_logger(__name__)


# =============================================
# ================ PYRO DAEMON ================
# =============================================


_pyro_daemon: Optional['EsdDaemon'] = None
_transfer_daemon: Optional['TransferDaemon'] = None
_discover_daemon: Optional['DiscoverDaemon'] = None

class EsdDaemon(pyro.Daemon):
    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.disconnection_callbacks = set()

    def add_disconnection_callback(self, callback):
        self.disconnection_callbacks.add(callback)

    def remove_disconnection_callback(self, callback):
        self.disconnection_callbacks.remove(callback)

    def publish(self, obj: Any, uid: str = None) -> Tuple[str, str]:  # uri, uid
        obj_id = uid or uuid()
        log.i("Publishing pyro object %s with uid='%s'",
              obj.__class__.__name__, obj_id[:6] + "..." + obj_id[-6:])

        return str(super().register(obj, objectId=obj_id)), obj_id

    def unpublish(self, obj_id):
        log.i("Unpublishing pyro object with uid='%s'",
              obj_id[:6] + "..." + obj_id[-6:])
        self.unregister(obj_id)

    def clientDisconnect(self, conn: socketutil.SocketConnection):
        log.i("Client disconnected: %s", conn.sock.getpeername())
        log.d("Notifying %d listeners", len(self.disconnection_callbacks))
        for cb in self.disconnection_callbacks:
            cb(conn)


def init_pyro_daemon(address: str,
                     port: int = 0,
                     nat_address: str = None,
                     nat_port: int = None):
    global _pyro_daemon
    log.i("Initializing pyro daemon\n"
          "\tAddress: %s\n"
          "\tPort: %s\n"
          "\tNat address: %s\n"
          "\tNat port: %s",
          address, port, nat_address, nat_port
      )
    _pyro_daemon = EsdDaemon(
        host=address,
        port=port,
        nathost=nat_address,
        natport=nat_port
    )


def get_pyro_daemon() -> Optional[EsdDaemon]:
    return _pyro_daemon


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

# =============================================
# ============== DISCOVER DAEMON ==============
# =============================================


class TransferDaemon:

    def __init__(self, port: int):
        self._acceptor = SocketTcpAcceptor(
            port=port,
            ssl_context=get_ssl_context()
        )
        self._callbacks = set()

    def add_callback(self, callback: Callable[[SocketTcpIn], bool]):
        self._callbacks.add(callback)
        log.d("Added callback to transfer daemon; current size = %d", len(self._callbacks))

    def remove_callback(self, callback: Callable[[SocketTcpIn], bool]):
        self._callbacks.remove(callback)
        log.d("Removed callback from transfer daemon; current size = %d", len(self._callbacks))

    def endpoint(self):
        return self._acceptor.endpoint()

    def run(self):
        while True:
            log.d("Waiting for transfer connections on port %d...", self._acceptor.endpoint()[1])
            sock = self._acceptor.accept()
            log.d("Received new connection from %s", sock.remote_endpoint())

            # Ask the listeners (callbacks) whether they want to handle
            # this incoming connection
            # If someone wants to handle it, we stop notifying the others
            # If nobody wants to handle it, we close the socket

            remove_cb = None

            for cb in self._callbacks:
                handled = cb(sock)
                if handled:
                    log.d("Socket has been managed by a listener")
                    remove_cb = cb
                    break
            else:
                log.w("No listeners wants to handle the socket, closing it")
                sock.close()

            if remove_cb:
                self.remove_callback(remove_cb)


def init_transfer_daemon(port: int):
    global _transfer_daemon
    _transfer_daemon = TransferDaemon(port)


def get_transfer_daemon() -> Optional[TransferDaemon]:
    return _transfer_daemon