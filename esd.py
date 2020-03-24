import json
import logging
import os
import random
import sys
import socket
import socketserver
import threading
import time
from typing import Dict, Optional, Tuple, List

import Pyro4 as Pyro4
from Pyro4 import socketutil

import netutils
from conf import Conf, LoggingLevels
from consts import ADDR_ANY
from defs import ServerIface, Address
from log import init_logging
from server_response import ServerResponse, build_server_response_success, build_server_response_error, ErrorCode
from utils import random_string


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
        # self.ip = socketutil.getInterfaceAddress()
        self.clients: Dict[(str, int), ClientContext] = {}

        self.gets: Dict[str, List[str]] = {}    # transaction -> list of remaining files

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

        new_path = self._path_for_client(client, path)

        logging.debug("Sharing path: %s", new_path)

        if not self._is_path_valid_for_client(new_path, client):
            logging.error("Path is invalid (out of sharing domain)")
            return build_server_response_error(ErrorCode.INVALID_PATH)

        if not os.path.isdir(new_path):
            logging.error("Path does not exists")
            return build_server_response_error(ErrorCode.INVALID_PATH)

        logging.debug("Path exists, success")

        client.rpwd = self._trailing_path_for_client(client, new_path)
        logging.debug("New rpwd: %s", client.rpwd)

        return build_server_response_success(client.rpwd)

    @Pyro4.expose
    def rls(self) -> ServerResponse:
        client = self._current_request_client()
        if not client:
            logging.warning("Not connected: %s", self._current_request_addr())
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        logging.info("<< RLS (%s)",  str(client))

        try:
            full_path = self._current_client_path(client)

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
            full_path = os.path.join(self._current_client_path(client), directory)

            logging.debug("Going to mkdir on %s", full_path)

            if not self._is_path_valid_for_client(full_path, client):
                return build_server_response_error(ErrorCode.INVALID_PATH)

            os.mkdir(full_path)
            return build_server_response_success()
        except Exception as e:
            logging.error("RMKDIR error: %s", str(e))
            return build_server_response_error(ErrorCode.COMMAND_EXECUTION_FAILED)

    @Pyro4.expose
    def get(self, files) -> ServerResponse:
        client = self._current_request_client()
        if not client:
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        logging.info("<< GET %s (%s)", str(files), str(client))

        # Compute real path for each filename
        normalized_files = []
        for f in files:
            normalized_files.append(self._path_for_client(client, f))

        logging.debug("Normalized files:\n%s", normalized_files)

        # Return a transaction ID for identify the transfer
        transaction = random_string()

        self.gets[transaction] = normalized_files
        return build_server_response_success({"transaction": transaction})

        # Check validity for each file

        # for root, directories, files in os.walk(client_path):
        #     for directory in directories:
        #         f = os.path.join(root, directory)
        #         files_set.intersection()
        #
        #         print(os.path.join(root, directory))
        #     for file in files:
        #         print(os.path.join(root, file))

    @Pyro4.expose
    def get_next(self, transaction) -> ServerResponse:
        client = self._current_request_client()
        if not client:
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        logging.info("<< GET_NEXT %s (%s)", transaction, str(client))

        if transaction not in self.gets:
            return build_server_response_error(ErrorCode.INVALID_TRANSACTION)

        remaining_files = self.gets[transaction]

        # if len(self.gets[transaction]) == 0:
        #     return build_server_response_success()  # Nothing else

        while len(remaining_files) > 0:

            # Get next file (or dir)
            next_file_path = self.gets[transaction].pop()

            logging.debug("Next file path: %s", next_file_path)

            # Check domain validity
            if not self._is_path_valid_for_client(next_file_path, client):
                logging.warning("Invalid file found: skipping %s", next_file_path)
                continue

            if os.path.isdir(next_file_path):
                logging.debug("Found a directory: adding all inner files to remaining_files")
                for f in os.listdir(next_file_path):
                    f_path = os.path.join(next_file_path, f)
                    logging.debug("Adding %s", f_path)
                    remaining_files.append(f_path)
                continue

            if not os.path.isfile(next_file_path):
                logging.warning("Not file nor dir? skipping")
                continue

            # We are handling a valid file, report the metadata to the client
            logging.debug("NEXT FILE: %s", next_file_path)

            trail = self._trailing_path_for_client(client, next_file_path)
            logging.debug("Trail: %s", trail)

            return build_server_response_success({
                "filename": trail,
                "length": os.path.getsize(next_file_path)
            })

        logging.debug("No remaining files")
        return build_server_response_success()

    def _current_request_addr(self) -> Optional[Address]:
        return Pyro4.current_context.client_sock_addr

    def _current_request_client(self) -> Optional[ClientContext]:
        return self.clients.get(self._current_request_addr())

    def _client_sharing_path(self, client: ClientContext):
        return self.sharings.get(client.sharing)

    def _current_client_path(self, client: ClientContext):
        sharing_path = self._client_sharing_path(client)

        if not sharing_path:
            return None

        return os.path.join(sharing_path, client.rpwd)

    def _path_for_client(self, client: ClientContext, path: str):
        sharing_path = self._client_sharing_path(client)

        if not sharing_path:
            return None

        if path.startswith(os.sep):
            # If path begins with / it refers to the root of the current sharing
            trail = path.lstrip(os.sep)
        else:
            # Otherwise it refers to a subdirectory starting from the current rpwd
            trail = os.path.join(client.rpwd, path)

        return os.path.normpath(os.path.join(sharing_path, trail))

    def _trailing_path_for_client(self, client: ClientContext, path: str):
        # with [home] = /home/stefano
        #   /home/stefano/Applications -> Applications
        return path.split(self._client_sharing_path(client))[1].lstrip(os.sep)



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
