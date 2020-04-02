import json
import logging
import os
import select
import shlex
import socket
import struct
import sys
import readline
from datetime import datetime
from math import ceil
from typing import Optional, Union, Any, Callable, List

import Pyro4

from args import Args
from commands import Commands
from conf import Conf
from consts import ADDR_ANY, ADDR_BROADCAST, PORT_ANY
from defs import ServerIface, Endpoint
from errors import ErrorCode
from globals import HOME
from log import init_logging_from_args, e, w, i, d, t
from server_response import ServerResponse, is_server_response_success, \
    is_server_response_error, build_server_response_error
from server_info import ServerInfo
from utils import eprint, values, terminate, to_int, size_str

APP_INFO = Conf.APP_NAME_CLIENT + " (" + Conf.APP_NAME_CLIENT_SHORT + ") v. " + Conf.APP_VERSION

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
    ErrorCode.COMMAND_EXECUTION_FAILED: "Command execution failed",
    ErrorCode.NOT_IMPLEMENTED: "Not implemented",
    ErrorCode.INVALID_TRANSACTION: "Invalid transaction",
    ErrorCode.UNEXPECTED_SERVER_RESPONSE: "Unexpected server response"
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
            server_discover_port: int,
            response_handler: Callable[[Endpoint, ServerInfo], bool],
            timeout=Conf.DISCOVER_DEFAULT_TIMEOUT_SEC):
        self.server_discover_port = server_discover_port
        self.response_handler = response_handler
        self.timeout = timeout

    def discover(self):
        # Listening socket
        in_addr = (ADDR_ANY, PORT_ANY)

        in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        in_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO,
                        struct.pack("LL", ceil(self.timeout), 0))
        in_sock.bind(in_addr)

        in_port = in_sock.getsockname()[1]

        d("Client discover port: %d", in_port)

        # Send discover
        out_addr = (ADDR_BROADCAST, self.server_discover_port)
        discover_message = in_port.to_bytes(2, "big")

        out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        out_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        d("Sending DISCOVER message: %s", str(discover_message))
        out_sock.sendto(discover_message, out_addr)

        # Listen
        discover_start_time = datetime.now()

        remaining_seconds = self.timeout

        while remaining_seconds > 0:
            t("Waiting for %.3f seconds...", remaining_seconds)

            read_fds, write_fds, error_fds = select.select([in_sock], [], [], remaining_seconds)

            if in_sock in read_fds:
                t("DISCOVER socket ready for recv")
                response, addr = in_sock.recvfrom(1024)
                d("Received DISCOVER response from: %s", addr)
                json_response: ServerResponse = json.loads(response)

                if json_response["success"] and json_response["data"]:
                    go_ahead = self.response_handler(addr, json_response["data"])

                    if not go_ahead:
                        t("Stopping DISCOVER since handle_discover_response_callback returned false")
                        return
            else:
                t("DISCOVER timeout elapsed (%.3f)", self.timeout)

            remaining_seconds = \
                self.timeout - (datetime.now() - discover_start_time).total_seconds()

        d("Stopping DISCOVER listener")


class Connection:
    def __init__(self, server_info):
        t("Initializing new Connection")
        self.server_info: ServerInfo = server_info
        self.server: Union[ServerIface, Any] = Pyro4.Proxy(self.server_info["uri"])
        self.c_connected = False
        self.c_sharing = None
        self.c_rpwd = ""

    def is_connected(self):
        d("c_connected: %d", self.c_connected)
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
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        resp = self.server.rcd(path)
        if is_server_response_success(resp):
            self.c_rpwd = resp["data"]

        return resp

    def rls(self) -> ServerResponse:
        if not self.c_connected:
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        return self.server.rls()

    def rmkdir(self, directory) -> ServerResponse:
        if not self.c_connected:
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        return self.server.rmkdir(directory)

    def get(self, files) -> ServerResponse:
        if not self.c_connected:
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        return self.server.get(files)

    def get_next(self, transaction) -> ServerResponse:
        if not self.c_connected:
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        return self.server.get_next(transaction)


# ========================

class Client:
    def __init__(self, server_discover_port: int):
        self.server_discover_port = server_discover_port
        self.connection: Optional[Connection] = None
        # self.pwd = os.getcwd()
        self.command_dispatcher = {
            Commands.HELP: self._execute_help,
            Commands.EXIT: self._execute_exit,
            Commands.LOCAL_CHANGE_DIRECTORY: self._execute_cd,
            Commands.REMOTE_CHANGE_DIRECTORY: self._execute_rcd,
            Commands.LOCAL_LIST_DIRECTORY: self._execute_ls,
            Commands.REMOTE_LIST_DIRECTORY: self._execute_rls,
            Commands.LOCAL_CREATE_DIRECTORY: self._execute_mkdir,
            Commands.REMOTE_CREATE_DIRECTORY: self._execute_rmkdir,
            Commands.LOCAL_CURRENT_DIRECTORY: self._execute_pwd,
            Commands.REMOTE_CURRENT_DIRECTORY: self._execute_rpwd,
            Commands.GET: self._execute_get,
            Commands.OPEN: self._execute_open,
            Commands.SCAN: self._execute_scan
        }

    def execute_command(self, full_command):
        full_command_parts = shlex.split(full_command)
        if len(full_command) < 1:
            return False

        command = full_command_parts[0]
        command_args = full_command_parts[1:]
        if command in self.command_dispatcher:
            t("Handling command %s%s", command, command_args)
            self.command_dispatcher[command](command_args)
            return True
        else:
            return False

    def is_connected(self):
        t("self.connection = %d", True if self.connection else False)
        return self.connection and self.connection.is_connected()

    def _execute_help(self, _):
        print(HELP)

    def _execute_exit(self, _):
        pass

    def _execute_cd(self, args):
        directory = args[0] if len(args) > 0 else HOME

        i(">> CD " + directory)
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

        i(">> RCD %s", directory)

        resp = self.connection.rcd(directory)
        if is_server_response_success(resp):
            d("Successfully RCDed")
            pass
        else:
            self._handle_error_response(resp)

    def _execute_ls(self, args):
        i(">> LS")

        try:
            for f in sorted(os.listdir(".")):
                print(f)
        except Exception as e:
            error_print(ErrorCode.COMMAND_EXECUTION_FAILED)

    def _execute_rls(self, args):
        if not self.connection:
            error_print(ErrorCode.NOT_CONNECTED)
            return

        i(">> RLS")

        resp = self.connection.rls()
        if is_server_response_success(resp) and "data" in resp:
            if not resp["data"]:
                return

            longest_size_str = len(size_str(max(resp["data"],
                                   key=lambda finfo: len(size_str(finfo["size"])))["size"]))

            d("longest_size_str %d", longest_size_str)
            t("longest_size_str %d", longest_size_str)

            for f_info in resp["data"]:
                t("f_info: %s", f_info)

                print(size_str(f_info["size"]).rjust(longest_size_str) +
                      "  " +
                      f_info["filename"])
        else:
            self._handle_error_response(resp)

    def _execute_mkdir(self, args):
        if len(args) <= 0:
            eprint(ErrorCode.INVALID_COMMAND_SYNTAX)
            return

        directory = args[0]
        i(">> RMKDIR " + directory)
        try:
            os.mkdir(directory)
        except Exception:
            error_print(ErrorCode.COMMAND_EXECUTION_FAILED)

    def _execute_rmkdir(self, args):
        if not self.connection:
            error_print(ErrorCode.NOT_CONNECTED)
            return

        if len(args) <= 0:
            eprint(ErrorCode.INVALID_COMMAND_SYNTAX)
            return

        directory = args[0]
        i(">> RMKDIR " + directory)

        resp = self.connection.rmkdir(directory)
        if is_server_response_success(resp):
            d("Successfully RMKDIRed")
            pass
        else:
            self._handle_error_response(resp)


    def _execute_pwd(self, args):
        i(">> PWD")

        try:
            print(os.getcwd())
        except Exception:
            error_print(ErrorCode.COMMAND_EXECUTION_FAILED)

    def _execute_rpwd(self, args):
        if not self.connection:
            error_print(ErrorCode.NOT_CONNECTED)
            return

        i(">> RPWD")
        print(self.connection.sharing_rpwd())

    def _execute_open(self, args):
        if len(args) <= 0:
            error_print(ErrorCode.INVALID_COMMAND_SYNTAX)
            return

        sharing_name = args[0]
        i(">> OPEN %s", sharing_name)

        server_info: Optional[ServerInfo] = None

        def response_handler(client_address: Endpoint,
                             a_server_info: ServerInfo) -> bool:
            nonlocal server_info
            d("Handling DISCOVER response from %s\n%s",
                          str(client_address), str(a_server_info))
            for sharing in a_server_info["sharings"]:
                if sharing == sharing_name:
                    d("Sharing [%s] found at %s:%d",
                                  sharing, a_server_info["ip"], a_server_info["port"])
                    server_info = a_server_info
                    return False    # Stop DISCOVER

            return True             # Continue DISCOVER

        Discoverer(self.server_discover_port, response_handler).discover()

        if not server_info:
            error_print(ErrorCode.SHARING_NOT_FOUND)
            return False

        if not self.connection:
            d("Creating new connection with %s", server_info["uri"])
            self.connection = Connection(server_info)
        else:
            d("Reusing existing connection with %s", server_info["uri"])

        # Send OPEN

        resp = self.connection.open(sharing_name)
        if is_server_response_success(resp):
            d("Successfully connected to %s:%d",
                          server_info["ip"], server_info["port"])
        else:
            self._handle_error_response(resp)
            self.connection = None

    def _execute_scan(self, args):
        i(">> SCAN")

        servers_info: List[ServerInfo] = []

        def response_handler(client_address: Endpoint,
                             server_info: ServerInfo) -> bool:
            d("Handling DISCOVER response from %s\n%s", str(client_address), str(server_info))
            servers_info.append(server_info)
            return True     # Go ahead

        Discoverer(self.server_discover_port, response_handler).discover()

        # Print sharings
        i("======================")
        for idx, server_info in enumerate(servers_info):
            print("{} ({}:{})"
                  .format(server_info["name"], server_info["ip"], server_info["port"]))

            for sharing_name in server_info["sharings"]:
                print("  " + sharing_name)

            if idx < len(servers_info) - 1:
                print("")
        i("======================")

    def _execute_get(self, args):
        if not self.connection:
            error_print(ErrorCode.NOT_CONNECTED)
            return

        i(">> GET %s", ", ".join(args))
        resp = self.connection.get(args)
        d("GET response\n%s", resp)

        if "data" not in resp or \
                "transaction" not in resp["data"] or \
                "port" not in resp["data"]:
            error_print(ErrorCode.UNEXPECTED_SERVER_RESPONSE)
            return

        transaction = resp["data"]["transaction"]
        port = resp["data"]["port"]

        if is_server_response_success(resp):
            d("Successfully GETed")

            transfer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            transfer_socket.connect((self.connection.server_info["ip"], port))

            while True:
                d("Fetching another file info")
                get_next_resp = self.connection.get_next(transaction)
                d("get_next()\n%s", get_next_resp)

                if "data" not in get_next_resp:
                    error_print(ErrorCode.UNEXPECTED_SERVER_RESPONSE)
                    return

                next_file = get_next_resp["data"]

                if next_file == "ok":
                    d("Nothing more to GET")
                    break

                d("NEXT: %s", next_file)
                file_len = next_file["length"]
                file_name = next_file["filename"]

                # Strip only the trail part
                if self.connection.c_rpwd:
                    trail_file_name = file_name.split(self.connection.c_rpwd)[1].lstrip(os.path.sep)
                else:
                    trail_file_name = file_name

                d("self.connection.c_rpwd: %s", self.connection.c_rpwd)
                d("Trail file name: %s", trail_file_name)

                # Create the file
                d("Creating intermediate dirs locally")
                head, tail = os.path.split(trail_file_name)
                if head:
                    os.makedirs(head, exist_ok=True)

                d("Opening file locally")
                file = open(trail_file_name, "wb")

                # Really get it

                BUFFER_SIZE = 4096

                read = 0
                while read < file_len:
                    recv_dim = min(BUFFER_SIZE, file_len - read)
                    chunk = transfer_socket.recv(recv_dim)

                    if not chunk:
                        d("END")
                        break

                    chunk_len = len(chunk)

                    d("Read chunk of %dB", chunk_len)

                    written_chunk_len = file.write(chunk)

                    if chunk_len != written_chunk_len:
                        w("Written less bytes than expected: something will go wrong")
                        exit(-1)

                    read += written_chunk_len
                    d("%d/%d (%.2f%%)", read, file_len, read / file_len * 100)

                d("DONE %s", trail_file_name)
                file.close()

                if os.path.getsize(trail_file_name) == file_len:
                    t("File OK (length match)")
                else:
                    w("File length mismatch. %d != %d",
                                    os.path.getsize(trail_file_name), file_len)
                    exit(-1)

            d("Closing socket")
            transfer_socket.close()
        else:
            self._handle_error_response(resp)

    def _handle_error_response(self, resp: ServerResponse):
        if resp["error"] == ErrorCode.NOT_CONNECTED:
            d("Received a NOT_CONNECTED response: destroying connection")
            self.connection = None
        response_error_print(resp)


# ========================


class Shell:

    COMMANDS = sorted(values(Commands))

    def __init__(self, client: Client):
        self.available_commands = []
        self.client = client

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
            try:
                prompt = self._build_prompt_string()
                command = input(prompt)
                outcome = self.client.execute_command(command)

                if not outcome:
                    error_print(ErrorCode.COMMAND_NOT_RECOGNIZED)
            except KeyboardInterrupt:
                d("CTRL+C detected")
                print()
            except EOFError:
                d("CTRL+D detected: exiting")
                break


    def _build_prompt_string(self):
        pwd = os.getcwd()
        if self.client.is_connected():
            rpwd = self.client.connection.sharing_rpwd()
        else:
            rpwd = None

        if rpwd:
            return rpwd + "  ##  " + pwd + "> "
        return pwd + "> "


class ClientArgument:
    VERBOSE =   ["-v", "--verbose"]
    PORT =      ["-p", "--port"]
    HELP =      ["-h", "--help"]
    VERSION =   ["-V", "--version"]


if __name__ == "__main__":
    args = Args(sys.argv[1:])

    if ClientArgument.HELP in args:
        terminate(HELP)

    if ClientArgument.VERSION in args:
        terminate(APP_INFO)

    init_logging_from_args(args, ClientArgument.VERBOSE)

    i(APP_INFO)

    server_discover_port = Conf.DEFAULT_SERVER_DISCOVER_PORT

    if ClientArgument.PORT in args:
        server_discover_port = to_int(args.get_param(ClientArgument.PORT))

    # Start in interactive mode
    client = Client(server_discover_port)
    shell = Shell(client)
    shell.input_loop()
