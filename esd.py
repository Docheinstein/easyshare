import json
import logging
import os
import sys
import socket
import socketserver
import threading
import time
from typing import Dict, Optional, Tuple

import Pyro4 as Pyro4

import netutils
from conf import Conf, LoggingLevels
from consts import ADDR_ANY
from defs import ServerIface, Address
from log import init_logging
from server_response import ServerResponse, build_server_response_success, build_server_response_error, ErrorCode


class ClientContext:
    def __init__(self):
        self.address = None
        self.port = None
        self.sharing = None
        self.rpwd = ""

    def __str__(self):
        return self.address + ":" + str(self.port)

class Server(ServerIface):

    def __init__(self):
        self.uri = None
        self.pyro_deamon = None
        self.discover_deamon = None
        self.sharings: Dict[str, str] = {}
        self.name = socket.gethostname()
        self.ip = netutils.get_primary_ip()
        self.clients: Dict[(str, int), ClientContext] = {}

    def setup(self):
        self.pyro_deamon = Pyro4.Daemon(host=self.ip)
        self.uri = self.pyro_deamon.register(self).asString()
        logging.debug("Server registered at URI: %s", self.uri)

        self.discover_deamon = DiscoverRequestListener(self.handle_discover_request)

    def add_share(self, name, path):
        logging.debug("SHARING %s as [%s]", path, name)
        self.sharings[name] = path

    def handle_discover_request(self, addr, data):
        logging.info("Handling DISCOVER request from %s", addr)

        deamon_addr_port = self.pyro_deamon.sock.getsockname()

        response_data = {
            "uri": self.uri,
            "name": self.name,
            "address": deamon_addr_port[0],
            "port": deamon_addr_port[1],
            "sharings": list(self.sharings.keys())
        }

        response = build_server_response_success(response_data)

        discover_response = bytes(json.dumps(response, separators=(",", ":")), encoding="UTF-8")

        resp_addr = (addr[0], Conf.DISCOVER_PORT_CLIENT)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        logging.debug("Sending DISCOVER response back to %s\n%s", resp_addr, json.dumps(response, indent=4))
        sock.sendto(discover_response, resp_addr)

    def start(self):
        logging.info("Starting DISCOVER deamon")
        self.discover_deamon.start()

        logging.info("Starting PYRO request loop")
        self.pyro_deamon.requestLoop()

    @Pyro4.expose
    def list(self):
        logging.info("<< LIST %s", str(self._current_request_addr()))
        time.sleep(0.5)
        return build_server_response_success(self.sharings)

    @Pyro4.expose
    def open(self, sharing):
        if not sharing:
            return build_server_response_error(ErrorCode.INVALID_COMMAND_SYNTAX)

        if sharing not in self.sharings:
            return build_server_response_error(ErrorCode.SHARING_NOT_FOUND)

        client_identifier = self._current_request_addr()
        logging.info("<< OPEN %s %s", sharing, str(client_identifier))

        client = self._current_request_client()
        if not client:
            client = ClientContext()
            client.address = client_identifier[0]
            client.port = client_identifier[1]
            client.sharing = sharing
            self.clients[client_identifier] = client
            logging.info("New client connected (%s) to sharing %s", str(client), client.sharing)
        else:
            client.sharing = sharing
            logging.info("Already connected client (%s) changed sharing to %s", str(client), client.sharing)

        return build_server_response_success()

    def close(self):
        pass

    @Pyro4.expose
    def rpwd(self) -> ServerResponse:
        # NOT NEEDED
        logging.info("<< RPWD %s", str(self._current_request_addr()))

        client = self._current_request_client()
        if not client:
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        return build_server_response_success(client.rpwd)
        # return client.rpwd

    @Pyro4.expose
    def rcd(self, path) -> ServerResponse:
        if not path:
            return build_server_response_error(ErrorCode.INVALID_COMMAND_SYNTAX)

        client = self._current_request_client()
        if not client:
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        logging.info("<< RCD %s (%s)", path, str(client))

        base_sharing = self.sharings[client.sharing]

        logging.debug("Base sharing: %s", self.sharings[client.sharing])
        logging.debug("Current rpwd: %s", client.rpwd)

        if path.startswith(os.sep):
            # If path begins with / it refers to the root of the current sharing
            new_rpwd = path.lstrip(os.sep)
        else:
            # Otherwise it refers to a subdirectory starting from the current rpwd
            new_rpwd = os.path.join(client.rpwd, path)

        logging.debug("New rpwd: %s", new_rpwd)
        new_rpwd = os.path.normpath(new_rpwd)
        logging.debug("New rpwd normalized: %s", new_rpwd)

        full_path = os.path.join(base_sharing, new_rpwd)
        logging.debug("New path: %s", full_path)
        full_path = os.path.normpath(full_path)
        logging.debug("New path normalized: %s", full_path)

        logging.debug("Checking validity of new path %s", full_path)
        logging.debug("Common path: %s", os.path.commonpath([full_path, base_sharing]))

        if base_sharing != os.path.commonpath([full_path, base_sharing]):
            return build_server_response_error(ErrorCode.INVALID_PATH)
        # TODO: fix^^
        logging.debug("Checking existence of new path %s", full_path)

        if not os.path.isdir(full_path):
            logging.error("Path does not exists")
            return build_server_response_error(ErrorCode.INVALID_PATH)

        logging.debug("Path exists, success")

        trail_rpwd = full_path.split(base_sharing)[1]

        client.rpwd = trail_rpwd.lstrip(os.sep)
        logging.debug("Trail path: %s", client.rpwd)

        return build_server_response_success(client.rpwd)

    @Pyro4.expose
    def rls(self) -> ServerResponse:
        client = self._current_request_client()
        if not client:
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        logging.info("<< RLS (%s)",  str(client))

        try:
            full_path = self._client_path(client)

            logging.debug("Going to ls on %s", full_path)

            if not self._is_path_valid_for_client(full_path, client):
                return build_server_response_error(ErrorCode.INVALID_PATH)

            ls_result = sorted(os.listdir(full_path))
            return build_server_response_success(ls_result)
        except Exception as e:
            logging.error("RLS error: %s", str(e))
            return build_server_response_error(ErrorCode.COMMAND_EXECUTION_FAILED)

    @Pyro4.expose
    def rmkdir(self, directory) -> ServerResponse:
        client = self._current_request_client()
        if not client:
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        logging.info("<< RMKDIR %s (%s)", directory, str(client))

        try:
            full_path = os.path.join(self._client_path(client), directory)

            logging.debug("Going to mkdir on %s", full_path)

            if not self._is_path_valid_for_client(full_path, client):
                return build_server_response_error(ErrorCode.INVALID_PATH)

            os.mkdir(full_path)
            return build_server_response_success()
        except Exception as e:
            logging.error("RMKDIR error: %s", str(e))
            return build_server_response_error(ErrorCode.COMMAND_EXECUTION_FAILED)

    def _current_request_addr(self) -> Optional[Address]:
        return Pyro4.current_context.client_sock_addr

    def _current_request_client(self) -> Optional[ClientContext]:
        return self.clients.get(self._current_request_addr())

    def _client_path(self, client: ClientContext):
        if client.sharing not in self.sharings:
            return None
        return os.path.join(self.sharings[client.sharing], client.rpwd)

    def _is_path_valid_for_client(self, path: str, client: ClientContext):
        if client.sharing not in self.sharings:
            logging.warning("Sharing not found %s", client.sharing)
            return False

        normalized_path = os.path.normpath(path)
        sharing_path = self.sharings[client.sharing]
        common_path = os.path.commonpath([normalized_path, sharing_path])

        logging.debug("Common path between '%s' and '%s' = '%s'",
                      normalized_path, sharing_path, common_path)

        return sharing_path == common_path

class DiscoverRequestListener(threading.Thread):

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

    server = Server()
    server.setup()

    server.add_share("home", "/home/stefano")
    server.add_share("tmp", "/tmp")
    server.add_share("sources", "/home/stefano/Sources")

    server.start()
