import threading
from typing import Callable

from easyshare.consts.net import ADDR_ANY
from easyshare.shared.log import d
from easyshare.shared.endpoint import Endpoint
from easyshare.utils.net import socket_udp


class DiscoverDeamon(threading.Thread):

    def __init__(self, port: int, callback: Callable[[Endpoint, bytes], None]):
        threading.Thread.__init__(self)
        self.port = port
        self.callback = callback

    def run(self) -> None:
        d("Starting DISCOVER deamon")

        sock = socket_udp(ADDR_ANY, self.port)

        while True:
            data, client_endpoint = sock.recvfrom(1024)
            d("Received DISCOVER request from: %s", client_endpoint)
            self.callback(client_endpoint, data)
