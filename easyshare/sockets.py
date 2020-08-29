import socket
import ssl

from abc import ABC
from typing import Optional, Union, Tuple

from easyshare.common import TransferDirection, TransferProtocol
from easyshare.consts.net import ADDR_BROADCAST, ADDR_ANY, PORT_ANY
from easyshare.logging import get_logger
from easyshare.endpoint import Endpoint
from easyshare.tracing import trace_bin
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
        try:
            return self.sock.getsockname()
        except:
            log.exception("Cannot determinate remote endpoint")
            return "0.0.0.0", 0  # fallback

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

    def set_timeout(self, timeout: float = None):
        self.sock.settimeout(timeout)


    def get_timeout(self) -> float:
        return self.sock.gettimeout()


# ================================================
# ================ UDP SOCKETS ===================
# ================================================


class SocketUdp(Socket):
    def recv(self, length=DEFAULT_SOCKET_BUFSIZE, trace: bool = True) -> Tuple[bytes, Endpoint]:
        data, sender = self.sock.recvfrom(length)

        if trace:
            trace_bin(data,
                      sender=sender, receiver=self.endpoint(),
                      direction=TransferDirection.IN, protocol=TransferProtocol.UDP)

        return data, sender

    def send(self, data: bytes, address: str, port: int, trace: bool = True) -> int:
        if trace:
            trace_bin(data,
                      sender=self.endpoint(), receiver=(address, port),
                      direction=TransferDirection.OUT, protocol=TransferProtocol.UDP)

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

    def send(self, data: bytes, trace: bool = True):
        if trace:
            trace_bin(data,
                   sender=self.endpoint(), receiver=self.remote_endpoint(),
                   direction=TransferDirection.OUT, protocol=TransferProtocol.TCP)

        self.sock.sendall(data)

    def recv(self, length: int, trace: bool = True) -> Optional[bytearray]:
        while True:
            remaining_length = length - len(self._recv_buffer)
            if remaining_length <= 0:
                break

            recvlen = min(remaining_length, DEFAULT_SOCKET_BUFSIZE)
            data = self.sock.recv(recvlen)

            if len(data) == 0:
                return None

            self._recv_buffer += data

        data = self._recv_buffer[0:length]
        self._recv_buffer = self._recv_buffer[length:]  # might have read more
                                                        # than the required length
        if trace:
            trace_bin(data,
                   sender=self.remote_endpoint(), receiver=self.endpoint(),
                   direction=TransferDirection.IN, protocol=TransferProtocol.TCP)

        return data

    def remote_endpoint(self) -> Optional[Endpoint]:
        try:
            return self.sock.getpeername()
        except:
            log.exception("Cannot determinate remote endpoint")
            return "0.0.0.0", 0  # fallback

    def remote_address(self) -> str:
        return self.remote_endpoint()[0]

    def remote_port(self) -> int:
        return self.remote_endpoint()[1]

class SocketTcpIn(SocketTcp):
    def __init__(self,
                 sock: socket.socket,
                 timeout: float = None):
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