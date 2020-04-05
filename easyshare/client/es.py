import os
import shlex
import socket
import sys
import readline
from typing import Optional, Callable, List, Dict

from easyshare import utils
from easyshare.client.connection import Connection
from easyshare.client.discover import Discoverer
from easyshare.client.errors import ClientErrors
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.response import Response, is_response_error, is_response_success
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.shared.args import Args
from easyshare.shared.conf import APP_NAME_CLIENT, APP_NAME_CLIENT_SHORT, APP_VERSION, DEFAULT_DISCOVER_PORT
from easyshare.shared.endpoint import Endpoint
from easyshare.shared.log import t, i, d, w, init_logging_from_args
from easyshare.utils.app import eprint, terminate, abort
from easyshare.utils.obj import values
from easyshare.utils.types import to_int

# ==================================================================


APP_INFO = APP_NAME_CLIENT + " (" + APP_NAME_CLIENT_SHORT + ") v. " + APP_VERSION


# === HELPS ===


HELP_APP = """\
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

HELP_COMMANDS = """\
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


# === ARGUMENTS ===


class ClientArguments:
    VERBOSE =   ["-v", "--verbose"]
    PORT =      ["-p", "--port"]
    HELP =      ["-h", "--help"]
    VERSION =   ["-V", "--version"]


# === COMMANDS ===


class Commands:
    HELP = "help"
    EXIT = "exit"

    LOCAL_CHANGE_DIRECTORY = "cd"
    LOCAL_LIST_DIRECTORY = "ls"
    LOCAL_CREATE_DIRECTORY = "mkdir"
    LOCAL_CURRENT_DIRECTORY = "pwd"

    REMOTE_CHANGE_DIRECTORY = "rcd"
    REMOTE_LIST_DIRECTORY = "rls"
    REMOTE_CREATE_DIRECTORY = "rmkdir"
    REMOTE_CURRENT_DIRECTORY = "rpwd"

    SCAN = "scan"
    OPEN = "open"

    GET = "get"
    PUT = "put"


SHELL_COMMANDS = values(Commands)

CLI_COMMANDS = [
    Commands.SCAN,
    Commands.GET
]

# === COMMANDS ARGUMENTS ===


class LsArguments:
    SORT_BY_SIZE = ["-s", "--sort"]


class OpenArguments:
    TIMEOUT = ["-t", "--timeout"]


class ScanArguments:
    TIMEOUT = ["-t", "--timeout"]


# === ERRORS ===


class ErrorsStrings:
    ERROR = "Error"
    INVALID_COMMAND_SYNTAX = "Invalid command syntax"
    NOT_IMPLEMENTED = "Not implemented"
    NOT_CONNECTED = "Invalid server name"
    COMMAND_EXECUTION_FAILED = "Command execution failed"
    SHARING_NOT_FOUND = "Sharing not found"
    INVALID_PATH = "Invalid path"
    INVALID_TRANSACTION = "Invalid transaction"

    COMMAND_NOT_RECOGNIZED = "Command not recognized"
    UNEXPECTED_SERVER_RESPONSE = "Unexpected server response"


ERRORS_STRINGS_MAP = {
    ServerErrors.ERROR: ErrorsStrings.ERROR,
    ServerErrors.INVALID_COMMAND_SYNTAX: ErrorsStrings.INVALID_COMMAND_SYNTAX,
    ServerErrors.NOT_IMPLEMENTED: ErrorsStrings.NOT_IMPLEMENTED,
    ServerErrors.NOT_CONNECTED: ErrorsStrings.NOT_CONNECTED,
    ServerErrors.COMMAND_EXECUTION_FAILED: ErrorsStrings.COMMAND_EXECUTION_FAILED,
    ServerErrors.SHARING_NOT_FOUND: ErrorsStrings.SHARING_NOT_FOUND,
    ServerErrors.INVALID_PATH: ErrorsStrings.INVALID_PATH,
    ServerErrors.INVALID_TRANSACTION: ErrorsStrings.INVALID_TRANSACTION,

    ClientErrors.COMMAND_NOT_RECOGNIZED: ErrorsStrings.COMMAND_NOT_RECOGNIZED,
    ClientErrors.INVALID_COMMAND_SYNTAX: ErrorsStrings.INVALID_COMMAND_SYNTAX,
    ClientErrors.COMMAND_EXECUTION_FAILED: ErrorsStrings.COMMAND_EXECUTION_FAILED,
    ClientErrors.UNEXPECTED_SERVER_RESPONSE: ErrorsStrings.UNEXPECTED_SERVER_RESPONSE,
    ClientErrors.NOT_CONNECTED: ErrorsStrings.NOT_CONNECTED,
    ClientErrors.INVALID_PATH: ErrorsStrings.INVALID_PATH,
    ClientErrors.SHARING_NOT_FOUND: ErrorsStrings.SHARING_NOT_FOUND,
}


def print_error(error_code: int):
    eprint(ERRORS_STRINGS_MAP.get(error_code, ErrorsStrings.ERROR))


def print_response_error(response: Response):
    if is_response_error(response):
        print_error(response["error"])

# ==================================================================


class Client:
    def __init__(self, server_discover_port: int):
        self.connection: Optional[Connection] = None

        self._server_discover_port = server_discover_port

        self._command_dispatcher: Dict[str, Callable[[Args], None]] = {
            Commands.LOCAL_CHANGE_DIRECTORY: self._cd,
            Commands.LOCAL_LIST_DIRECTORY: self._ls,
            Commands.LOCAL_CREATE_DIRECTORY: self._mkdir,
            Commands.LOCAL_CURRENT_DIRECTORY: self._pwd,

            Commands.REMOTE_CHANGE_DIRECTORY: self._rcd,
            Commands.REMOTE_LIST_DIRECTORY: self._rls,
            Commands.REMOTE_CREATE_DIRECTORY: self._rmkdir,
            Commands.REMOTE_CURRENT_DIRECTORY: self._rpwd,

            Commands.SCAN: self._scan,
            Commands.OPEN: self._open,

            Commands.GET: self._get,
        }


    def execute_command(self, command: str, args: Args) -> bool:
        if command not in self._command_dispatcher:
            return False

        t("Handling command %s (%s)", command, args)
        self._command_dispatcher[command](args)
        return True

    def is_connected(self):
        t("self.connection = %d", True if self.connection else False)
        return self.connection and self.connection.is_connected()


    # === LOCAL COMMANDS ===

    def _cd(self, args: Args):
        directory = args.get_param(default="/")

        i(">> CD " + directory)

        if not os.path.isdir(os.path.join(os.getcwd(), directory)):
            print_error(ClientErrors.INVALID_PATH)
            return

        try:
            os.chdir(directory)
        except Exception:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

    def _ls(self, args: Args):
        i(">> LS")

        if LsArguments.SORT_BY_SIZE in args:
            sort_by = "size"
        else:
            sort_by = "name"

        ls_result = utils.os.ls(os.getcwd(), sort_by=sort_by)
        if not ls_result:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

        self._print_file_infos(ls_result)

    def _mkdir(self, args: Args):
        directory = args.get_param()

        if not directory:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> MKDIR " + directory)

        try:
            os.mkdir(directory)
        except Exception:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

    def _pwd(self, _: Args):
        i(">> PWD")

        try:
            print(os.getcwd())
        except Exception:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

    # === REMOTE COMMANDS ===

    # RPWD

    def _rpwd(self, _: Args):
        if not self.connection:
            print_error(ClientErrors.NOT_CONNECTED)
            return

        i(">> RPWD")
        print(self.connection.rpwd())

    def _rcd(self, args: Args):
        if not self.connection:
            print_error(ClientErrors.NOT_CONNECTED)
            return

        directory = args.get_param(default="/")

        i(">> RCD %s", directory)

        resp = self.connection.rcd(directory)
        if is_response_success(resp):
            d("Successfully RCDed")
            pass
        else:
            self._handle_error_response(resp)

    def _rls(self, args: Args):
        if not self.connection:
            print_error(ClientErrors.NOT_CONNECTED)
            return

        if LsArguments.SORT_BY_SIZE in args:
            sort_by = "size"
        else:
            sort_by = "name"

        i(">> RLS (sort by %s)", sort_by)

        resp = self.connection.rls(sort_by)

        if is_response_success(resp) and "data" in resp:
            if not resp["data"]:
                return

            self._print_file_infos(resp["data"])

        else:
            self._handle_error_response(resp)

    def _rmkdir(self, args: Args):
        if not self.connection:
            print_error(ClientErrors.NOT_CONNECTED)
            return

        directory = args.get_param()

        if not directory:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> RMKDIR " + directory)

        resp = self.connection.rmkdir(directory)
        if is_response_success(resp):
            d("Successfully RMKDIRed")
            pass
        else:
            self._handle_error_response(resp)


    def _open(self, args: Args):
        sharing_name = args.get_param()
        if not sharing_name:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        timeout = to_int(args.get_param(OpenArguments.TIMEOUT,
                                        default=Discoverer.DEFAULT_TIMEOUT))

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

        Discoverer(self._server_discover_port, response_handler).discover(timeout)

        if not server_info:
            print_error(ClientErrors.SHARING_NOT_FOUND)
            return False

        if not self.connection:
            d("Creating new connection with %s", server_info["uri"])
            self.connection = Connection(server_info)
        else:
            d("Reusing existing connection with %s", server_info["uri"])

        # Actually send OPEN

        resp = self.connection.open(sharing_name)
        if is_response_success(resp):
            d("Successfully connected to %s:%d",
              server_info["ip"], server_info["port"])
        else:
            self._handle_error_response(resp)
            self.connection = None  # Invalidate connection

    def _scan(self, args: Args):
        timeout = to_int(args.get_param(OpenArguments.TIMEOUT,
                                        default=Discoverer.DEFAULT_TIMEOUT))

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

        Discoverer(self._server_discover_port, response_handler).discover(timeout)

        i("======================")

    def _get(self, args):
        if not self.connection:
            print_error(ClientErrors.NOT_CONNECTED)
            return

        i(">> GET %s", ", ".join(args))
        resp = self.connection.get(args)
        d("GET response\n%s", resp)

        if "data" not in resp or \
                "transaction" not in resp["data"] or \
                "port" not in resp["data"]:
            print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
            return

        transaction = resp["data"]["transaction"]
        port = resp["data"]["port"]

        if is_response_success(resp):
            d("Successfully GETed")

            transfer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            transfer_socket.connect((self.connection.server_info["ip"], port))

            while True:
                d("Fetching another file info")
                get_next_resp = self.connection.get_next(transaction)
                d("get_next()\n%s", get_next_resp)

                if "data" not in get_next_resp:
                    print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
                    return

                next_file = get_next_resp["data"]

                if next_file == "ok":
                    d("Nothing more to GET")
                    break

                d("NEXT: %s", next_file)
                file_len = next_file["length"]
                file_name = next_file["name"]

                c_rpwd = self.connection.rpwd()
                # FIND A BETTER NAME
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

        size_infos_str = []
        longest_size_str = 0

        for idx, info in enumerate(infos):
            size_info_str = utils.os.size_str(info["size"])
            size_infos_str[idx] = size_info_str
            longest_size_str = max(longest_size_str, len(size_info_str))

        t("longest_size_str %d", longest_size_str)

        for idx, info in enumerate(infos):
            t("f_info: %s", info)

            print("{}  {}  {}".format(
                ("D" if info["type"] == "dir" else "F"),
                size_infos_str[idx].rjust(longest_size_str),
                info["name"]))

    def _handle_error_response(self, resp: Response):
        if resp["error"] == ServerErrors.NOT_CONNECTED:
            d("Received a NOT_CONNECTED response: destroying connection")
            self.connection = None
        print_response_error(resp)


# ========================


class Shell:

    def __init__(self, client: Client):
        self.client = client
        self._suggestions = []
        self._shell_command_dispatcher: Dict[str, Callable[[Args], None]] = {
            Commands.HELP: self._help,
            Commands.EXIT: self._exit,
        }

        readline.set_completer(self.next_suggestion)
        readline.parse_and_bind("tab: complete")

    def next_suggestion(self, text, state):
        if state == 0:
            self._suggestions = [c for c in SHELL_COMMANDS if c.startswith(text)]
        if len(self._suggestions) > 0:
            return self._suggestions.pop()
        return None

    def input_loop(self):
        command = None
        while command != Commands.EXIT:
            try:
                prompt = self._build_prompt_string()
                command_line = input(prompt)

                command_line_parts = shlex.split(command_line)
                if len(command_line_parts) < 1:
                    print_error(ClientErrors.COMMAND_NOT_RECOGNIZED)
                    continue

                command = command_line_parts[0]
                command_args = Args(command_line_parts[1:])

                outcome = \
                    self._execute_shell_command(command, command_args) or \
                    self.client.execute_command(command, command_args)

                if not outcome:
                    print_error(ClientErrors.COMMAND_NOT_RECOGNIZED)
            except KeyboardInterrupt:
                d("CTRL+C detected")
                print()
            except EOFError:
                d("CTRL+D detected: exiting")
                break

    def _build_prompt_string(self):
        if self.client.is_connected():
            prompt_base = "{}:/{}  ##  ".format(
                self.client.connection.sharing_name(),
                self.client.connection.rpwd()
            ).rstrip()
        else:
            prompt_base = ""

        return prompt_base + os.getcwd() + "> "

    def _execute_shell_command(self, command: str, args: Args) -> bool:
        if command not in self._shell_command_dispatcher:
            return False

        t("Handling shell command %s (%s)", command, args)
        self._shell_command_dispatcher[command](args)
        return True

    def _help(self, _: Args):
        print(HELP_COMMANDS)

    def _exit(self, _: Args):
        pass


def main():
    args = Args(sys.argv[1:])

    init_logging_from_args(args, ClientArguments.VERBOSE)

    i(APP_INFO)
    d(args)

    if ClientArguments.HELP in args:
        terminate(HELP_APP)

    if ClientArguments.VERSION in args:
        terminate(APP_INFO)

    server_discover_port = DEFAULT_DISCOVER_PORT

    if ClientArguments.PORT in args:
        server_discover_port = to_int(args.get_param(ClientArguments.PORT))

    # Start in interactive mode
    client = Client(server_discover_port)

    # Allow some commands directly from command line
    # GET, SCAN
    full_command = args.get_params()

    if full_command:
        command = full_command.pop(0)

        if command not in CLI_COMMANDS:
            abort("Unknown command: {}".format(command))

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