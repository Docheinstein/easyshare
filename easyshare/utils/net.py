import enum
import socket
import re

from typing import Optional

from easyshare.consts.net import ADDR_ANY, PORT_ANY
from easyshare.logging import get_logger
from easyshare.utils.types import is_int


log = get_logger(__name__)


IP_REGEX = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


class SocketMode(enum.Enum):
    TCP = 0
    UDP = 1


class SocketDirection(enum.Enum):
    IN = 0
    OUT = 1


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


def is_valid_ip(ip: str) -> bool:
    return True if IP_REGEX.match(ip) else False


def is_valid_port(p: int) -> bool:
    return is_int(p) and 0 <= p <= 65535


def socket_udp_in(address: str = ADDR_ANY, port: int = PORT_ANY, *,
                  timeout: float = None) -> socket.socket:
    return _socket(SocketMode.UDP, SocketDirection.IN,
                   address=address, port=port,  timeout=timeout)


def socket_udp_out(*,
                   timeout: float = None, broadcast: bool = False) -> socket.socket:
    return _socket(SocketMode.UDP, SocketDirection.OUT,
                   timeout=timeout, broadcast=broadcast)


def socket_tcp_in(address: str, port: int, *,
                  timeout: float = None,
                  pending_connections: int = 1):
    return _socket(SocketMode.TCP, SocketDirection.IN,
                   address=address, port=port, timeout=timeout,
                   pending_connections=pending_connections)


def socket_tcp_out(address: str, port: int, *,
                   timeout: float = None):
    return _socket(SocketMode.TCP, SocketDirection.OUT,
                   address=address, port=port, timeout=timeout)


def _socket(mode: SocketMode, direction: SocketDirection,
            address: str = None, port: int = None,
            timeout: float = None, broadcast: bool = False,
            pending_connections: int = 1, reuse_addr: bool = True) -> Optional[socket.socket]:

    log.d("Creating raw_socket\n"
        "\tmode:            %s\n"
        "\tdirection:       %s\n"
        "\taddress:         %s\n"
        "\tport:            %s\n"  
        "\ttimeout:         %s\n"
        "\treuse_addr:      %s\n"
        "\tout bcast:       %s\n"  
        "\tin  no. allowed: %s",
          mode,
          direction,
          "<any>" if address == ADDR_ANY else address,
          "<any>" if port == PORT_ANY else port,
          timeout,
          reuse_addr,
          broadcast,
          str(pending_connections),
    )

    if mode == SocketMode.TCP:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)    # TCP
    elif mode == SocketMode.UDP:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)     # UDP
    else:
        return None

    if timeout:
        sock.settimeout(timeout)

    # in_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO,
    #                    struct.pack("LL", ceil(self.timeout), 0))

    if reuse_addr:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    if direction == SocketDirection.IN:
        sock.bind((address, port))
        if mode == SocketMode.TCP:
            sock.listen(pending_connections)
    elif direction == SocketDirection.OUT:
        if broadcast:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if mode == SocketMode.TCP:
            sock.connect((address, port))
    else:
        return None

    return sock

