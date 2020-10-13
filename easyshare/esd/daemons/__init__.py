from abc import ABC, abstractmethod

from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.sockets import SocketTcpAcceptor, SocketUdpIn, SocketTcpIn
from easyshare.ssl import get_ssl_context

log = get_logger(__name__)


# ====================================
# ============== DAEMON ==============
# ====================================


class Daemon(ABC):
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

    @abstractmethod
    def kill(self):
        pass


class UdpDaemon(Daemon, ABC):
    def __init__(self, port: int, trace: bool):
        super().__init__()
        self._sock = SocketUdpIn(
            port=port
        )
        self._traced = trace

    def endpoint(self) -> Endpoint:
        return self._sock.endpoint()

    def run(self):
        while True:
            log.d(f"Waiting for UDP request to on port {self.port()}...")
            data, client_endpoint = self._sock.recv(trace=self._traced)

            log.i(f"Received UDP request from: {client_endpoint}")
            self._handle_message(data, client_endpoint)

    def kill(self):
        try:
            self._sock.close()
        except:
            log.wexception("Kill of daemon was not clean")

    @abstractmethod
    def _handle_message(self, data: bytes, client_endpoint: Endpoint):
        pass


class TcpDaemon(Daemon, ABC):
    def __init__(self, address: str, port: int):
        super().__init__()

        self._acceptor = SocketTcpAcceptor(
            address=address,
            port=port,
            ssl_context=get_ssl_context()
        )

    def endpoint(self) -> Endpoint:
        return self._acceptor.endpoint()

    def run(self):
        while True:
            log.d(f"Waiting for TCP connections on port {self.port()}...")
            sock = self._acceptor.accept()

            remote_endpoint = sock.remote_endpoint()

            if not remote_endpoint:
                log.w("Invalid endpoint, refusing connection")
                continue

            log.d(f"Received new valid TCP connection from {sock.remote_endpoint()}")
            self._handle_connection(sock)

    def kill(self):
        try:
            self._acceptor.close()
        except:
            log.wexception("Kill of daemon was not clean")

    @abstractmethod
    def _handle_connection(self, sock: SocketTcpIn):
        pass