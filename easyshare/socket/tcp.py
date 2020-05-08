import socket
import ssl

from typing import Tuple, Optional

from easyshare.consts.net import PORT_ANY, ADDR_ANY
from easyshare.logging import get_logger
from easyshare.shared.endpoint import Endpoint
from easyshare.socket.base import Socket, DEFAULT_SOCKET_BUFSIZE
from easyshare.utils.net import socket_tcp_out, socket_tcp_in
from easyshare.utils.ssl import wrap_socket


log = get_logger(__name__)

class SocketTcp(Socket):
    def send(self, data: bytes):
        self.sock.sendall(data)

    def recv(self, bufsize=DEFAULT_SOCKET_BUFSIZE) -> bytes:
        return self.sock.recv(bufsize)

    def remote_endpoint(self) -> Endpoint:
        return self.sock.getpeername()

    def remote_address(self) -> str:
        return self.remote_endpoint()[0]

    def remote_port(self) -> int:
        return self.remote_endpoint()[1]


class SocketTcpIn(SocketTcp):
    def __init__(self,
                 sock: socket.socket,
                 ssl_context: Optional[ssl.SSLContext] = None):
        super().__init__(
            wrap_socket(
                sock,
                ssl_context=ssl_context,
                server_side=True
            )
        )


class SocketTcpOut(SocketTcp):
    def __init__(self,
                 address: str,
                 port: int, *,
                 timeout: float = None,
                 ssl_context: Optional[ssl.SSLContext] = None):
        super().__init__(
            wrap_socket(
                socket_tcp_out(address=address, port=port, timeout=timeout),
                ssl_context=ssl_context,
                server_hostname=address
            )
        )


class SocketTcpAcceptor(Socket):

    def __init__(self,
                 address: str = ADDR_ANY,
                 port: int = PORT_ANY, *,
                 ssl_context: Optional[ssl.SSLContext] = None):
        super().__init__(
            wrap_socket(
                socket_tcp_in(address, port),
                ssl_context=ssl_context,
                server_hostname=address
            )
        )

    def accept(self, timeout: float = None) -> Optional[SocketTcpIn]:
        if timeout:
            self.sock.settimeout(timeout)

        newsock, endpoint = self.sock.accept()
        sock = SocketTcpIn(newsock)

        assert sock.remote_endpoint() == endpoint

        return sock # sock is already ssl-protected if the acceptor was protected