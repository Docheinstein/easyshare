from typing import Union

from easyshare.common import TransferDirection, TransferProtocol
from easyshare.logging import get_logger
from easyshare.sockets import SocketTcp
from easyshare.tracing import trace_bin_payload, get_tracing_level, TRACING_BIN_ALL, trace_bin_all
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

    def read(self, *, trace: bool = True) -> bytearray:
        do_trace_bin_all = get_tracing_level() == TRACING_BIN_ALL

        # recv() the HEADER (2 bytes)

        header_data = self._socket.recv(4, tracer=trace_bin_all if trace and do_trace_bin_all else False)
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


        if trace and not do_trace_bin_all:
            trace_bin_payload(payload_data,
                          sender=self._socket.remote_endpoint(), receiver=self._socket.endpoint(),
                          direction=TransferDirection.IN, protocol=TransferProtocol.TCP)

        return payload_data

    def write(self, payload_data: Union[bytearray, bytes], *, trace: bool = True):
        do_trace_bin_all = get_tracing_level() == TRACING_BIN_ALL

        payload_size = len(payload_data)
        header = itob(payload_size, 4)

        data = bytearray()
        data += header
        data += payload_data

        log.d("stream.send() - sending %s", repr(data))

        if trace and not do_trace_bin_all:
            trace_bin_payload(payload_data,
                              sender=self._socket.endpoint(), receiver=self._socket.remote_endpoint(),
                              direction=TransferDirection.OUT, protocol=TransferProtocol.TCP)

        self._socket.send(data, tracer=trace_bin_all if trace and do_trace_bin_all else False)

    def close(self):
        self._socket.close()
        self._is_open = False

    def _ensure_data(self, data):
        if data is None:
            log.d("Connection closed")
            self._is_open = False
            raise StreamClosedError("Connection closed")
