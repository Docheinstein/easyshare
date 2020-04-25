import socket
import ssl

from abc import ABC
from typing import Optional, Union

from easyshare.shared.endpoint import Endpoint
from easyshare.shared.log import w


DEFAULT_SOCKET_BUFSIZE = 4096


class Socket(ABC):
    def __init__(self,
                 sock: socket.socket,
                 ssl_context: ssl.SSLContext = None,
                 ssl_server_side: bool = False):
        self.sock: Union[socket.socket, ssl.SSLSocket] = sock

        if ssl_context:
            self.sock = ssl_context.wrap_socket(self.sock,
                                                server_side=ssl_server_side)

    def endpoint(self) -> Endpoint:
        return self.sock.getsockname()

    def address(self) -> str:
        return self.endpoint()[0]

    def port(self) -> int:
        return self.endpoint()[1]

    def is_ssl_enabled(self) -> bool:
        return isinstance(self.sock, ssl.SSLSocket)

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
                w("Nothing to close for this socket, invalid params?")
