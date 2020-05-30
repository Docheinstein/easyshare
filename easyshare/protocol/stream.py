from typing import Optional, Union

from easyshare.logging import get_logger
from easyshare.sockets import SocketTcp
from easyshare.utils.types import btoi, itob

log = get_logger(__name__)

class StreamClosedError(ValueError):
    pass

class Stream:
    def __init__(self, socket: SocketTcp):
        self._socket = socket
        self._is_open = True

    def is_open(self):
        return self._is_open

    def read(self) -> bytearray:
        # recv() the HEADER (2 bytes)

        header_data = self._socket.recv(4)
        self._ensure_data(header_data)

        header = btoi(header_data)

        payload_size = header

        log.d("stream.recv() - received header, payload will be: %d bytes", payload_size)

        if payload_size <= 0:
            log.d("Nothing to receive")
            return bytearray()

        # recv() the PAYLOAD (<header> bytes)
        payload_data = self._socket.recv(payload_size)
        self._ensure_data(header_data)

        log.d("stream.recv() - received payload of %d", len(payload_data))

        return payload_data

    def write(self, /, payload_data: Union[bytearray, bytes]):
        payload_size = len(payload_data)
        header = itob(payload_size, 4)

        data = bytearray()
        data += header
        data += payload_data

        log.d("stream.send() - sending %s", repr(data))

        self._socket.send(data)

    def close(self):
        self._socket.close()

    def _ensure_data(self, data):
        if data is None:
            log.d("Connection closed")
            self._is_open = False
            raise StreamClosedError("Connection closed")