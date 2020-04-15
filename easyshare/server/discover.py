import threading
from typing import Callable

from easyshare.shared.log import d, v
from easyshare.shared.endpoint import Endpoint
from easyshare.shared.trace import trace_out, trace_in
from easyshare.socket.udp import SocketUdpIn


class DiscoverDeamon(threading.Thread):

    def __init__(self, port: int, callback: Callable[[Endpoint, bytes], None]):
        threading.Thread.__init__(self)
        self.port = port
        self.callback = callback

    def run(self) -> None:
        v("Starting DISCOVER deamon")

        sock = SocketUdpIn(port=self.port)

        while True:
            data, client_endpoint = sock.recv()

            trace_in(
                "DISCOVER {}".format(str(data)),
                ip=client_endpoint[0],
                port=client_endpoint[1]
            )

            d("Received DISCOVER request from: %s", client_endpoint)
            self.callback(client_endpoint, data)
