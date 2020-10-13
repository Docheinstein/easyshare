from typing import Union

from easyshare.logging import get_logger
from easyshare.sockets import SocketTcp
from easyshare.utils.types import btoi, itob

log = get_logger(__name__)

class StreamClosedError(ValueError):
    pass

class TcpStream:
    def __init__(self, socket: SocketTcp):
        self._socket = socket
        self._is_open = True

    def endpoint(self):
        return self._socket.endpoint()

    def remote_endpoint(self):
        return self._socket.remote_endpoint()

    def is_open(self):
        return self._is_open

    def read(self, *, timeout: float = None, trace: bool = True) -> bytearray:
        # Eventually set the socket timeout for the read()s
        prev_timeout = self._socket.get_timeout()

        if timeout:
            self._socket.set_timeout(timeout)

        # recv() the HEADER (2 bytes)
        header_data = self._socket.recv(4, trace=False) # don't trace the header

        self._ensure_data(header_data)

        header = btoi(header_data)

        payload_size = header

        log.d(f"stream.recv() - received header, payload will be: {payload_size} bytes")

        if payload_size <= 0:
            log.d("Nothing to receive")
            return bytearray()

        # recv() the PAYLOAD (<header> bytes)
        payload_data = self._socket.recv(payload_size, trace=trace)

        self._ensure_data(header_data)

        log.d(f"stream.recv() - received payload of {len(payload_data)}")

        if timeout:
            self._socket.set_timeout(prev_timeout)

        return payload_data

    def write(self, payload_data: Union[bytearray, bytes], *,
              timeout: float = None, trace: bool = True):
        # Eventually set the socket timeout for the write()s

        prev_timeout = self._socket.get_timeout()

        if timeout:
            self._socket.set_timeout(timeout)

        header = itob(len(payload_data), 4)

        self._socket.send(header, trace=False) # don't trace the header

        log.d(f"stream.send() - sending {repr(payload_data)}")

        self._socket.send(payload_data, trace=trace)

        if timeout:
            self._socket.set_timeout(prev_timeout)

    def close(self):
        self._socket.close()
        self._is_open = False

    def _ensure_data(self, data):
        if data is None:
            log.d("Connection closed")
            self._is_open = False
            raise StreamClosedError("Connection closed")
