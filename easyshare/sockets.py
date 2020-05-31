import socket
import ssl

from abc import ABC
from typing import Optional, Union, Tuple

from easyshare.consts.net import ADDR_BROADCAST, ADDR_ANY, PORT_ANY
from easyshare.logging import get_logger
from easyshare.endpoint import Endpoint
from easyshare.utils.net import socket_udp_in, socket_udp_out, socket_tcp_out, socket_tcp_in
from easyshare.utils.ssl import sslify_socket

log = get_logger(__name__)


DEFAULT_SOCKET_BUFSIZE = 4096


# Smarter wrappers of socket.socket, SSL aware

# ================================================
# ================ BASE SOCKETS ==================
# ================================================

class Socket(ABC):
    def __init__(self, sock: socket.socket):
        self.sock: Union[socket.socket, ssl.SSLSocket] = sock

    def endpoint(self) -> Endpoint:
        return self.sock.getsockname()

    def address(self) -> str:
        return self.endpoint()[0]

    def port(self) -> int:
        return self.endpoint()[1]

    def is_ssl_enabled(self) -> bool:
        return isinstance(self.sock, ssl.SSLSocket)

    def ssl_certificate(self) -> Optional[bytes]:
        return self.sock.getpeercert(binary_form=True) if self.is_ssl_enabled() else None

    def close(self, both=True, rd=False, wr=False):
        if both:
            self.sock.close()
        else:
            if rd and wr:
                self.sock.shutdown(socket.SHUT_RDWR)
            elif rd:
                self.sock.shutdown(socket.SHUT_RD)
            elif wr:
                self.sock.shutdown(socket.SHUT_WR)
            else:
                log.w("Nothing to close for this socket, invalid params?")


# ================================================
# ================ UDP SOCKETS ===================
# ================================================


class SocketUdp(Socket):
    def recv(self, length=DEFAULT_SOCKET_BUFSIZE) -> Tuple[bytes, Endpoint]:
        return self.sock.recvfrom(length)

    def send(self, data: bytes, address: str, port: int) -> int:
        return self.sock.sendto(data, (address, port))

    def broadcast(self, data: bytes, port: int) -> int:
        return self.sock.sendto(data, (ADDR_BROADCAST, port))


class SocketUdpIn(SocketUdp):
    def __init__(self, address: str = ADDR_ANY, port: int = PORT_ANY, *,
                 timeout: float = None):
        super().__init__(socket_udp_in(address, port, timeout=timeout))


class SocketUdpOut(SocketUdp):
    def __init__(self, *, timeout: float = None, broadcast: bool = False):
        super().__init__(socket_udp_out(timeout=timeout, broadcast=broadcast))



# ================================================
# ================ TCP SOCKETS ===================
# ================================================


class SocketTcp(Socket):
    def __init__(self, sock: socket.socket):
        super().__init__(sock)
        self._recv_buffer = bytearray()

    def send(self, data: bytes):
        self.sock.sendall(data)

    def recv(self, length: int) -> Optional[bytearray]:
        while True:
            remaining_length = length - len(self._recv_buffer)
            if remaining_length <= 0:
                break

            log.d("recv() - waiting for %d bytes", remaining_length)
            recvlen = min(remaining_length, DEFAULT_SOCKET_BUFSIZE)
            data = self.sock.recv(recvlen)
            log.d("recv(): %s", repr(data))

            if len(data) == 0:
                log.d("EOF")
                return None

            self._recv_buffer += data

        read = self._recv_buffer[0:length]
        self._recv_buffer = self._recv_buffer[length:]
        return read

    # def recv_into(self, bufsize, buffer: bytearray = None) -> int:
    #     return self.sock.recv_into(buffer, bufsize)

    def remote_endpoint(self) -> Optional[Endpoint]:
        try:
            return self.sock.getpeername()
        except:
            log.exception("Cannot determinate remote endpoint")
            return None

    def remote_address(self) -> str:
        return self.remote_endpoint()[0]

    def remote_port(self) -> int:
        return self.remote_endpoint()[1]

class SocketTcpIn(SocketTcp):
    def __init__(self,
                 sock: socket.socket):
        super().__init__(sock) # already sslified by the acceptor, eventually

class SocketTcpOut(SocketTcp):
    def __init__(self,
                 address: str,
                 port: int, *,
                 timeout: float = None,
                 ssl_context: Optional[ssl.SSLContext] = None):
        super().__init__(
            sslify_socket(
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
            sslify_socket(
                socket_tcp_in(address, port),
                ssl_context=ssl_context,
                server_side=True
            )
        )

    def accept(self, timeout: float = None) -> Optional[SocketTcpIn]:
        if timeout:
            self.sock.settimeout(timeout)

        newsock, endpoint = self.sock.accept()
        sock = SocketTcpIn(newsock)

        return sock  # sock is already ssl-protected if the acceptor was protected