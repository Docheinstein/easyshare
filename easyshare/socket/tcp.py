import socket

from typing import Tuple

from easyshare.consts.net import PORT_ANY, ADDR_ANY
from easyshare.shared.endpoint import Endpoint
from easyshare.socket.base import Socket, DEFAULT_SOCKET_BUFSIZE
from easyshare.utils.net import socket_tcp_out, socket_tcp_in


class SocketTcp(Socket):
    def __init__(self):
        super().__init__()

    def send(self, data: bytes):
        self.sock.sendall(data)

    def recv(self, bufsize=DEFAULT_SOCKET_BUFSIZE) -> bytes:
        return self.sock.recv(bufsize)


class SocketTcpIn(SocketTcp):
    def __init__(self, sock: socket.socket):
        super().__init__()
        self.sock = sock


class SocketTcpOut(SocketTcp):
    def __init__(self, address: str, port: int, *,
                 timeout: float = None):
        super().__init__()
        self.sock = socket_tcp_out(address=address, port=port, timeout=timeout)


class SocketTcpAcceptor(Socket):
    def __init__(self, *,
                 address: str = ADDR_ANY, port: int = PORT_ANY):
        super().__init__()
        self.sock = socket_tcp_in(address, port)

    def accept(self) -> Tuple[SocketTcp, Endpoint]:
        newsock, endpoint = self.sock.accept()
        return SocketTcpIn(newsock), endpoint

