from typing import Optional, Union

from easyshare.logging import get_logger
from easyshare.sockets import SocketTcp
from easyshare.tracing import trace_in
from easyshare.utils.types import bytes_to_int, int_to_bytes

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
        self._ensure(header_data)

        header = bytes_to_int(header_data)

        payload_size = header

        log.d("Received an header, payload will be: %d bytes", payload_size)

        if payload_size <= 0:
            log.d("Nothing to receive")
            return bytearray()

        # recv() the PAYLOAD (<header> bytes)
        payload_data = self._socket.recv(payload_size)
        self._ensure(header_data)

        log.d("Received payload of %d", len(payload_data))

        return payload_data

    def write(self, /, payload_data: Union[bytearray, bytes]):
        payload_size = len(payload_data)
        header = int_to_bytes(payload_size, 4)

        data = bytearray()
        data += header
        data += payload_data

        self._socket.send(data)

    def _ensure(self, data):
        if data is None:
            log.d("Connection closed")
            self._is_open = False
            raise StreamClosedError("Connection closed")