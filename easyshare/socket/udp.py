from typing import Tuple

from easyshare.consts.net import ADDR_ANY, PORT_ANY, ADDR_BROADCAST
from easyshare.shared.endpoint import Endpoint
from easyshare.socket.base import Socket, DEFAULT_SOCKET_BUFSIZE
from easyshare.utils.net import socket_udp_in, socket_udp_out


class SocketUdp(Socket):
    def __init__(self):
        super().__init__()

    def recv(self, bufsize=DEFAULT_SOCKET_BUFSIZE) -> Tuple[bytes, Endpoint]:
        return self.sock.recvfrom(bufsize)

    def send(self, data: bytes, address: str, port: int) -> int:
        return self.sock.sendto(data, (address, port))

    def broadcast(self, data: bytes, port: int) -> int:
        return self.sock.sendto(data, (ADDR_BROADCAST, port))


class SocketUdpIn(SocketUdp):
    def __init__(self, address: str = ADDR_ANY, port: int = PORT_ANY, *,
                 timeout: float = None):
        super().__init__()
        self.sock = socket_udp_in(address, port, timeout=timeout)


class SocketUdpOut(SocketUdp):
    def __init__(self, *, timeout: float = None, broadcast: bool = False):
        super().__init__()
        self.sock = socket_udp_out(timeout=timeout, broadcast=broadcast)

