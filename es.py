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
from defs import ServerIface, Address
from globals import HOME
from log import init_logging
from server_response import ServerResponse, is_server_response_success, SERVER_RESPONSE_ERROR, \
    is_server_response_error, ErrorCode, ErrorCode
from server_info import ServerInfo
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

ERRORS_STR = {
    ErrorCode.ERROR: "Error",
    ErrorCode.NOT_CONNECTED: "Not connected",
    ErrorCode.INVALID_COMMAND_SYNTAX: "Invalid command syntax",
    ErrorCode.SHARING_NOT_FOUND: "Sharing not found",
    ErrorCode.INVALID_PATH: "Invalid path",
    ErrorCode.COMMAND_NOT_RECOGNIZED: "Command not recognized",
    ErrorCode.COMMAND_EXECUTION_FAILED: "Command execution failed"
}


def error_string(error_code: int) -> str:
    error_code = error_code if error_code in ERRORS_STR else ErrorCode.ERROR
    return ERRORS_STR[error_code]


def error_print(error_code: int):
    eprint(error_string(error_code))


def response_error_print(response: ServerResponse):
    error_code = response["error"] if is_server_response_error(response) else ErrorCode.ERROR
    error_print(error_code)


class Discoverer:
    def __init__(
            self,
            response_handler: Callable[[Address, ServerInfo], bool],
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
                json_response: ServerResponse = json.loads(response)

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


class Connection:
    def __init__(self, server_info):
        self.server_info: ServerInfo = server_info
        self.server: Union[ServerIface, Any] = Pyro4.Proxy(self.server_info["uri"])
        self.c_connected = False
        self.c_sharing = None
        self.c_rpwd = ""

    def is_connected(self):
        return self.c_connected

    def sharing_rpwd(self):
        return os.path.join(self.c_sharing,
                            self.c_rpwd).rstrip(os.sep)

    def open(self, sharing) -> ServerResponse:
        resp = self.server.open(sharing)

        if is_server_response_success(resp):
            self.c_connected = True
            self.c_sharing = sharing

        return resp

    def rcd(self, path) -> ServerResponse:
        if not self.c_connected:
            return SERVER_RESPONSE_ERROR

        resp = self.server.rcd(path)
        if is_server_response_success(resp):
            self.c_rpwd = resp["data"]

        return resp

    def rls(self) -> ServerResponse:
        if not self.c_connected:
            return SERVER_RESPONSE_ERROR

        return self.server.rls()


# ========================

class Client:
    def __init__(self):
        self.connection: Optional[Connection] = None
        # self.pwd = os.getcwd()
        self.command_dispatcher = {
            Commands.HELP: self._execute_help,
            Commands.LOCAL_CHANGE_DIRECTORY: self._execute_cd,
            Commands.REMOTE_CHANGE_DIRECTORY: self._execute_rcd,
            Commands.LOCAL_LIST_DIRECTORY: self._execute_ls,
            Commands.REMOTE_LIST_DIRECTORY: self._execute_rls,
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

    def is_connected(self):
        return self.connection and self.connection.is_connected()

    def _execute_help(self, _):
        print(HELP)

    def _execute_cd(self, args):
        directory = args[0] if len(args) > 0 else HOME

        logging.info(">> CD " + directory)
        if not os.path.isdir(os.path.join(os.getcwd(), directory)):
            error_print(ErrorCode.INVALID_PATH)
            return

        try:
            os.chdir(directory)
        except Exception:
            error_print(ErrorCode.COMMAND_EXECUTION_FAILED)

    def _execute_rcd(self, args):
        if not self.connection:
            error_print(ErrorCode.NOT_CONNECTED)
            return

        directory = args[0] if len(args) > 0 else "/"

        logging.info(">> RCD %s", directory)

        resp = self.connection.rcd(directory)
        if is_server_response_success(resp):
            logging.debug("Successfully RCDed")
            pass
        else:
            response_error_print(resp)

    def _execute_ls(self, args):
        logging.info(">> LS")

        try:
            for f in sorted(os.listdir(".")):
                print(f)
        except Exception as e:
            error_print(ErrorCode.COMMAND_EXECUTION_FAILED)

    def _execute_rls(self, args):
        if not self.connection:
            error_print(ErrorCode.NOT_CONNECTED)
            return

        logging.info(">> RLS")

        resp = self.connection.rls()
        if is_server_response_success(resp) and "data" in resp:
            for f in resp["data"]:
                print(f)
        else:
            response_error_print(resp)

    def _execute_mkdir(self, args):
        if len(args) <= 0:
            eprint(ErrorCode.INVALID_COMMAND_SYNTAX)
            return

        directory = args[0]
        logging.info(">> MKDIR " + directory)
        try:
            os.mkdir(directory)
        except Exception as e:
            error_print(ErrorCode.COMMAND_EXECUTION_FAILED)

    def _execute_pwd(self, args):
        logging.info(">> PWD")

        try:
            print(os.getcwd())
        except Exception as e:
            error_print(ErrorCode.COMMAND_EXECUTION_FAILED)

    def _execute_rpwd(self, args):
        if not self.connection:
            eprint("Not connected")
            return

        logging.info(">> RPWD")
        print(self.connection.sharing_rpwd())

    def _execute_open(self, args):
        if len(args) <= 0:
            error_print(ErrorCode.INVALID_COMMAND_SYNTAX)
            return

        sharing_name = args[0]
        logging.info(">> OPEN %s", sharing_name)

        server_info: Optional[ServerInfo] = None

        def response_handler(client_address: Address,
                             a_server_info: ServerInfo) -> bool:
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

        Discoverer(response_handler).discover()

        if not server_info:
            error_print(ErrorCode.SHARING_NOT_FOUND)
            return False

        if not self.connection:
            logging.debug("Creating new connection with %s", server_info["uri"])
            self.connection = Connection(server_info)
        else:
            logging.debug("Reusing existing connection with %s", server_info["uri"])

        # Send OPEN

        resp = self.connection.open(sharing_name)
        if is_server_response_success(resp):
            logging.debug("Successfully connected to %s:%d",
                          server_info["address"], server_info["port"])
        else:
            response_error_print(resp)
            self.connection = None

    def _execute_scan(self, args):
        logging.info(">> SCAN")

        servers_info: List[ServerInfo] = []

        def response_handler(client_address: Address,
                             server_info: ServerInfo) -> bool:
            logging.debug("Handling DISCOVER response from %s\n%s", str(client_address), str(server_info))
            servers_info.append(server_info)
            return True     # Go ahead

        Discoverer(response_handler).discover()

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

# ========================


class Shell:

    COMMANDS = sorted(values(Commands))

    def __init__(self):
        self.connection = None
        self.available_commands = []
        self.client = Client()

    def setup(self):
        readline.set_completer(self.next_suggestion)
        readline.parse_and_bind("tab: complete")

    def next_suggestion(self, text, state):
        if state == 0:
            self.available_commands = [c for c in Shell.COMMANDS if c.startswith(text)]
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
                error_print(ErrorCode.COMMAND_NOT_RECOGNIZED)

    def _build_prompt_string(self):
        pwd = os.getcwd()
        if self.client.is_connected():
            rpwd = self.client.connection.sharing_rpwd()
        else:
            rpwd = None

        if rpwd:
            return rpwd + "  ##  " + pwd + "> "
        return pwd + "> "


if __name__ == "__main__":
    init_logging(enabled=True, level=LoggingLevels.TRACE)

    if len(sys.argv) <= 1:
        # Start in interactive mode
        shell = Shell()
        shell.setup()
        shell.input_loop()
