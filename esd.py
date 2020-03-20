import logging
import sys
import socket
import socketserver
import threading

import Pyro4 as Pyro4

from conf import Conf, LoggingLevels
from consts import ADDR_ANY
from log import init_logging
from utils import abort

class EasyshareClientInfo:
    def __init__(self):
        self.address = None
        self.port = None

    def __str__(self):
        return self.address + ":" + str(self.port)

class EasyshareServer:
    def __init__(self):
        self.uri = None
        self.pyro_deamon = None
        self.discover_deamon = None
        self.sharings = {}
        self.name = socket.gethostname()
        self.clients = {}

    def setup(self):
        self.pyro_deamon = Pyro4.Daemon()
        self.uri = self.pyro_deamon.register(self).asString()
        logging.debug("Server registered at URI: %s", self.uri)

        self.discover_deamon = EasyshareDiscoverRequestListener(self.handle_discover_request)

    def add_share(self, name, path):
        logging.debug("SHARING %s as [%s]", path, name)
        self.sharings[name] = path


    def handle_discover_request(self, addr, data):
        logging.info("Handling DISCOVER request from %s", addr)

        discover_response = "{}\n{}\n{}".format(self.uri, self.name, self.pyro_deamon.sock.getsockname()[1])

        discovery_message = bytes(discover_response, encoding="UTF-8")

        resp_addr = (addr[0], Conf.DISCOVER_PORT_CLIENT)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        logging.debug("Sending DISCOVER response back to %s", resp_addr)
        sock.sendto(discovery_message, resp_addr)

    def start(self):
        logging.info("Starting DISCOVER deamon")
        self.discover_deamon.start()

        logging.info("Starting PYRO request loop")
        self.pyro_deamon.requestLoop()

    @Pyro4.expose
    def list_sharings(self):
        logging.trace("<< LIST (%s)", Pyro4.current_context.client_sock_addr)
        return self.sharings

    @Pyro4.expose
    def connect(self):
        logging.trace("<< CONNECT %s", Pyro4.current_context.client_sock_addr)
        client_identifier = Pyro4.current_context.client_sock_addr
        if not client_identifier in self.clients:
            client = EasyshareClientInfo()
            client.address = client_identifier[0]
            client.port = client_identifier[1]
            self.clients[client_identifier] = client
            logging.info("New client connected: %s", str(client))
        else:
            logging.warning("Client already connected: %s", self.clients[client_identifier])


    @Pyro4.expose
    def rpwd(self):
        logging.trace("<< RPWD (%s)", Pyro4.current_context.client_sock_addr)



class EasyshareDiscoverRequestListener(threading.Thread):

    def __init__(self, callback):
        threading.Thread.__init__(self)
        self.callback = callback  # (addr, data)

    def run(self) -> None:
        logging.trace("Starting DISCOVER listener")
        discover_server_addr = (ADDR_ANY, Conf.DISCOVER_PORT_SERVER)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(discover_server_addr)

        while True:
            data, addr = sock.recvfrom(1024)
            logging.debug("Received DISCOVER request from: %s", addr)
            self.callback(addr, data)


if __name__ == "__main__":
    init_logging(level=LoggingLevels.TRACE)

    server = EasyshareServer()
    server.setup()

    server.add_share("home", "/home/stefano")
    server.add_share("tmp", "/tmp")
    server.add_share("sources", "/home/stefano/Sources")

    server.start()
