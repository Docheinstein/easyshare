import select
from datetime import datetime
from typing import Callable, cast

from easyshare.common import TransferDirection, TransferProtocol
from easyshare.consts.net import ADDR_BROADCAST
from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.protocol.types import ServerInfoFull
from easyshare.sockets import SocketUdpIn, SocketUdpOut
from easyshare.tracing import trace_text, get_tracing_level, TRACING_TEXT
from easyshare.utils.json import btoj, j
from easyshare.utils.types import itob

log = get_logger(__name__)


class Discoverer:
    """
    Contacts the remote 'DiscoverDaemon's broadcasting a discover packet
    and notifies the 'response_handler' about the eventual discover responses.
    """

    def __init__(
            self, *,
            discover_port: int,
            discover_timeout: int,
            response_handler: Callable[[Endpoint, ServerInfoFull], bool],
            discover_addr: str = ADDR_BROADCAST):

        self._discover_addr = discover_addr
        self._discover_port = discover_port
        self._discover_timeout = discover_timeout
        self._response_handler = response_handler

    def discover(self) -> bool:
        """
        Sends a discover packet and waits for 'discover_timeout' seconds,
        notifying the response_handler in the meanwhile.
        Returns True if the discover finished (timedout) or False if it has been stopped.
        """
        discover_completed = True

        # Listening socket
        in_sock = SocketUdpIn()

        log.i("Client discover port: %d", in_sock.port())

        # Send discover
        discover_message = in_sock.port()
        discover_message_b = itob(discover_message, 2)
        out_sock = SocketUdpOut(broadcast=self._discover_addr == ADDR_BROADCAST)

        log.i("Sending DISCOVER to %s:%d",
              self._discover_addr,
              self._discover_port)

        if get_tracing_level() == TRACING_TEXT: # check for avoid json_pretty_str call
            trace_text(
                str(discover_message),
                sender=out_sock.endpoint(), receiver=(self._discover_addr, self._discover_port),
                direction=TransferDirection.OUT, protocol=TransferProtocol.UDP
            )

        out_sock.send(discover_message_b, self._discover_addr, self._discover_port,
                      trace=get_tracing_level() > TRACING_TEXT)

        # Listen
        discover_start_time = datetime.now()

        while True:
            # Calculate remaining time
            remaining_seconds = \
                self._discover_timeout - (datetime.now() - discover_start_time).total_seconds()

            if remaining_seconds < 0:
                # No more time to wait
                log.i("DISCOVER timeout elapsed (%.3f)", self._discover_timeout)
                break

            log.i("Waiting for %.3f seconds...", remaining_seconds)

            # Wait for message with select()
            read_fds, write_fds, error_fds = select.select([in_sock.sock], [], [], remaining_seconds)

            if in_sock.sock not in read_fds:
                continue

            # Ready for recv
            log.d("DISCOVER socket ready for recv")
            raw_resp, endpoint = in_sock.recv(trace=get_tracing_level() > TRACING_TEXT)

            log.i("Received DISCOVER response from: %s", endpoint)
            resp: ServerInfoFull = cast(ServerInfoFull, btoj(raw_resp))

            if get_tracing_level() == TRACING_TEXT:  # check for avoid json_pretty_str call
                trace_text(
                    j(resp),
                    sender=in_sock.endpoint(), receiver=endpoint,
                    direction=TransferDirection.IN, protocol=TransferProtocol.UDP
                )

            # Dispatch the response and check whether go on on listening
            go_ahead = self._response_handler(endpoint, resp)

            if not go_ahead:
                log.d("Stopping DISCOVER since handle_discover_response_callback returned false")
                discover_completed = False
                break

        log.i("Stopping DISCOVER listener")

        # Close sockets
        in_sock.close()
        out_sock.close()

        return discover_completed