from typing import Optional, Callable

from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.sockets import SocketTcpAcceptor, SocketTcpIn
from easyshare.ssl import get_ssl_context

log = get_logger(__name__)


# =============================================
# ============== TRANSFER DAEMON ==============
# =============================================


_transfer_daemon: Optional['TransferDaemon'] = None


class TransferDaemon:
    """
    Transfer daemon that listens to new requests from clients (by default on port 12021)
    add notifies the listeners about the incoming connections.
    The sense is that the listeners of this daemon (a 'TransferService', e.g. get or put)
    should handle the new socket (after some check, e.g. IP provenience).
    """

    def __init__(self, port: int):
        self._acceptor = SocketTcpAcceptor(
            port=port,
            ssl_context=get_ssl_context()
        )
        self._callbacks = set()

    def add_callback(self, callback: Callable[[SocketTcpIn], bool]):
        """
        Adds a callback to invoke when a connection on the transfer socket is received.
        If a listener wants to handle the socket, it should return True.
        If all the listeners returns False, the socket is closed (nobody handled it).
        """
        self._callbacks.add(callback)
        log.d("Added callback to transfer daemon; current size = %d", len(self._callbacks))

    def remove_callback(self, callback: Callable[[SocketTcpIn], bool]):
        """ Removes a callback from the set of callbacks """
        self._callbacks.remove(callback)
        log.d("Removed callback from transfer daemon; current size = %d", len(self._callbacks))

    def endpoint(self) -> Endpoint:
        return self._acceptor.endpoint()

    def address(self) -> str:
        return self._acceptor.address()

    def port(self) -> int:
        return self._acceptor.port()

    def run(self):
        while True:
            log.d("Waiting for transfer connections on port %d...", self._acceptor.port())
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
    """ Initializes the global transfer daemon on the given port """
    global _transfer_daemon
    _transfer_daemon = TransferDaemon(port)


def get_transfer_daemon() -> Optional[TransferDaemon]:
    """ Get the global transfer daemon instance """
    return _transfer_daemon