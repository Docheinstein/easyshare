from typing import Callable

from easyshare.consts import ADDR_ANY
from easyshare.logging import get_logger
from easyshare.endpoint import Endpoint
from easyshare.tracing import trace_in
from easyshare.sockets import SocketUdpIn
from easyshare.utils.types import bytes_to_int

log = get_logger()

class DiscoverDaemon:

    def __init__(self,
                 port: int,
                 callback: Callable[[Endpoint, bytes], None]):
        self.sock = SocketUdpIn(
            address=ADDR_ANY,
            port=port
        )
        self._callback = callback

    def run(self):
        while True:
            log.d("Waiting for DISCOVER request to handle...")
            data, client_endpoint = self.sock.recv()

            trace_in(
                "DISCOVER {} ({})".format(str(data),  bytes_to_int(data)),
                ip=client_endpoint[0],
                port=client_endpoint[1]
            )

            log.i("Received DISCOVER request from: %s", client_endpoint)
            self._callback(client_endpoint, data)

    def endpoint(self):
        return self.sock.endpoint()