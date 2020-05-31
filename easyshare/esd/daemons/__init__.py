from abc import ABC, abstractmethod
from typing import Callable

from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.sockets import SocketTcpAcceptor, SocketUdpIn, SocketTcp
from easyshare.ssl import get_ssl_context

log = get_logger(__name__)


# ====================================
# ============== DAEMON ==============
# ====================================


class Daemon(ABC):
    def __init__(self):
        self._callbacks = {}

    @abstractmethod
    def add_callback(self, callback, once):
        pass

    @abstractmethod
    def remove_callback(self, callback):
        pass

    @abstractmethod
    def endpoint(self) -> Endpoint:
        pass

    def address(self) -> str:
        return self.endpoint()[0]

    def port(self) -> int:
        return self.endpoint()[1]

    @abstractmethod
    def run(self):
        pass


class UdpDaemon(Daemon):
    def __init__(self, port: int, trace: bool):
        super().__init__()
        self._sock = SocketUdpIn(
            port=port
        )
        self._traced = trace

    def add_callback(self, callback: Callable[[Endpoint, bytes], bool], once: bool = False):
        self._callbacks[callback] = once
        log.d("Added callback to %s; current size = %d", self.__class__.__name__, len(self._callbacks))

    def remove_callback(self, callback: Callable[[Endpoint, bytes], bool]):
        self._callbacks.pop(callback, None)
        log.d("Removed callback from %s; current size = %d", self.__class__.__name__, len(self._callbacks))

    def endpoint(self) -> Endpoint:
        return self._sock.endpoint()


    def run(self):
        while True:
            log.d("Waiting for UDP request to on port %d...", self.port())
            data, client_endpoint = self._sock.recv(trace=self._traced)

            self._trace_hook(data, client_endpoint)

            log.i("Received UDP request from: %s", client_endpoint)

            # Ask the listeners (callbacks) whether they want to handle
            # this incoming message
            # If someone wants to handle it, we stop notifying the others

            remove_cb = None

            for cb, once in self._callbacks.items():
                handled = cb(client_endpoint, data)
                if handled:
                    log.d("Request has been managed by a listener")
                    if once:
                        log.d("Removing listener since once=True")
                        remove_cb = cb
                    break
            else:
                log.w("No listener wants to handle the request")
                # Nothing to close, UDP

            if remove_cb:
                self.remove_callback(remove_cb)

    def _trace_hook(self, data: bytes, client_endpoint: Endpoint):
        pass

class TcpDaemon(Daemon):
    def __init__(self, address: str, port: int):
        super().__init__()

        self._acceptor = SocketTcpAcceptor(
            address=address,
            port=port,
            ssl_context=get_ssl_context()
        )

    def add_callback(self, callback: Callable[[SocketTcp], bool], once: bool = False):
        self._callbacks[callback] = once
        log.d("Added callback to %s; current size = %d", self.__class__.__name__, len(self._callbacks))

    def remove_callback(self, callback: Callable[[SocketTcp], bool]):
        self._callbacks.pop(callback, None)
        log.d("Removed callback from %s; current size = %d", self.__class__.__name__, len(self._callbacks))

    def endpoint(self) -> Endpoint:
        return self._acceptor.endpoint()

    def run(self):
        while True:
            log.d("Waiting for TCP connections on port %d...", self.port())
            sock = self._acceptor.accept()
            remote_endpoint = sock.remote_endpoint()

            if not remote_endpoint:
                log.w("Invalid endpoint, refusing connection")
                continue

            log.d("Received new valid TCP connection from %s", sock.remote_endpoint())

            # Ask the listeners (callbacks) whether they want to handle
            # this incoming connection
            # If someone wants to handle it, we stop notifying the others
            # If nobody wants to handle it, we close the socket

            remove_cb = None

            for cb, once in self._callbacks.items():
                handled = cb(sock)
                if handled:
                    log.d("Socket has been managed by a listener")
                    if once:
                        log.d("Removing listener since once=True")
                        remove_cb = cb
                    break
            else:
                log.w("No listener wants to handle the socket, closing it")
                sock.close()

            if remove_cb:
                self.remove_callback(remove_cb)