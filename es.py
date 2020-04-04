import json
import os
import select
import shlex
import socket
import struct
import sys
import readline
from datetime import datetime
from math import ceil
from typing import Optional, Union, Any, Callable, List, Dict

import Pyro4

import utils
from args import Args
from commands import Commands
from conf import Conf
from consts import ADDR_ANY, ADDR_BROADCAST, PORT_ANY
from defs import ServerIface, Endpoint, FileInfo
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


class LsArguments:
    SORT_BY_SIZE = ["-s", "--sort"]


class OpenArguments:
    TIMEOUT = ["-t", "--timeout"]


class ScanArguments:
    TIMEOUT = ["-t", "--timeout"]


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
        d("Sending DISCOVER on port %d message: %s",
          self.server_discover_port, str(discover_message))
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

    def rpwd(self):
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

    def rls(self, sort_by: str) -> ServerResponse:
        if not self.c_connected:
            return build_server_response_error(ErrorCode.NOT_CONNECTED)

        return self.server.rls(sort_by)

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
        self.command_dispatcher: Dict[str, Callable[[Args], None]] = {
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

    def execute_command_line(self, command_line: str) -> bool:
        command_line_parts = shlex.split(command_line)
        if len(command_line_parts) < 1:
            return False

        command = command_line_parts[0]
        command_args = Args(command_line_parts[1:])

        return self.execute_command(command, command_args)

    def execute_command(self, command: str, args: Args) -> bool:
        if command in self.command_dispatcher:
            t("Handling command %s (%s)", command, args)
            self.command_dispatcher[command](args)
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

    def _execute_cd(self, args: Args):
        directory = args.get_param(default="/")

        i(">> CD " + directory)
        if not os.path.isdir(os.path.join(os.getcwd(), directory)):
            error_print(ErrorCode.INVALID_PATH)
            return

        try:
            os.chdir(directory)
        except Exception:
            error_print(ErrorCode.COMMAND_EXECUTION_FAILED)

    def _execute_rcd(self, args: Args):
        if not self.connection:
            error_print(ErrorCode.NOT_CONNECTED)
            return

        directory = args.get_param(default="/")

        i(">> RCD %s", directory)

        resp = self.connection.rcd(directory)
        if is_server_response_success(resp):
            d("Successfully RCDed")
            pass
        else:
            self._handle_error_response(resp)

    def _execute_ls(self, args: Args):
        i(">> LS")

        if LsArguments.SORT_BY_SIZE in args:
            sort_by = "size"
        else:
            sort_by = "name"

        ls_result = utils.ls(os.getcwd(), sort_by=sort_by)
        if not ls_result:
            error_print(ErrorCode.COMMAND_EXECUTION_FAILED)

        self._print_file_infos(ls_result)

    def _execute_rls(self, args: Args):
        if not self.connection:
            error_print(ErrorCode.NOT_CONNECTED)
            return

        if LsArguments.SORT_BY_SIZE in args:
            sort_by = "size"
        else:
            sort_by = "name"

        i(">> RLS (sort by %s)", sort_by)

        resp = self.connection.rls(sort_by)

        if is_server_response_success(resp) and "data" in resp:
            if not resp["data"]:
                return

            self._print_file_infos(resp["data"])

        else:
            self._handle_error_response(resp)

    def _execute_mkdir(self, args: Args):
        directory = args.get_param()

        if not directory:
            error_print(ErrorCode.INVALID_COMMAND_SYNTAX)
            return

        i(">> MKDIR " + directory)
        try:
            os.mkdir(directory)
        except Exception:
            error_print(ErrorCode.COMMAND_EXECUTION_FAILED)

    def _execute_rmkdir(self, args: Args):
        if not self.connection:
            error_print(ErrorCode.NOT_CONNECTED)
            return

        directory = args.get_param()

        if not directory:
            error_print(ErrorCode.INVALID_COMMAND_SYNTAX)
            return

        i(">> RMKDIR " + directory)

        resp = self.connection.rmkdir(directory)
        if is_server_response_success(resp):
            d("Successfully RMKDIRed")
            pass
        else:
            self._handle_error_response(resp)

    def _execute_pwd(self, _: Args):
        i(">> PWD")

        try:
            print(os.getcwd())
        except Exception:
            error_print(ErrorCode.COMMAND_EXECUTION_FAILED)

    def _execute_rpwd(self, _: Args):
        if not self.connection:
            error_print(ErrorCode.NOT_CONNECTED)
            return

        i(">> RPWD")
        print(self.connection.rpwd())

    def _execute_open(self, args: Args):
        sharing_name = args.get_param()
        if not sharing_name:
            error_print(ErrorCode.INVALID_COMMAND_SYNTAX)
            return

        timeout = to_int(args.get_param(OpenArguments.TIMEOUT,
                                        default=Conf.DISCOVER_DEFAULT_TIMEOUT_SEC))

        i(">> OPEN %s (timeout = %d)", sharing_name, timeout)

        server_info: Optional[ServerInfo] = None

        def response_handler(client_endpoint: Endpoint,
                             a_server_info: ServerInfo) -> bool:
            nonlocal server_info
            d("Handling DISCOVER response from %s\n%s",
              str(client_endpoint), str(a_server_info))
            for sharing in a_server_info["sharings"]:
                if sharing == sharing_name:
                    d("Sharing [%s] found at %s:%d",
                      sharing, a_server_info["ip"], a_server_info["port"])
                    server_info = a_server_info
                    return False    # Stop DISCOVER

            return True             # Continue DISCOVER

        Discoverer(self.server_discover_port, response_handler,
                   timeout=timeout).discover()

        if not server_info:
            error_print(ErrorCode.SHARING_NOT_FOUND)
            return False

        if not self.connection:
            d("Creating new connection with %s", server_info["uri"])
            self.connection = Connection(server_info)
        else:
            d("Reusing existing connection with %s", server_info["uri"])

        # Actually send OPEN

        resp = self.connection.open(sharing_name)
        if is_server_response_success(resp):
            d("Successfully connected to %s:%d",
              server_info["ip"], server_info["port"])
        else:
            self._handle_error_response(resp)
            self.connection = None  # Invalidate connection

    def _execute_scan(self, args: Args):
        timeout = to_int(args.get_param(OpenArguments.TIMEOUT,
                                        default=Conf.DISCOVER_DEFAULT_TIMEOUT_SEC))

        i(">> SCAN (timeout = %d)")

        servers_found = 0

        def response_handler(client_address: Endpoint,
                             server_info: ServerInfo) -> bool:
            nonlocal servers_found

            d("Handling DISCOVER response from %s\n%s", str(client_address), str(server_info))
            # Print as soon as they come

            if servers_found > 0:
                print("")
            else:
                i("======================")

            print("{} ({}:{})"
                  .format(server_info["name"], server_info["ip"], server_info["port"]))

            for sharing_name in server_info["sharings"]:
                print("  " + sharing_name)

            servers_found += 1

            return True     # Go ahead

        Discoverer(self.server_discover_port, response_handler,
                   timeout=timeout).discover()

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
                file_name = next_file["name"]

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

    def _print_file_infos(self, infos: List[FileInfo]):

        longest_size_str = 0

        for info in infos:
            longest_size_str = max(longest_size_str, len(size_str(info["size"])))

        t("longest_size_str %d", longest_size_str)

        for info in infos:
            t("f_info: %s", info)

            print("{}  {}  {}".format(
                ("D" if info["type"] == "dir" else "F"),
                size_str(info["size"]).rjust(longest_size_str),
                info["name"]))

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
                outcome = self.client.execute_command_line(command)

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
            rpwd = self.client.connection.rpwd()
        else:
            rpwd = None

        if rpwd:
            return rpwd + "  ##  " + pwd + "> "
        return pwd + "> "


class ClientArguments:
    VERBOSE =   ["-v", "--verbose"]
    PORT =      ["-p", "--port"]
    HELP =      ["-h", "--help"]
    VERSION =   ["-V", "--version"]






def main():
    args = Args(sys.argv[1:])

    init_logging_from_args(args, ClientArguments.VERBOSE)

    i(APP_INFO)
    d(args)

    if ClientArguments.HELP in args:
        terminate(HELP)

    if ClientArguments.VERSION in args:
        terminate(APP_INFO)

    server_discover_port = Conf.DEFAULT_SERVER_DISCOVER_PORT

    if ClientArguments.PORT in args:
        server_discover_port = to_int(args.get_param(ClientArguments.PORT))

    # Start in interactive mode
    client = Client(server_discover_port)

    # Allow some commands directly from command line
    # GET, SCAN
    full_command = args.get_params()

    COMMAND_LINE_COMMANDS = [Commands.GET, Commands.SCAN]

    if full_command:
        command = full_command.pop(0)

        if command not in COMMAND_LINE_COMMANDS:
            utils.abort("Unknown command: {}".format(command))

        # Execute directly
        # Take out the first token as "command" and leave
        # everything else as it is
        d("Executing command directly from command line: %s (%s)",
          command, args)
        client.execute_command(command, args)
    else:
        # Start the shell
        d("Executing shell")
        shell = Shell(client)
        shell.input_loop()


if __name__ == "__main__":
    main()