import select
from datetime import datetime
from typing import Callable

from easyshare.protocol.response import Response, is_data_response
from easyshare.shared.log import d, w, v
from easyshare.shared.endpoint import Endpoint
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.shared.trace import trace_out
from easyshare.socket.udp import SocketUdpIn, SocketUdpOut
from easyshare.utils.json import bytes_to_json
from easyshare.utils.types import int_to_bytes


class Discoverer:

    DEFAULT_TIMEOUT = 2

    def __init__(
            self,
            server_discover_port: int,
            response_handler: Callable[[Endpoint, ServerInfo], bool]):
        self.server_discover_port = server_discover_port
        self.response_handler = response_handler

    def discover(self, timeout: float = DEFAULT_TIMEOUT):
        # Listening socket
        in_sock = SocketUdpIn()

        d("Client discover port: %d", in_sock.port())

        # Send discover
        discover_message = int_to_bytes(in_sock.port(), 2)
        out_sock = SocketUdpOut(broadcast=True)

        d("Broadcasting DISCOVER on port %d", self.server_discover_port)

        trace_out(
            ip="",
            port=self.server_discover_port,
            name="broadcast",
            what="DISCOVER {}".format(str(discover_message))
        )

        out_sock.broadcast(discover_message, self.server_discover_port)

        # Listen
        discover_start_time = datetime.now()

        while True:
            # Calculate remaining time
            remaining_seconds = \
                timeout - (datetime.now() - discover_start_time).total_seconds()

            if remaining_seconds < 0:
                # No more time to wait
                d("DISCOVER timeout elapsed (%.3f)", timeout)
                break

            d("Waiting for %.3f seconds...", remaining_seconds)

            # Wait for message with select()
            read_fds, write_fds, error_fds = select.select([in_sock.sock], [], [], remaining_seconds)

            if in_sock.sock not in read_fds:
                continue

            # Ready for recv
            d("DISCOVER socket ready for recv")
            raw_resp, endpoint = in_sock.recv()

            d("Received DISCOVER response from: %s", endpoint)
            resp: Response = bytes_to_json(raw_resp)

            if not is_data_response(resp):
                w("Invalid DISCOVER response")
                continue

            # Dispatch the response and check whether go on on listening
            go_ahead = self.response_handler(endpoint, resp.get("data"))

            if not go_ahead:
                d("Stopping DISCOVER since handle_discover_response_callback returned false")
                break

        v("Stopping DISCOVER listener")

        # Close sockets
        in_sock.close()
        out_sock.close()
