import socket
import ssl

from typing import Tuple

from easyshare.consts.net import PORT_ANY, ADDR_ANY
from easyshare.shared.endpoint import Endpoint
from easyshare.socket.base import Socket, DEFAULT_SOCKET_BUFSIZE
from easyshare.utils.net import socket_tcp_out, socket_tcp_in


class SocketTcp(Socket):
    def send(self, data: bytes):
        self.sock.sendall(data)

    def recv(self, bufsize=DEFAULT_SOCKET_BUFSIZE) -> bytes:
        return self.sock.recv(bufsize)


class SocketTcpIn(SocketTcp):
    def __init__(self,
                 sock: socket.socket,
                 ssl_context: ssl.SSLContext = None,
                 ssl_server_side: bool = False):
        super().__init__(
            sock,
            ssl_context=ssl_context,
            ssl_server_side=ssl_server_side
        )


class SocketTcpOut(SocketTcp):
    def __init__(self,
                 address: str,
                 port: int, *,
                 timeout: float = None,
                 ssl_context: ssl.SSLContext = None,
                 ssl_server_side: bool = False):
        super().__init__(
            socket_tcp_out(address=address, port=port, timeout=timeout),
            ssl_context=ssl_context,
            ssl_server_side=ssl_server_side
        )


class SocketTcpAcceptor(Socket):

    def __init__(self, *,
                 address: str = ADDR_ANY,
                 port: int = PORT_ANY,
                 ssl_context: ssl.SSLContext = None):
        super().__init__(
            socket_tcp_in(address, port),
            ssl_context=ssl_context,
            ssl_server_side=True
        )

    def accept(self) -> Tuple[SocketTcp, Endpoint]:
        newsock, endpoint = self.sock.accept()
        # newsock is already ssl-protected if the acceptor was protected
        return SocketTcpIn(newsock), endpoint

