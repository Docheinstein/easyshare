import threading
from typing import Callable

from easyshare.logging import get_logger
from easyshare.shared.endpoint import Endpoint
from easyshare.tracing import trace_in
from easyshare.socket.udp import SocketUdpIn
from easyshare.utils.types import bytes_to_int

log = get_logger()

class DiscoverDaemon(threading.Thread):

    def __init__(self,
                 address: str,
                 port: int,
                 callback: Callable[[Endpoint, bytes], None]):
        threading.Thread.__init__(self)
        self.sock = SocketUdpIn(address=address, port=port)
        self._callback = callback

    def run(self) -> None:
        log.i("Starting DISCOVER deamon")

        while True:
            data, client_endpoint = self.sock.recv()

            trace_in(
                "DISCOVER {} ({})".format(str(data),  bytes_to_int(data)),
                ip=client_endpoint[0],
                port=client_endpoint[1]
            )

            log.i("Received DISCOVER request from: %s", client_endpoint)
            self._callback(client_endpoint, data)
