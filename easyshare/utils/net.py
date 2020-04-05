import socket
from typing import Optional

from easyshare.consts.net import ADDR_ANY, PORT_ANY
from easyshare.shared.log import e
from easyshare.utils.types import is_int


def get_primary_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


def is_valid_port(o: int) -> bool:
    return is_int(o) and 0 < o < 65535


def socket_udp_in(address: str = ADDR_ANY, port: int = PORT_ANY, *,
                  timeout: float = None) -> socket.socket:
    return _socket_udp(address, port, ingoing=True, timeout=timeout)


def socket_udp_out(timeout: float = None, broadcast: bool = False) -> socket.socket:
    return _socket_udp(outgoing=True, timeout=timeout, broadcast=broadcast)


def _socket_udp(address: str = None, port: int = None,
               ingoing: bool = False, outgoing: bool = False,
               timeout: float = None, broadcast: bool = False) -> Optional[socket.socket]:
    if not (ingoing ^ outgoing):
        e("Socket creation failed, invalid parameteres")
        return None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    if timeout:
        sock.settimeout(timeout)

    # in_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO,
    #                    struct.pack("LL", ceil(self.timeout), 0))

    if ingoing:
        sock.bind((address, port))

    if outgoing:
        if broadcast:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    return sock

