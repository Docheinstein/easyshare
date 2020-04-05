import socket

from abc import ABC
from typing import Optional

from easyshare.shared.endpoint import Endpoint
from easyshare.shared.log import w


class Socket(ABC):
    def __init__(self):
        self.sock: socket.socket = Optional[None]

    def endpoint(self) -> Endpoint:
        return self.sock.getsockname()

    def address(self) -> str:
        return self.endpoint()[0]

    def port(self) -> int:
        return self.endpoint()[1]

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
