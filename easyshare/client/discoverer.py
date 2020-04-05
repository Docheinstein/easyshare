import select
import socket
import struct
from datetime import datetime
from math import ceil
from typing import Callable

from easyshare.consts.net import ADDR_ANY, PORT_ANY
from easyshare.shared.log import d, t
from easyshare.shared.endpoint import Endpoint
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.protocol.response import Response
from easyshare.utils.json import bytes_to_json_object


class Discoverer:

    DEFAULT_TIMEOUT = 2

    def __init__(
            self,
            server_discover_port: int,
            response_handler: Callable[[Endpoint, ServerInfo], bool],
            timeout=DEFAULT_TIMEOUT):
        self.server_discover_port = server_discover_port
        self.response_handler = response_handler
        self.timeout = timeout

    def discover(self):
        # Listening socket
        in_addr = (ADDR_ANY, PORT_ANY)

        in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        in_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO,
                           struct.pack("LL", ceil(self.timeout), 0))
        in_sock.bind(in_addr)

        in_port = in_sock.getsockname()[1]

        d("Client discover port: %d", in_port)

        # Send discover
        out_addr = (socket.INADDR_BROADCAST, self.server_discover_port)
        discover_message = in_port.to_bytes(2, "big")

        out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        out_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        d("Sending DISCOVER on port %d message: %s",
          self.server_discover_port, str(discover_message))
        out_sock.sendto(discover_message, out_addr)

        # Listen
        discover_start_time = datetime.now()

        remaining_seconds = self.timeout

        while remaining_seconds > 0:
            t("Waiting for %.3f seconds...", remaining_seconds)

            read_fds, write_fds, error_fds = select.select([in_sock], [], [], remaining_seconds)

            if in_sock in read_fds:
                t("DISCOVER socket ready for recv")
                response, addr = in_sock.recvfrom(1024)
                d("Received DISCOVER response from: %s", addr)
                json_response: Response = bytes_to_json_object(response)

                if json_response["success"] and json_response["data"]:
                    go_ahead = self.response_handler(addr, json_response["data"])

                    if not go_ahead:
                        t("Stopping DISCOVER since handle_discover_response_callback returned false")
                        return
            else:
                t("DISCOVER timeout elapsed (%.3f)", self.timeout)

            remaining_seconds = \
                self.timeout - (datetime.now() - discover_start_time).total_seconds()

        d("Stopping DISCOVER listener")
