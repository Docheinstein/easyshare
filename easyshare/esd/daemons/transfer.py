from typing import Optional, Callable

from easyshare.logging import get_logger
from easyshare.sockets import SocketTcpAcceptor, SocketTcpIn
from easyshare.ssl import get_ssl_context

log = get_logger(__name__)


# =============================================
# ============== TRANSFER DAEMON ==============
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