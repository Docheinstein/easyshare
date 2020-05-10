import select
from datetime import datetime
from typing import Callable

from easyshare.consts import ADDR_BROADCAST
from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.protocol import Response, is_data_response
from easyshare.protocol import ServerInfoFull
from easyshare.tracing import trace_out, trace_in
from easyshare.sockets import SocketUdpIn, SocketUdpOut
from easyshare.utils.json import bytes_to_json, j
from easyshare.utils.types import int_to_bytes

log = get_logger(__name__)


class Discoverer:

    DEFAULT_TIMEOUT = 2

    def __init__(
            self, *,
            server_discover_port: int,
            response_handler: Callable[[Endpoint, ServerInfoFull], bool],
            server_discover_addr: str = ADDR_BROADCAST):

        self.server_discover_addr = server_discover_addr
        self.server_discover_port = server_discover_port
        self.response_handler = response_handler

    def discover(self, timeout: float = DEFAULT_TIMEOUT):
        # Listening socket
        in_sock = SocketUdpIn()

        log.i("Client discover port: %d", in_sock.port())

        # Send discover
        discover_message_raw = in_sock.port()
        discover_message = int_to_bytes(discover_message_raw, 2)
        out_sock = SocketUdpOut(broadcast=self.server_discover_addr == ADDR_BROADCAST)

        log.i("Sending DISCOVER to %s:%d",
              self.server_discover_addr,
              self.server_discover_port)

        trace_out(
            "DISCOVER {} ({})".format(str(discover_message), discover_message_raw),
            ip=self.server_discover_addr,
            port=self.server_discover_port
        )

        out_sock.send(discover_message, self.server_discover_addr, self.server_discover_port)

        # Listen
        discover_start_time = datetime.now()

        while True:
            # Calculate remaining time
            remaining_seconds = \
                timeout - (datetime.now() - discover_start_time).total_seconds()

            if remaining_seconds < 0:
                # No more time to wait
                log.i("DISCOVER timeout elapsed (%.3f)", timeout)
                break

            log.i("Waiting for %.3f seconds...", remaining_seconds)

            # Wait for message with select()
            read_fds, write_fds, error_fds = select.select([in_sock.sock], [], [], remaining_seconds)

            if in_sock.sock not in read_fds:
                continue

            # Ready for recv
            log.d("DISCOVER socket ready for recv")
            raw_resp, endpoint = in_sock.recv()

            log.i("Received DISCOVER response from: %s", endpoint)
            resp: Response = bytes_to_json(raw_resp)

            trace_in(
                "DISCOVER\n{}".format(j(resp)),
                ip=endpoint[0],
                port=endpoint[1]
            )

            if not is_data_response(resp):
                log.w("Invalid DISCOVER response")
                continue

            # Dispatch the response and check whether go on on listening
            go_ahead = self.response_handler(endpoint, resp.get("data"))

            if not go_ahead:
                log.d("Stopping DISCOVER since handle_discover_response_callback returned false")
                break

        log.i("Stopping DISCOVER listener")

        # Close sockets
        in_sock.close()
        out_sock.close()
