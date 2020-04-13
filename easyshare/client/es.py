import os
import shlex
import socket
import sys
import readline
from typing import Optional, Callable, List, Dict

from easyshare.client.connection import Connection
from easyshare.client.discover import Discoverer
from easyshare.client.errors import ClientErrors
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.filetype import FTYPE_DIR, FTYPE_FILE
from easyshare.protocol.response import Response, is_error_response, is_success_response
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.shared.args import Args
from easyshare.shared.conf import APP_NAME_CLIENT, APP_NAME_CLIENT_SHORT, APP_VERSION, DEFAULT_DISCOVER_PORT
from easyshare.shared.endpoint import Endpoint
from easyshare.shared.log import i, d, w, init_logging, v, VERBOSITY_VERBOSE, get_verbosity, VERBOSITY_MAX, \
    VERBOSITY_NONE, VERBOSITY_ERROR, VERBOSITY_WARNING, VERBOSITY_INFO, VERBOSITY_DEBUG
from easyshare.shared.trace import init_tracing, is_tracing_enabled
from easyshare.utils.app import eprint, terminate, abort
from easyshare.utils.obj import values
from easyshare.utils.types import to_int
from easyshare.utils.os import ls, size_str

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
    TRACE =     ["-t", "--trace"]
    VERBOSE =   ["-v", "--verbose"]
    PORT =      ["-p", "--port"]
    HELP =      ["-h", "--help"]
    VERSION =   ["-V", "--version"]


# === COMMANDS ===


class Commands:
    HELP = "help"
    EXIT = "exit"

    TRACE = "trace"
    TRACE_SHORT = "t"

    VERBOSE = "verbose"
    VERBOSE_SHORT = "v"

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
    SORT_BY_SIZE = ["-S", "-s", "--sort"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]


class OpenArguments:
    TIMEOUT = ["-T", "--timeout"]


class ScanArguments:
    TIMEOUT = ["-T", "--timeout"]


# === ERRORS ===


class ErrorsStrings:
    ERROR = "Error"
    INVALID_COMMAND_SYNTAX = "Invalid command syntax"
    INVALID_PARAMETER_VALUE = "Invalid parameter value"
    NOT_IMPLEMENTED = "Not implemented"
    NOT_CONNECTED = "Not connected"
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
    ClientErrors.INVALID_PARAMETER_VALUE: ErrorsStrings.INVALID_PARAMETER_VALUE,
    ClientErrors.COMMAND_EXECUTION_FAILED: ErrorsStrings.COMMAND_EXECUTION_FAILED,
    ClientErrors.UNEXPECTED_SERVER_RESPONSE: ErrorsStrings.UNEXPECTED_SERVER_RESPONSE,
    ClientErrors.NOT_CONNECTED: ErrorsStrings.NOT_CONNECTED,
    ClientErrors.INVALID_PATH: ErrorsStrings.INVALID_PATH,
    ClientErrors.SHARING_NOT_FOUND: ErrorsStrings.SHARING_NOT_FOUND,
}


def error_string(error_code: int) -> str:
    return ERRORS_STRINGS_MAP.get(error_code, ErrorsStrings.ERROR)


def print_error(error_code: int):
    eprint(error_string(error_code))


def print_response_error(resp: Response):
    if is_error_response(resp):
        print_error(resp["error"])


# ==================================================================


class Client:
    def __init__(self, server_discover_port: int):
        self.connection: Optional[Connection] = None

        self._server_discover_port = server_discover_port

        self._command_dispatcher: Dict[str, Callable[[Args], None]] = {
            Commands.TRACE: self._trace,
            Commands.TRACE_SHORT: self._trace,
            Commands.VERBOSE: self._verbose,
            Commands.VERBOSE_SHORT: self._verbose,

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

        d("Handling command %s (%s)", command, args)
        self._command_dispatcher[command](args)
        return True

    def is_connected(self):
        return self.connection and self.connection.is_connected()

    # === LOCAL COMMANDS ===

    def _trace(self, args: Args):
        enable = to_int(args.get_param())

        if enable is None:
            # Toggle tracing if no parameter is provided
            enable = not is_tracing_enabled()

        i(">> TRACE (%d)", enable)

        init_tracing(enable)

        print("Tracing = {:d}{}".format(
            enable,
            " (enabled)" if enable else " (disabled)"
        ))

    def _verbose(self, args: Args):
        verbosity = to_int(args.get_param())

        if verbosity is None:
            # Increase verbosity (or disable if is already max)
            verbosity = (get_verbosity() + 1) % (VERBOSITY_MAX + 1)

        i(">> VERBOSE (%d)", verbosity)

        init_logging(verbosity)


        VERBOSITY_EXPLANATION_MAP = {
            VERBOSITY_NONE: " (disabled)",
            VERBOSITY_ERROR: " (error)",
            VERBOSITY_WARNING: " (error / warn)",
            VERBOSITY_INFO: " (error / warn / info)",
            VERBOSITY_VERBOSE: " (error / warn / info / verbose)",
            VERBOSITY_DEBUG: " (error / warn / info / verbose / debug)",
        }

        if verbosity not in VERBOSITY_EXPLANATION_MAP:
            verbosity = max(min(verbosity, VERBOSITY_DEBUG), VERBOSITY_NONE)

        print("Verbosity = {:d}{}".format(
            verbosity,
            VERBOSITY_EXPLANATION_MAP.get(verbosity, "")
        ))


    def _cd(self, args: Args):
        directory = args.get_param(default="/")

        i(">> CD %s", directory)

        if not os.path.isdir(os.path.join(os.getcwd(), directory)):
            print_error(ClientErrors.INVALID_PATH)
            return

        try:
            os.chdir(directory)
        except Exception:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

    def _ls(self, args: Args):
        sort_by = ["name"]
        reverse = LsArguments.REVERSE in args

        if LsArguments.SORT_BY_SIZE in args:
            sort_by.append("size")
        if LsArguments.GROUP in args:
            sort_by.append("ftype")

        i(">> LS (sort by %s%s)", sort_by, " | reverse" if reverse else "")

        ls_result = ls(os.getcwd(), sort_by=sort_by, reverse=reverse)
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
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        i(">> RPWD")
        print(self.connection.rpwd())

    def _rcd(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        directory = args.get_param(default="/")

        i(">> RCD %s", directory)

        resp = self.connection.rcd(directory)
        if is_success_response(resp):
            v("Successfully RCDed")
        else:
            self._handle_error_response(resp)

    def _rls(self, args: Args):
        if not self.connection:
            print_error(ClientErrors.NOT_CONNECTED)
            return

        sort_by = ["name"]
        reverse = LsArguments.REVERSE in args

        if LsArguments.SORT_BY_SIZE in args:
            sort_by.append("size")
        if LsArguments.GROUP in args:
            sort_by.append("ftype")

        i(">> RLS (sort by %s%s)", sort_by, " | reverse" if reverse else "")

        resp = self.connection.rls(sort_by, reverse=reverse)

        if is_success_response(resp):
            self._print_file_infos(resp.get("data"))
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
        if is_success_response(resp):
            v("Successfully RMKDIRed")
            pass
        else:
            self._handle_error_response(resp)

    def _open(self, args: Args):
        #                    |------sharing_location-----|
        # open <sharing_name>[@<hostname> | @<ip>[:<port>]]
        #      |_________________________________________|
        #               sharing specifier

        sharing_specifier = args.get_param()

        if not sharing_specifier:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        timeout = to_int(args.get_param(OpenArguments.TIMEOUT,
                                        default=Discoverer.DEFAULT_TIMEOUT))

        if not timeout:
            print_error(ClientErrors.INVALID_PARAMETER_VALUE)
            return False

        sharing_name, _, sharing_location = sharing_specifier.partition("@")

        i(">> OPEN %s%s (timeout = %d)",
          sharing_name,
          "@{}".format(sharing_location) if sharing_location else "",
          timeout)

        server_info: Optional[ServerInfo] = None

        def response_handler(client_endpoint: Endpoint,
                             a_server_info: ServerInfo) -> bool:
            nonlocal server_info
            d("Handling DISCOVER response from %s\n%s",
              str(client_endpoint), str(a_server_info))

            # If the sharing_location is specified, it must match

            if sharing_location and \
                    sharing_location != a_server_info.get("name") and \
                    sharing_location != a_server_info.get("ip") and \
                    sharing_location != "{}:{}".format(a_server_info.get("ip"),
                                                       a_server_info.get("port")):
                d("Discarding server info which does not match the sharing_location %s", sharing_location)
                return True  # Continue DISCOVER

            # If we are here, the sharing_location either is
            # not specified or it does match
            # Let's see if it has the right sharing
            for sharing_info in a_server_info.get("sharings"):
                # Check whether this server has a sharing with the name
                # we are looking for
                if sharing_info.get("name") == sharing_name:
                    d("Sharing [%s] found at %s:%d",
                      sharing_info.get("name"),
                      a_server_info.get("ip"),
                      a_server_info.get("port"))
                    server_info = a_server_info

                    # Check if it is actually a directory
                    if sharing_info.get("ftype") == FTYPE_DIR:
                        return False    # Stop DISCOVER
                    else:
                        w("The sharing %s is not a directory; cannot open", sharing_name)

            return True             # Continue DISCOVER

        Discoverer(self._server_discover_port, response_handler).discover(timeout)

        if not server_info:
            print_error(ClientErrors.SHARING_NOT_FOUND)
            return False

        if not self.connection:
            d("Creating new connection with %s", server_info.get("uri"))
            self.connection = Connection(server_info)
        else:
            d("Reusing existing connection with %s", server_info.get("uri"))

        # Actually send OPEN

        resp = self.connection.open(sharing_name)
        if is_success_response(resp):
            d("Successfully connected to %s:%d",
              server_info.get("ip"), server_info.get("port"))
        else:
            self._handle_error_response(resp)
            self.connection = None  # Invalidate connection

    def _scan(self, args: Args):
        timeout = to_int(args.get_param(ScanArguments.TIMEOUT,
                                        default=Discoverer.DEFAULT_TIMEOUT))

        if not timeout:
            print_error(ClientErrors.INVALID_PARAMETER_VALUE)
            return False

        i(">> SCAN (timeout = %d)", timeout)

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
                  .format(server_info.get("name"),
                          server_info.get("ip"),
                          server_info.get("port")))

            print("  DIRECTORIES")

            for sharing_info in server_info.get("sharings"):
                if sharing_info.get("ftype") == FTYPE_DIR:
                    print("   > " + sharing_info.get("name"))

            print("  FILES")

            for sharing_info in server_info.get("sharings"):
                if sharing_info.get("ftype") == FTYPE_FILE:
                    print("   > " + sharing_info.get("name"))

            servers_found += 1

            return True     # Go ahead

        Discoverer(self._server_discover_port, response_handler).discover(timeout)

        i("======================")

    def _get(self, args):
        # TODO: refactor this
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

        if is_success_response(resp):
            v("Successfully GETed")

            transfer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            transfer_socket.connect((self.connection.server_info.ip, port))

            while True:
                v("Fetching another file info")
                get_next_resp = self.connection.get_next(transaction)
                d("get_next()\n%s", get_next_resp)

                if "data" not in get_next_resp:
                    print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
                    return

                next_file = get_next_resp["data"]

                if next_file == "ok":
                    v("Nothing more to GET")
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
                v("Creating intermediate dirs locally")
                head, tail = os.path.split(trail_file_name)
                if head:
                    os.makedirs(head, exist_ok=True)

                v("Opening file locally")
                file = open(trail_file_name, "wb")

                # Really get it

                BUFFER_SIZE = 4096

                read = 0
                while read < file_len:
                    recv_dim = min(BUFFER_SIZE, file_len - read)
                    chunk = transfer_socket.recv(recv_dim)

                    if not chunk:
                        v("END")
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
                    d("File OK (length match)")
                else:
                    w("File length mismatch. %d != %d",
                                    os.path.getsize(trail_file_name), file_len)
                    exit(-1)

            v("Closing socket")
            transfer_socket.close()
        else:
            self._handle_error_response(resp)

    def _print_file_infos(self, infos: List[FileInfo]):
        size_infos_str = []
        longest_size_str = 0

        for idx, info in enumerate(infos):
            size_info_str = size_str(info.get("size"))
            size_infos_str.append(size_info_str)
            longest_size_str = max(longest_size_str, len(size_info_str))

        d("longest_size_str %d", longest_size_str)

        for idx, info in enumerate(infos):
            d("f_info: %s", info)

            print("{}  {}  {}".format(
                ("D" if info.get("ftype") == FTYPE_DIR else "F"),
                size_infos_str[idx].rjust(longest_size_str),
                info.get("name")))

    def _handle_error_response(self, resp: Response):
        if is_error_response(ServerErrors.NOT_CONNECTED):
            v("Received a NOT_CONNECTED response: destroying connection")
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

                try:
                    command_line_parts = shlex.split(command_line)
                except ValueError:
                    w("Invalid command line")
                    print_error(ClientErrors.COMMAND_NOT_RECOGNIZED)
                    continue

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
                v("CTRL+C detected")
                print()
            except EOFError:
                v("CTRL+D detected: exiting")
                break

    def _build_prompt_string(self):
        if self.client.is_connected():
            prompt_base = "{}:/{}  ##  ".format(
                self.client.connection.sharing_name(),
                self.client.connection.rpwd()
            )
        else:
            prompt_base = ""

        return prompt_base + os.getcwd() + "> "

    def _execute_shell_command(self, command: str, args: Args) -> bool:
        if command not in self._shell_command_dispatcher:
            return False

        d("Handling shell command %s (%s)", command, args)
        self._shell_command_dispatcher[command](args)
        return True

    def _help(self, _: Args):
        print(HELP_COMMANDS)

    def _exit(self, _: Args):
        pass


def main():
    args = Args(sys.argv[1:])

    verbosity = 0
    tracing = 0

    if ClientArguments.VERBOSE in args:
        verbosity = to_int(args.get_param(ClientArguments.VERBOSE, default=VERBOSITY_VERBOSE))
        if verbosity is None:
            abort("Invalid --verbose parameter value")

    if ClientArguments.TRACE in args:
        tracing = to_int(args.get_param(ClientArguments.TRACE, default=1))
        if tracing is None:
            abort("Invalid --trace parameter value")

    init_logging(verbosity)
    init_tracing(True if tracing else False)

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
        v("Executing shell")
        shell = Shell(client)
        shell.input_loop()


if __name__ == "__main__":
    main()
