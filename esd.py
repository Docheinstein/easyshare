import json
import logging
import sys
import socket
import socketserver
import threading
import time
from typing import Dict

import Pyro4 as Pyro4

import netutils
from conf import Conf, LoggingLevels
from consts import ADDR_ANY
from defs import EasyshareServerIface, EasyshareServerResponseCode
from log import init_logging

class EasyshareClientContext:
    def __init__(self):
        self.address = None
        self.port = None
        self.sharing = None
        self.pwd = ""

    def __str__(self):
        return self.address + ":" + str(self.port)

class EasyshareServer(EasyshareServerIface):

    def __init__(self):
        self.uri = None
        self.pyro_deamon = None
        self.discover_deamon = None
        self.sharings: Dict[str, str] = {}
        self.name = socket.gethostname()
        self.ip = netutils.get_primary_ip()
        self.clients: Dict[(str, int), EasyshareClientContext] = {}

    def setup(self):
        self.pyro_deamon = Pyro4.Daemon(host=self.ip)
        self.uri = self.pyro_deamon.register(self).asString()
        logging.debug("Server registered at URI: %s", self.uri)

        self.discover_deamon = EasyshareDiscoverRequestListener(self.handle_discover_request)

    def add_share(self, name, path):
        logging.debug("SHARING %s as [%s]", path, name)
        self.sharings[name] = path


    def handle_discover_request(self, addr, data):
        logging.info("Handling DISCOVER request from %s", addr)

        deamon_addr_port = self.pyro_deamon.sock.getsockname()

        discover_response_content = {
            "uri": self.uri,
            "name": self.name,
            "address": deamon_addr_port[0],
            "port": deamon_addr_port[1],
            "sharings": list(self.sharings.keys())
        }

        logging.debug("Computing DISCOVER response content:\n%s",
                      json.dumps(discover_response_content, indent=4))

        discovery_response_data = bytes(json.dumps(discover_response_content, separators=(",", ":")), encoding="UTF-8")

        resp_addr = (addr[0], Conf.DISCOVER_PORT_CLIENT)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        logging.debug("Sending DISCOVER response back to %s", resp_addr)
        sock.sendto(discovery_response_data, resp_addr)

    def start(self):
        logging.info("Starting DISCOVER deamon")
        self.discover_deamon.start()

        logging.info("Starting PYRO request loop")
        self.pyro_deamon.requestLoop()

    @Pyro4.expose
    def list(self):
        logging.trace("<< LIST (%s)", Pyro4.current_context.client_sock_addr)
        time.sleep(0.5)
        return self.sharings

    @Pyro4.expose
    def open(self, sharing):
        if not sharing:
            return EasyshareServerResponseCode.INVALID_COMMAND_SYNTAX

        if sharing not in self.sharings:
            return EasyshareServerResponseCode.SHARING_NOT_FOUND

        logging.trace("<< OPEN %s", Pyro4.current_context.client_sock_addr)
        client_identifier = Pyro4.current_context.client_sock_addr
        if not client_identifier in self.clients:
            client = EasyshareClientContext()
            client.address = client_identifier[0]
            client.port = client_identifier[1]
            client.sharing = sharing
            self.clients[client_identifier] = client
            logging.info("New client connected (%s) to resource %s", str(client), client.sharing)
            return EasyshareServerResponseCode.OK
        else:
            logging.warning("Client already connected: %s", self.clients[client_identifier])
            # TODO: switch sharing

    def close(self):
        pass

    @Pyro4.expose
    def rpwd(self):
        logging.trace("<< RPWD (%s)", Pyro4.current_context.client_sock_addr)

        client_identifier = Pyro4.current_context.client_sock_addr
        if not client_identifier in self.clients:
            return EasyshareServerResponseCode.NOT_CONNECTED

        client = self.clients[client_identifier]
        return client.pwd
        # return -2

    @Pyro4.expose
    def rcd(self, path):
        if not path:
            return EasyshareServerResponseCode.INVALID_COMMAND_SYNTAX

        client_identifier = Pyro4.current_context.client_sock_addr
        if not client_identifier in self.clients:
            return EasyshareServerResponseCode.NOT_CONNECTED

        logging.trace("<< RCD %s (%s)", path, Pyro4.current_context.client_sock_addr)

        client = self.clients[client_identifier]

        # TODO: ensure path existence
        client.pwd = path
        return EasyshareServerResponseCode.OK



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
