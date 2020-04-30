import socket
import ssl

from abc import ABC
from typing import Optional, Union

from easyshare.logging import get_logger
from easyshare.shared.endpoint import Endpoint


log = get_logger(__name__)

DEFAULT_SOCKET_BUFSIZE = 4096


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
