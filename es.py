import abc
import json
import logging
import os
import select
import socket
import struct
import sys
import threading
import readline
from datetime import datetime
from math import ceil
from typing import Optional, Union, Any, Callable, List

import Pyro4

from commands import Commands
from conf import Conf, LoggingLevels
from consts import ADDR_ANY, ADDR_BROADCAST
from defs import EasyshareServerIface, ResponseCode, Address
from log import init_logging
from server_response import EasyshareServerResponse, is_server_response_success, SERVER_RESPONSE_ERROR, \
    is_server_response_error
from server_info import EasyshareServerInfo
from utils import eprint, values

HELP = """\
cd      <path>      |   change local directory
exit                |   exit shell
get     <file>      |   download file or folder
help                |   print command list
ls                  |   list local directory
mkdir   <folder>    |   create local directory
open    <sharing>   |   connect to a server's sharing
put     <file>      |   upload file or folder
pwd                 |   print local directory name
rcd     <path>      |   change remote directory
rls                 |   list remote directory
rmkdir  <folder>    |   create remote directory
rpwd                |   print remote directory name
scan    [timeout]   |   scan the network for sharings"""
# ^^ Non mi piace timeout ^^

SERVER_RESPONSE_ERRORS = [val for val in values(ResponseCode) if val < 0]

SERVER_RESPONSE_ERRORS_STR = {
    ResponseCode.NOT_CONNECTED: "Not connected"
}

INVALID_RESPONSE = "Invalid response"
# ^^ Find a good place ^^

#
# class EasyshareDiscoverResponse:
#     def __init__(self):
#         self.uri = None
#         self.name = None
#         self.address = None
#         self.port = None
#         self.sharings = None
#
#     @staticmethod
#     def from_string(s):
#         try:
#             j = json.loads(s)
#             resp = EasyshareDiscoverResponse()
#             resp.uri = j["uri"]
#             resp.name = j["name"]
#             resp.address = j["address"]
#             resp.port = j["port"]
#             resp.sharings = j["sharings"]
#             return resp
#         except json.JSONDecodeError as e:
#             logging.warning("JSON decode error {%s} while decoding\n%s", e, str(s))
#             return None
#
#     def __str__(self):
#         return str(self.__dict__)


class EasyshareDiscoverer:
    def __init__(
            self,
            response_handler: Callable[[Address, EasyshareServerInfo], bool],
            timeout=Conf.DISCOVER_DEFAULT_TIMEOUT_SEC):
        self.response_handler = response_handler
        self.timeout = timeout

    def discover(self):
        # Listening socket
        in_addr = (ADDR_ANY, Conf.DISCOVER_PORT_CLIENT)

        in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        in_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO,
                        struct.pack("LL", ceil(self.timeout), 0))
        in_sock.bind(in_addr)

        # Send discover
        out_addr = (ADDR_BROADCAST, Conf.DISCOVER_PORT_SERVER)
        discover_message = bytes("DISCOVER", encoding="UTF-8")

        out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        out_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        logging.debug("Sending DISCOVER message")
        out_sock.sendto(discover_message, out_addr)

        # Listen

        discover_start_time = datetime.now()

        remaining_seconds = self.timeout

        while remaining_seconds > 0:
            logging.trace("Waiting for %.3f seconds...", remaining_seconds)

            read_fds, write_fds, error_fds = select.select([in_sock], [], [], remaining_seconds)

            if in_sock in read_fds:
                logging.trace("DISCOVER socket ready for recv")
                response, addr = in_sock.recvfrom(1024)
                logging.debug("Received DISCOVER response from: %s", addr)
                json_response: EasyshareServerResponse = json.loads(response)

                if json_response["success"] and json_response["data"]:
                    go_ahead = self.response_handler(addr, json_response["data"])

                    if not go_ahead:
                        logging.trace("Stopping DISCOVER since handle_discover_response_callback returned false")
                        return
            else:
                logging.trace("DISCOVER timeout elapsed (%.3f)", self.timeout)

            remaining_seconds = \
                self.timeout - (datetime.now() - discover_start_time).total_seconds()

        logging.debug("Stopping DISCOVER listener")


class EasyshareConnection:
    def __init__(self, server_info):
        self.server_info: EasyshareServerInfo = server_info
        self.server: Union[EasyshareServerIface, Any] = Pyro4.Proxy(self.server_info["uri"])
        self.c_connected = False
        self.c_sharing = None
        self.c_rpwd = ""

    def open(self, sharing) -> EasyshareServerResponse:
        resp = self.server.open(sharing)

        if is_server_response_success(resp):
            self.c_connected = True
            self.c_sharing = sharing

        return resp

    def rcd(self, path) -> EasyshareServerResponse:
        if not self.c_connected:
            return SERVER_RESPONSE_ERROR

        resp = self.server.rcd(path)
        if is_server_response_success(resp):
            self.c_rpwd = resp["data"]["rpwd"]

        return resp

# ========================

class EasyshareClient:
    def __init__(self):
        self.connection: Optional[EasyshareConnection] = None
        # self.pwd = os.getcwd()
        self.command_dispatcher = {
            Commands.HELP: self._execute_help,
            Commands.LOCAL_CHANGE_DIRECTORY: self._execute_cd,
            Commands.REMOTE_CHANGE_DIRECTORY: self._execute_rcd,
            Commands.LOCAL_LIST_DIRECTORY: self._execute_ls,
            Commands.LOCAL_CREATE_DIRECTORY: self._execute_mkdir,
            Commands.LOCAL_CURRENT_DIRECTORY: self._execute_pwd,
            Commands.REMOTE_CURRENT_DIRECTORY: self._execute_rpwd,
            Commands.OPEN: self._execute_open,
            Commands.SCAN: self._execute_scan
        }

    def execute_command(self, full_command):
        full_command = full_command.split()
        if len(full_command) < 1:
            return False

        command = full_command[0]
        command_args = full_command[1:]
        if command in self.command_dispatcher:
            logging.trace("Handling command {%s}" % command)
            self.command_dispatcher[command](command_args)
            return True
        else:
            return False


    def _execute_help(self, _):
        print(HELP)

    def _execute_cd(self, args):
        if len(args) <= 0:
            eprint(EasyshareShell.INVALID_COMMAND_SYNTAX)
            return

        directory = args[0]
        logging.info(">> CD " + directory)
        try:
            os.chdir(directory)
        except Exception as e:
            logging.error(EasyshareShell.COMMAND_EXECUTION_ERROR)
            eprint(e)

    def _execute_rcd(self, args):
        if len(args) <= 0:
            eprint(EasyshareShell.INVALID_COMMAND_SYNTAX)
            return

        if not self.connection:
            eprint("Not connected")
            return

        directory = args[0]
        logging.info(">> RCD %s", directory)

        resp = self.connection.rcd(directory)
        if is_server_response_error(resp):
            print("Error...")
            return

    def _execute_ls(self, args):
        try:
            for f in os.listdir("."):
                print(f)
        except Exception as e:
            logging.error(EasyshareShell.COMMAND_EXECUTION_ERROR)
            eprint(e)

    def _execute_mkdir(self, args):
        if len(args) <= 0:
            eprint(EasyshareShell.INVALID_COMMAND_SYNTAX)
            return

        directory = args[0]
        logging.info("MKDIR " + directory)
        try:
            os.mkdir(directory)
        except Exception as e:
            logging.error(EasyshareShell.COMMAND_EXECUTION_ERROR)
            eprint(e)

    def _execute_pwd(self, args):
        try:
            logging.info("PWD")
            print(os.getcwd())
        except Exception as e:
            logging.error(EasyshareShell.COMMAND_EXECUTION_ERROR)
            eprint(e)

    def _execute_rpwd(self, args):
        if not self.connection:
            eprint("Not connected")
            return

        print(self.connection.c_rpwd)

        # No need to perform the request

        # resp = self.connection.c_rpwd
        # if EasyshareClient.is_error(resp):
        #     print(EasyshareClient.error_string(resp))
        #     return
        #
        # if not isinstance(resp, str):
        #     logging.warning("Invalid response type: %s", type(resp))
        #     print(INVALID_RESPONSE)
        #     return
        #
        # print(resp)

    def _execute_open(self, args):
        if len(args) <= 0:
            eprint(EasyshareShell.INVALID_COMMAND_SYNTAX)
            return

        sharing_name = args[0]
        logging.info(">> OPEN %s", sharing_name)

        server_info: Optional[EasyshareServerInfo] = None

        def response_handler(client_address: Address,
                             a_server_info: EasyshareServerInfo) -> bool:
            nonlocal server_info
            logging.debug("Handling DISCOVER response from %s\n%s",
                          str(client_address), str(a_server_info))
            for sharing in a_server_info["sharings"]:
                if sharing == sharing_name:
                    logging.debug("Sharing [%s] found at %s:%d",
                                  sharing, a_server_info["address"], a_server_info["port"])
                    server_info = a_server_info
                    return False    # Stop DISCOVER

            return True             # Continue DISCOVER

        EasyshareDiscoverer(response_handler).discover()

        if not server_info:
            eprint("Not found")
            return False

        if not self.connection:
            logging.debug("Creating new connection with %s", server_info["uri"])
            self.connection = EasyshareConnection(server_info)
        else:
            logging.debug("Reusing existing connection with %s", server_info["uri"])

        # Send OPEN

        resp = self.connection.open(sharing_name)
        if is_server_response_success(resp):
            logging.debug("Successfully connected to %s:%d",
                          server_info["address"], server_info["port"])
        else:
            eprint("Connection error")
            self.connection = None

    def _execute_scan(self, args):
        logging.info(">> SCAN")

        servers_info: List[EasyshareServerInfo] = []

        def response_handler(client_address: Address,
                             server_info: EasyshareServerInfo) -> bool:
            logging.debug("Handling DISCOVER response from %s\n%s", str(client_address), str(server_info))
            servers_info.append(server_info)
            return True     # Go ahead

        EasyshareDiscoverer(response_handler).discover()

        # Print sharings
        logging.info("======================")
        for idx, server_info in enumerate(servers_info):
            print("{} ({}:{})"
                  .format(server_info["name"], server_info["address"], server_info["port"]))

            for sharing_name in server_info["sharings"]:
                print("  " + sharing_name)

            if idx < len(servers_info) - 1:
                print("")
        logging.info("======================")


    def is_connected(self):
        return True if self.connection else False

    @staticmethod
    def is_error(resp):
        return isinstance(resp, int) and int(resp) in SERVER_RESPONSE_ERRORS

    @staticmethod
    def error_string(resp):
        return SERVER_RESPONSE_ERRORS_STR[int(resp)]


# ========================


class EasyshareShell:
    COMMAND_NOT_RECOGNIZED = "Command not recognized"
    INVALID_COMMAND_SYNTAX = "Invalid command syntax"
    COMMAND_EXECUTION_ERROR = "Command execution error"

    DEFAULT_PROMPT_STRING = "es"

    COMMANDS = sorted(values(Commands))

    def __init__(self):
        self.connection = None
        self.available_commands = []
        self.client = EasyshareClient()

    def setup(self):
        readline.set_completer(self.next_suggestion)
        readline.parse_and_bind("tab: complete")

    def next_suggestion(self, text, state):
        if state == 0:
            self.available_commands = [c for c in EasyshareShell.COMMANDS if c.startswith(text)]
        if len(self.available_commands) > 0:
            return self.available_commands.pop()
        return None

    def input_loop(self):
        command = None
        while command != Commands.EXIT:
            prompt = self._build_prompt_string()
            command = input(prompt)
            outcome = self.client.execute_command(command)

            if not outcome:
                eprint(EasyshareShell.COMMAND_NOT_RECOGNIZED)

    def _build_prompt_string(self):
        pwd = os.getcwd()
        if self.client.is_connected():
            rpwd = os.path.join(self.client.connection.c_sharing, self.client.connection.c_rpwd)
        else:
            rpwd = None

        if rpwd:
            return rpwd + "  ##  " + pwd + "> "
        return pwd + "> "

if __name__ == "__main__":
    init_logging(enabled=True, level=LoggingLevels.TRACE)

    print(SERVER_RESPONSE_ERRORS)
    if len(sys.argv) <= 1:
        # Start in interactive mode
        shell = EasyshareShell()
        shell.setup()
        shell.input_loop()
