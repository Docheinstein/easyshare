import enum
import os
import random
import shlex
import shutil
import sys
import readline
import time
from inspect import Traceback
from stat import S_ISDIR, S_ISREG
from typing import Optional, Callable, List, Dict, Union, Tuple, Any

import Pyro4
from Pyro4 import util
from Pyro4.core import _BatchProxyAdapter
from Pyro4.errors import ConnectionClosedError, PyroError
from anytree import AnyNode, RenderTree

from easyshare.client.connection import Connection
from easyshare.client.discover import Discoverer
from easyshare.client.errors import ClientErrors
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.filetype import FTYPE_DIR, FTYPE_FILE, FileType
from easyshare.protocol.iserver import IServer
from easyshare.protocol.response import Response, is_error_response, is_success_response, is_data_response
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.protocol.sharinginfo import SharingInfo
from easyshare.shared.args import Args
from easyshare.shared.conf import APP_NAME_CLIENT, APP_NAME_CLIENT_SHORT, APP_VERSION, DEFAULT_DISCOVER_PORT, DIR_COLOR, \
    FILE_COLOR, PROGRESS_COLOR, DONE_COLOR
from easyshare.shared.endpoint import Endpoint
from easyshare.shared.log import i, d, w, init_logging, v, VERBOSITY_VERBOSE, get_verbosity, VERBOSITY_MAX, \
    VERBOSITY_NONE, VERBOSITY_ERROR, VERBOSITY_WARNING, VERBOSITY_INFO, VERBOSITY_DEBUG, e
from easyshare.shared.progress import FileProgressor
from easyshare.shared.trace import init_tracing, is_tracing_enabled
from easyshare.socket.tcp import SocketTcpOut
from easyshare.tree.tree import TreeNodeDict, TreeRenderPostOrder
from easyshare.utils.app import eprint, terminate, abort
from easyshare.utils.colors import init_colors, Color, red, fg
from easyshare.utils.env import terminal_size
from easyshare.utils.json import json_to_pretty_str
from easyshare.utils.obj import values
from easyshare.utils.types import to_int, to_bool, str_to_bool, bool_to_str
from easyshare.utils.os import ls, size_str, rm, tree, mv, cp

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
    NO_COLOR =  ["--no-color"]


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
    LOCAL_TREE_DIRECTORY = "tree"
    LOCAL_CREATE_DIRECTORY = "mkdir"
    LOCAL_CURRENT_DIRECTORY = "pwd"
    LOCAL_REMOVE = "rm"
    LOCAL_MOVE = "mv"
    LOCAL_COPY = "cp"

    REMOTE_CHANGE_DIRECTORY = "rcd"
    REMOTE_LIST_DIRECTORY = "rls"
    REMOTE_TREE_DIRECTORY = "rtree"
    REMOTE_CREATE_DIRECTORY = "rmkdir"
    REMOTE_CURRENT_DIRECTORY = "rpwd"
    REMOTE_REMOVE = "rrm"
    REMOTE_MOVE = "rmv"
    REMOTE_COPY = "rcp"

    SCAN = "scan"
    OPEN = "open"
    CLOSE = "close"

    GET = "get"
    PUT = "put"

    INFO = "info"
    PING = "ping"


SHELL_COMMANDS = values(Commands)

CLI_COMMANDS = [
    Commands.SCAN,
    Commands.OPEN,
    Commands.GET,
    Commands.INFO,
]

# === COMMANDS ARGUMENTS ===


class LsArguments:
    SORT_BY_SIZE = ["-s", "--sort-size"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]
    SIZE = ["-S"]


class TreeArguments:
    SORT_BY_SIZE = ["-s", "--sort-size"]
    REVERSE = ["-r", "--reverse"]
    GROUP = ["-g", "--group"]
    MAX_DEPTH = ["-d", "--depth"]
    SIZE = ["-S"]


class OpenArguments:
    TIMEOUT = ["-T", "--timeout"]


class ScanArguments:
    TIMEOUT = ["-T", "--timeout"]


class GetArguments:
    YES_TO_ALL = ["-Y", "--yes"]
    NO_TO_ALL = ["-N", "--no"]


# === MISC ===

class GetMode(enum.Enum):
    FILES = "files"
    SHARING = "sharing"

# === ERRORS ===


class ErrorsStrings:
    ERROR = "Error"
    INVALID_COMMAND_SYNTAX = "Invalid command syntax"
    INVALID_PARAMETER_VALUE = "Invalid parameter value"
    NOT_IMPLEMENTED = "Not implemented"
    NOT_CONNECTED = "Not connected"
    COMMAND_EXECUTION_FAILED = "Command execution failed"
    SHARING_NOT_FOUND = "Sharing not found"
    SERVER_NOT_FOUND = "Server not found"
    INVALID_PATH = "Invalid path"
    INVALID_TRANSACTION = "Invalid transaction"

    COMMAND_NOT_RECOGNIZED = "Command not recognized"
    UNEXPECTED_SERVER_RESPONSE = "Unexpected server response"
    IMPLEMENTATION_ERROR = "Implementation error"
    CONNECTION_ERROR = "Connection error"


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
    ClientErrors.SERVER_NOT_FOUND: ErrorsStrings.SERVER_NOT_FOUND,
    ClientErrors.IMPLEMENTATION_ERROR: ErrorsStrings.IMPLEMENTATION_ERROR,
    ClientErrors.CONNECTION_ERROR: ErrorsStrings.CONNECTION_ERROR,
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
            Commands.TRACE: self.trace,
            Commands.TRACE_SHORT: self.trace,
            Commands.VERBOSE: self.verbose,
            Commands.VERBOSE_SHORT: self.verbose,

            Commands.LOCAL_CHANGE_DIRECTORY: self.cd,
            Commands.LOCAL_LIST_DIRECTORY: self.ls,
            Commands.LOCAL_TREE_DIRECTORY: self.tree,
            Commands.LOCAL_CREATE_DIRECTORY: self.mkdir,
            Commands.LOCAL_CURRENT_DIRECTORY: self.pwd,
            Commands.LOCAL_REMOVE: self.rm,
            Commands.LOCAL_MOVE: self.mv,
            Commands.LOCAL_COPY: self.cp,

            Commands.REMOTE_CHANGE_DIRECTORY: self.rcd,
            Commands.REMOTE_LIST_DIRECTORY: self.rls,
            Commands.REMOTE_TREE_DIRECTORY: self.rtree,
            Commands.REMOTE_CREATE_DIRECTORY: self.rmkdir,
            Commands.REMOTE_CURRENT_DIRECTORY: self.rpwd,
            Commands.REMOTE_REMOVE: self.rrm,
            Commands.REMOTE_MOVE: self.rmv,
            Commands.REMOTE_COPY: self.rcp,

            Commands.SCAN: self.scan,
            Commands.OPEN: self.open,
            Commands.CLOSE: self.close,

            Commands.GET: self.get,
            Commands.PUT: self.put,

            Commands.INFO: self.info,

            Commands.PING: self.ping,
        }

    def execute_command(self, command: str, args: Args) -> bool:
        if command not in self._command_dispatcher:
            return False

        d("Client: handling command %s (%s)", command, args)
        self._command_dispatcher[command](args)
        return True

    def is_connected(self):
        return self.connection and self.connection.is_connected()

    # === LOCAL COMMANDS ===

    def trace(self, args: Args):
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

    def verbose(self, args: Args):
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

    def cd(self, args: Args):
        directory = args.get_param(default="/")

        i(">> CD %s", directory)

        if not os.path.isdir(os.path.join(os.getcwd(), directory)):
            print_error(ClientErrors.INVALID_PATH)
            return

        try:
            os.chdir(directory)
        except Exception:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

    def ls(self, args: Args):
        sort_by = ["name"]
        reverse = LsArguments.REVERSE in args

        if LsArguments.SORT_BY_SIZE in args:
            sort_by.append("size")
        if LsArguments.GROUP in args:
            sort_by.append("ftype")

        i(">> LS (sort by %s%s)", sort_by, " | reverse" if reverse else "")

        ls_result = ls(os.getcwd(), sort_by=sort_by, reverse=reverse)
        if ls_result is None:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

        Client._print_list_files_info(ls_result, show_size=LsArguments.SIZE in args)

    def tree(self, args: Args):
        sort_by = ["name"]
        reverse = TreeArguments.REVERSE in args

        if TreeArguments.SORT_BY_SIZE in args:
            sort_by.append("size")
        if TreeArguments.GROUP in args:
            sort_by.append("ftype")

        # FIXME: max_depth = 0
        max_depth = to_int(args.get_param(TreeArguments.MAX_DEPTH))

        i(">> TREE (sort by %s%s)", sort_by, " | reverse" if reverse else "")

        tree_root = tree(os.getcwd(), sort_by=sort_by, reverse=reverse, max_depth=max_depth)

        if tree_root is None:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

        Client._print_tree_files_info(tree_root,
                                      max_depth=max_depth,
                                      show_size=TreeArguments.SIZE in args)

    def mkdir(self, args: Args):
        directory = args.get_param()

        if not directory:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> MKDIR " + directory)

        try:
            os.mkdir(directory)
        except Exception:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

    def pwd(self, _: Args):
        i(">> PWD")

        try:
            print(os.getcwd())
        except Exception:
            print_error(ClientErrors.COMMAND_EXECUTION_FAILED)

    def rm(self, args: Args):
        paths = args.get_params()

        if not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> RM %s", paths)

        def handle_rm_error(err):
            eprint(err)

        for path in paths:
            rm(path, error_callback=handle_rm_error)

    def mv(self, args: Args):
        """
        mv <src>... <dest>

        A1  At least two parameters
        A2  If a <src> doesn't exist => IGNORES it

        2 args:
        B1  If <dest> exists
            B1.1    If type of <dest> is DIR => put <src> into <dest> anyway

            B1.2    If type of <dest> is FILE
                B1.2.1  If type of <src> is DIR => ERROR
                B1.2.2  If type of <src> is FILE => OVERWRITE
        B2  If <dest> doesn't exist => preserve type of <src>

        3 args:
        C1  if <dest> exists => must be a dir
        C2  If <dest> doesn't exist => ERROR

        """
        mv_args = args.get_params()
        args_count = len(mv_args)

        if not mv_args or args_count < 2:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        dest = mv_args.pop()

        # C1/C2 check: with 3+ arguments
        if args_count >= 3:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not os.path.isdir(dest):
                eprint("'%s' must be an existing directory", dest)
                return

        # Every other constraint is well handled by shutil.move()
        errors = []

        for src in mv_args:
            v(">> MV <%s> <%s>", src, dest)
            try:
                mv(src, dest)
            except Exception as ex:
                errors.append(str(ex))

        if errors:
            e("%d errors occurred", len(errors))

        for err in errors:
            eprint(err)


    def cp(self, args: Args):

        cp_args = args.get_params()
        args_count = len(cp_args)

        if not cp_args or args_count < 2:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        dest = cp_args.pop()

        # C1/C2 check: with 3+ arguments
        if args_count >= 3:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not os.path.isdir(dest):
                eprint("'%s' must be an existing directory", dest)
                return

        # Every other constraint is well handled by shutil.move()
        errors = []

        for src in cp_args:
            v(">> CP <%s> <%s>", src, dest)
            try:
                cp(src, dest)
            except Exception as ex:
                errors.append(str(ex))

        if errors:
            e("%d errors occurred", len(errors))

        for err in errors:
            eprint(err)

    # === REMOTE COMMANDS ===

    # RPWD

    def rpwd(self, _: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        i(">> RPWD")
        print(self.connection.rpwd())

    def rcd(self, args: Args):
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


    def rls(self, args: Args):
        if not self.is_connected():
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

        if not is_data_response(resp):
            self._handle_error_response(resp)
            return

        Client._print_list_files_info(resp.get("data"),
                                      show_size=LsArguments.SIZE in args)

    def rtree(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        sort_by = ["name"]
        reverse = TreeArguments.REVERSE in args

        if TreeArguments.SORT_BY_SIZE in args:
            sort_by.append("size")
        if TreeArguments.GROUP in args:
            sort_by.append("ftype")

        # FIXME: max_depth = 0
        max_depth = to_int(args.get_param(TreeArguments.MAX_DEPTH))

        i(">> RTREE (sort by %s%s)", sort_by, " | reverse" if reverse else "")

        resp = self.connection.rtree(sort_by, reverse=reverse, depth=max_depth)

        if not is_data_response(resp):
            self._handle_error_response(resp)
            return

        Client._print_tree_files_info(resp.get("data"),
                                      max_depth=max_depth,
                                      show_size=TreeArguments.SIZE in args)

    def rmkdir(self, args: Args):
        if not self.is_connected():
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

    def rrm(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        paths = args.get_params()

        if not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> RRM %s ", paths)

        resp = self.connection.rrm(paths)
        if is_success_response(resp):
            v("Successfully RRMed")
            if is_data_response(resp):
                errors = resp.get("data").get("errors")
                if errors:
                    e("%d errors occurred while doing rrm", len(errors))
                    for err in errors:
                        eprint(err)
        else:
            self._handle_error_response(resp)

    def rcp(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        paths = args.get_params()

        if not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        dest = paths.pop()

        if not dest or not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> RCP %s -> %s", str(paths), dest)

        resp = self.connection.rcp(paths, dest)
        if is_success_response(resp):
            v("Successfully RCPed")

            if is_data_response(resp):
                errors = resp.get("data").get("errors")
                if errors:
                    e("%d errors occurred while doing rcp", len(errors))
                    for err in errors:
                        eprint(err)

        else:
            self._handle_error_response(resp)

    def rmv(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        paths = args.get_params()

        if not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        dest = paths.pop()

        if not dest or not paths:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        i(">> RMV %s -> %s", str(paths), dest)

        resp = self.connection.rmv(paths, dest)
        if is_success_response(resp):
            v("Successfully RMVed")

            if is_data_response(resp):
                errors = resp.get("data").get("errors")
                if errors:
                    e("%d errors occurred while doing rmv", len(errors))
                    for err in errors:
                        eprint(err)

        else:
            self._handle_error_response(resp)


    def open(self, args: Args):
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

        server_info: ServerInfo = self._discover_sharing(
            name=sharing_name,
            location=sharing_location,
            ftype=FTYPE_DIR,
            timeout=timeout
        )

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
            v("Successfully connected to %s:%d",
              server_info.get("ip"), server_info.get("port"))
        else:
            self._handle_error_response(resp)
            self.close()

    def close(self, _: Optional[Args] = None):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        i(">> CLOSE")

        self.connection.close()  # async call
        self.connection = None   # Invalidate connection

    def scan(self, args: Args):
        timeout = to_int(args.get_param(ScanArguments.TIMEOUT,
                                        default=Discoverer.DEFAULT_TIMEOUT))

        if not timeout:
            print_error(ClientErrors.INVALID_PARAMETER_VALUE)
            return False

        i(">> SCAN (timeout = %d)", timeout)

        servers_found = 0

        def response_handler(client: Endpoint,
                             server_info: ServerInfo) -> bool:
            nonlocal servers_found

            d("Handling DISCOVER response from %s\n%s", str(client), str(server_info))
            # Print as soon as they come

            if not servers_found:
                i("======================")
            else:
                print("")

            print("{} ({}:{})"
                  .format(server_info.get("name"),
                          server_info.get("ip"),
                          server_info.get("port")))

            Client._print_sharings(server_info.get("sharings"))

            servers_found += 1

            return True     # Go ahead

        Discoverer(self._server_discover_port, response_handler).discover(timeout)

        i("======================")

    def info(self, args: Args):
        # Can be done either
        # 1. If connected to a server: we already have the server info
        # 2. If not connected to a server: we have to fetch the server info

        # Without parameter it means we are trying to see the info of the
        # current connection
        # With a paremeter it means we are trying to see the info of a server
        # The param should be <hostname> | <ip[:port]>

        def print_server_info(server_info: ServerInfo):
            print(
                "Name: {}\n"
                "IP: {}\n"
                "Port: {}\n"
                "Auth: {}\n"
                "Sharings\n{}"
                .format(
                    server_info.get("name"),
                    server_info.get("ip"),
                    server_info.get("port"),
                    bool_to_str(server_info.get("auth"), "yes", "no"),
                    Client._sharings_string(server_info.get("sharings"))
                )
            )

        if self.is_connected():
            # Connected, print current server info
            d("Info while connected, printing current server info")
            print_server_info(self.connection.server_info)
        else:
            # Not connected, we need a parameter that specifies the server
            server_specifier = args.get_param()

            if not server_specifier:
                e("Server specifier not found")
                print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
                return

            i(">> INFO %s", server_specifier)

            server_info: ServerInfo = self._discover_server(
                location=server_specifier
            )

            if not server_info:
                print_error(ClientErrors.SERVER_NOT_FOUND)
                return False

            # Server info retrieved successfully
            print_server_info(server_info)

    def ping(self, _: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        resp = self.connection.ping()
        if is_data_response(resp) and resp.get("data") == "pong":
            print("Connection is UP")
        else:
            print("Connection is DOWN")



    def put_files(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        files = args.get_params(default=[])

        i(">> PUT [files] %s", files)
        self._do_put(self.connection, files, args)


    def put_sharing(self, args: Args):
        if self.is_connected():
            # We should not reach this point if we are connected to a sharing
            print_error(ClientErrors.IMPLEMENTATION_ERROR)
            return

        params = args.get_params()
        sharing_specifier = params.pop(0)

        if not sharing_specifier:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        sharing_name, _, sharing_location = sharing_specifier.rpartition("@")

        if not sharing_name:
            # if @ is not found, rpartition put the entire string on
            # the last element of th tuple
            sharing_name = sharing_location
            sharing_location = None

        timeout = to_int(args.get_param(ScanArguments.TIMEOUT,
                                        default=Discoverer.DEFAULT_TIMEOUT))

        if not timeout:
            print_error(ClientErrors.INVALID_PARAMETER_VALUE)
            return False

        # We have to perform a discover

        server_info: ServerInfo = self._discover_sharing(
            name=sharing_name,
            location=sharing_location,
            timeout=timeout
        )

        if not server_info:
            print_error(ClientErrors.SHARING_NOT_FOUND)
            return False

        d("Creating new temporary connection with %s", server_info.get("uri"))
        connection = Connection(server_info)

        # Open connection

        v("Opening temporary connection")
        open_response = connection.open(sharing_name)

        if not is_success_response(open_response):
            w("Cannot open connection; aborting")
            print_response_error(open_response)
            return

        files = ["."] if not params else params
        i(">> PUT [sharing] %s %s", sharing_name)
        self._do_put(connection, files, args)

        # Close connection
        d("Closing temporary connection")
        connection.close()

    def get_files(self, args: Args):
        if not self.is_connected():
            print_error(ClientErrors.NOT_CONNECTED)
            return

        files = args.get_params(default=[])

        i(">> GET [files] %s", files)
        self._do_get(self.connection, files, args)

    def get_sharing(self, args: Args):
        if self.is_connected():
            # We should not reach this point if we are connected to a sharing
            print_error(ClientErrors.IMPLEMENTATION_ERROR)
            return

        params = args.get_params()
        sharing_specifier = params.pop(0)

        if not sharing_specifier:
            print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
            return

        sharing_name, _, sharing_location = sharing_specifier.rpartition("@")

        if not sharing_name:
            # if @ is not found, rpartition put the entire string on
            # the last element of th tuple
            sharing_name = sharing_location
            sharing_location = None

        timeout = to_int(args.get_param(ScanArguments.TIMEOUT,
                                        default=Discoverer.DEFAULT_TIMEOUT))

        if not timeout:
            print_error(ClientErrors.INVALID_PARAMETER_VALUE)
            return False

        # We have to perform a discover

        server_info: ServerInfo = self._discover_sharing(
            name=sharing_name,
            location=sharing_location,
            timeout=timeout
        )

        if not server_info:
            print_error(ClientErrors.SHARING_NOT_FOUND)
            return False

        d("Creating new temporary connection with %s", server_info.get("uri"))
        connection = Connection(server_info)

        # Open connection

        v("Opening temporary connection")
        open_response = connection.open(sharing_name)

        if not is_success_response(open_response):
            w("Cannot open connection; aborting")
            print_response_error(open_response)
            return

        files = ["."] if not params else params
        i(">> GET [sharing] %s %s", sharing_name)
        self._do_get(connection, files, args)

        # Close connection
        d("Closing temporary connection")
        connection.close()

    def _do_put(self,
                connection: Connection,
                files: List[str],
                args: Args):
        if not connection.is_connected():
            e("Connection must be opened for do GET")
            return

        if len(files) == 0:
            files = ["."]

        put_response = connection.put()

        # if not is_data_response(put_response):
        #     print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
        #     return

        if not is_success_response(put_response):
            Client._handle_connection_error_response(connection, put_response)
            return

        transaction_id = put_response["data"].get("transaction")
        port = put_response["data"].get("port")

        if not transaction_id or not port:
            print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
            return

        v("Successfully PUTed")
        transfer_socket = SocketTcpOut(connection.server_info.get("ip"), port)

        files = sorted(files, reverse=True)
        sendfiles: List[dict] = []

        for f in files:
            _, trail = os.path.split(f)
            d("-> trail: %s", trail)
            sendfile = {
                "local": f,
                "remote": trail
            }
            d("Adding sendfile %s", json_to_pretty_str(sendfile))
            sendfiles.append(sendfile)


        def send_file(local_path: str, remote_path: str):
            fstat = os.lstat(local_path)
            fsize = fstat.st_size

            if S_ISDIR(fstat.st_mode):
                ftype = FTYPE_DIR
            elif S_ISREG(fstat.st_mode):
                ftype = FTYPE_FILE
            else:
                w("Unknown file type")
                return

            finfo = {
                "name": remote_path,
                "ftype": ftype,
                "size": fsize
            }

            d("send_file finfo: %s", json_to_pretty_str(finfo))

            d("doing a put_next_info")

            resp = connection.put_next_info(transaction_id, finfo)

            if not is_success_response(resp):
                Client._handle_connection_error_response(connection, resp)
                return

            progressor = FileProgressor(
                fsize,
                description="PUT " + local_path,
                color_progress=PROGRESS_COLOR,
                color_done=DONE_COLOR
            )

            if ftype == FTYPE_DIR:
                d("Sent a DIR, nothing else to do")
                progressor.done()
                return

            d("Actually sending the file")

            BUFFER_SIZE = 4096

            f = open(local_path, "rb")

            cur_pos = 0

            while cur_pos < fsize:
                r = random.random() * 0.001
                time.sleep(0.001 + r)

                chunk = f.read(BUFFER_SIZE)
                d("Read chunk of %dB", len(chunk))

                if not chunk:
                    d("Finished %s", local_path)
                    # FIXME: sending something?
                    break

                transfer_socket.send(chunk)

                cur_pos += len(chunk)
                progressor.update(cur_pos)

            d("DONE %s", local_path)
            f.close()

            progressor.done()


        while sendfiles:
            v("Putting another file info")
            next_file = sendfiles.pop()

            # Check what is this
            # 1. Non existing: skip
            # 2. A file: send it directly (parent dirs won't be replicated)
            # 3. A dir: send it recursively

            next_file_local = next_file.get("local")
            next_file_remote = next_file.get("remote")

            if os.path.isfile(next_file_local):
                # Send it directly
                d("-> is a FILE")
                send_file(next_file_local, next_file_remote)

            elif os.path.isdir(next_file_local):
                # Send it recursively

                d("-> is a DIR")

                # Directory found
                dir_files = sorted(os.listdir(next_file_local), reverse=True)

                if dir_files:

                    v("Found a filled directory: adding all inner files to remaining_files")
                    for f in dir_files:
                        f_path_local = os.path.join(next_file_local, f)
                        f_path_remote = os.path.join(next_file_remote, f)
                        # Push to the begin instead of the end
                        # In this way we perform a breadth-first search
                        # instead of a depth-first search, which makes more sense
                        # because we will push the files that belongs to the same
                        # directory at the same time
                        sendfile = {
                            "local": f_path_local,
                            "remote": f_path_remote
                        }
                        d("Adding sendfile %s", json_to_pretty_str(sendfile))

                        sendfiles.append(sendfile)
                else:
                    v("Found an empty directory")
                    d("Pushing an info for the empty directory")

                    send_file(next_file_local, next_file_remote)
            else:
                eprint("Failed to send '{}'".format(next_file_local))
                w("Unknown file type, doing nothing")

    def _do_get(self,
                connection: Connection,
                files: List[str],
                args: Args):
        if not connection.is_connected():
            e("Connection must be opened for do GET")
            return

        get_response = connection.get(files)

        if not is_data_response(get_response):
            print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
            return

        if is_error_response(get_response):
            Client._handle_connection_error_response(connection, get_response)
            return

        transaction_id = get_response["data"].get("transaction")
        port = get_response["data"].get("port")

        if not transaction_id or not port:
            print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
            return

        v("Successfully GETed")

        transfer_socket = SocketTcpOut(connection.server_info.get("ip"), port)

        overwrite_all: Optional[bool] = None

        if GetArguments.YES_TO_ALL in args:
            overwrite_all = True
        if GetArguments.NO_TO_ALL in args:
            overwrite_all = False

        v("Overwrite all mode: %s", bool_to_str(overwrite_all))

        while True:
            v("Fetching another file info")
            get_next_resp = connection.get_next_info(transaction_id)

            d("get_next_info()\n%s", get_next_resp)

            if not is_success_response(get_next_resp):
                print_error(ClientErrors.COMMAND_EXECUTION_FAILED)
                return

            next_file: FileInfo = get_next_resp.get("data")

            if not next_file:
                v("Nothing more to GET")
                break

            fname = next_file.get("name")
            fsize = next_file.get("size")
            ftype = next_file.get("ftype")

            d("NEXT: %s of type %s", fname, ftype)

            progressor = FileProgressor(
                fsize,
                description="GET " + fname,
                color_progress=PROGRESS_COLOR,
                color_done=DONE_COLOR
            )

            # Case: DIR
            if ftype == FTYPE_DIR:
                v("Creating dirs %s", fname)
                os.makedirs(fname, exist_ok=True)
                progressor.done()
                continue

            if ftype != FTYPE_FILE:
                w("Cannot handle this ftype")
                continue

            # Case: FILE
            parent_dirs, _ = os.path.split(fname)
            if parent_dirs:
                v("Creating parent dirs %s", parent_dirs)
                os.makedirs(parent_dirs, exist_ok=True)

            # Check wheter it already exists
            if os.path.isfile(fname):
                w("File already exists, asking whether overwrite it (if needed)")

                # Ask whether overwrite just once or forever
                current_overwrite_decision = overwrite_all

                # Ask until we get a valid answer
                while current_overwrite_decision is None:

                    overwrite_answer = input(
                        "{} already exists, overwrite it? [Y : yes / yy : yes to all / n : no / nn : no to all] "
                            .format(fname)
                    ).lower()

                    if not overwrite_answer or overwrite_answer == "y":
                        current_overwrite_decision = True
                    elif overwrite_answer == "n":
                        current_overwrite_decision = False
                    elif overwrite_answer == "yy":
                        current_overwrite_decision = overwrite_all = True
                    elif overwrite_answer == "nn":
                        current_overwrite_decision = overwrite_all = False
                    else:
                        w("Invalid answer, asking again")

                if current_overwrite_decision is False:
                    d("Skipping " + fname)
                    continue
                else:
                    d("Will overwrite file")

            v("Opening file '{}' locally".format(fname))
            file = open(fname, "wb")

            # Really get it

            BUFFER_SIZE = 4096

            read = 0

            while read < fsize:
                recv_size = min(BUFFER_SIZE, fsize - read)
                chunk = transfer_socket.recv(recv_size)

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
                d("%d/%d (%.2f%%)", read, fsize, read / fsize * 100)
                progressor.update(read)

            progressor.done()
            d("DONE %s", fname)
            file.close()

            if os.path.getsize(fname) == fsize:
                d("File OK (length match)")
            else:
                e("File length mismatch. %d != %d",
                  os.path.getsize(fname), fsize)

        v("GET transaction %s finished, closing socket", transaction_id)
        transfer_socket.close()

    def get(self, args: Args):
        # 'get' command is multipurpose
        # 1. Inside a connection: get a list of files (or directories)
        # 2. Outside a connection:
        #   2.1 get a file sharing (ftype = 'file')
        #   2.2 get all the content of directory sharing (ftype = 'dir')

        if self.is_connected():
            d("GET => get_files")
            self.get_files(args)
        else:
            d("GET => get_sharing")
            self.get_sharing(args)

    def put(self, args: Args):
        if self.is_connected():
            d("PUT => put_files")
            self.put_files(args)
        else:
            d("PUT => put_sharing")
            self.put_sharing(args)

    def _discover_server(self, location: str) -> Optional[ServerInfo]:

        if not location:
            e("Server location must be specified")
            return None

        server_info: Optional[ServerInfo] = None

        def response_handler(client_endpoint: Endpoint,
                             a_server_info: ServerInfo) -> bool:
            nonlocal server_info
            d("Handling DISCOVER response from %s\n%s",
              str(client_endpoint), str(a_server_info))

            # Check if 'location' matches (if specified)
            if location == a_server_info.get("name") or \
                location == a_server_info.get("ip") or \
                location == "{}:{}".format(a_server_info.get("ip"),
                                           a_server_info.get("port")):
                server_info = a_server_info
                return False    # Stop DISCOVER

            return True  # Continue DISCOVER

        Discoverer(self._server_discover_port, response_handler).discover()
        return server_info


    def _discover_sharing(self,
                          name: str = None,
                          location: str = None,
                          ftype: FileType = None,
                          timeout: int = Discoverer.DEFAULT_TIMEOUT) -> Optional[ServerInfo]:
        """
        Performs a discovery for find whose server the sharing with the given
        'name' belongs to.

        """

        server_info: Optional[ServerInfo] = None

        def response_handler(client_endpoint: Endpoint,
                             a_server_info: ServerInfo) -> bool:
            nonlocal server_info
            d("Handling DISCOVER response from %s\n%s",
              str(client_endpoint), str(a_server_info))

            # Check if 'location' matches (if specified)
            if location and \
                    location != a_server_info.get("name") and \
                    location != a_server_info.get("ip") and \
                    location != "{}:{}".format(a_server_info.get("ip"),
                                               a_server_info.get("port")):
                d("Discarding server info which does not match the location filter '%s'", location)
                return True  # Continue DISCOVER

            for sharing_info in a_server_info.get("sharings"):

                # Check if 'name' matches (if specified)
                if name and sharing_info.get("name") != name:
                    d("Ignoring sharing which does not match the name filter '%s'", name)
                    continue

                if ftype and sharing_info.get("ftype") != ftype:
                    d("Ignoring sharing which does not match the ftype filter '%s'", ftype)
                    continue

                # FOUND
                d("Sharing [%s] found at %s:%d",
                  sharing_info.get("name"),
                  a_server_info.get("ip"),
                  a_server_info.get("port"))

                server_info = a_server_info
                return False    # Stop DISCOVER

            return True             # Continue DISCOVER

        Discoverer(self._server_discover_port, response_handler).discover(timeout)
        return server_info


    @staticmethod
    def _print_sharings(sharings: List[SharingInfo]):
        print(Client._sharings_string(sharings))

    @staticmethod
    def _sharings_string(sharings: List[SharingInfo]) -> str:
        s = ""

        d_sharings = [sh.get("name") for sh in sharings if sh.get("ftype") == FTYPE_DIR]
        f_sharings = [sh.get("name") for sh in sharings if sh.get("ftype") == FTYPE_FILE]

        if d_sharings:
            s += "  DIRECTORIES\n"
            for dsh in d_sharings:
                s += "  - " + dsh + "\n"

        if f_sharings:
            s += "  FILES\n"
            for fsh in f_sharings:
                s += "  - " + fsh + "\n"

        return s.rstrip("\n")

    @staticmethod
    def _print_tree_files_info(root: TreeNodeDict,
                               max_depth: int = None,
                               show_size: bool = False):
        for prefix, node, depth in TreeRenderPostOrder(root, depth=max_depth):
            ftype = node.get("ftype")
            size = node.get("size")

            print("{}{}{}".format(
                prefix,
                "[{}]  ".format(size_str(size).rjust(4)) if show_size else "",
                fg(node.get("name"), color=DIR_COLOR if ftype == FTYPE_DIR else FILE_COLOR),
            ))


    @staticmethod
    def _print_list_files_info(infos: List[FileInfo], show_size: bool = False):
        for info in infos:
            d("f_info: %s", info)

            fname = info.get("name")
            size = info.get("size")

            if info.get("ftype") == FTYPE_DIR:
                ftype_short = "D"
                fname = fg(fname, DIR_COLOR)
            else:
                ftype_short = "F"
                fname = fg(fname, FILE_COLOR)

            print("{}  {}{}".format(
                ftype_short,
                "{}  ".format(size_str(size).rjust(4)) if show_size else "",
                fname
            ))

    def _handle_error_response(self, resp: Response):
        Client._handle_connection_error_response(self.connection, resp)

    @staticmethod
    def _handle_connection_error_response(connection: Connection, resp: Response):
        if is_error_response(ServerErrors.NOT_CONNECTED):
            v("Received a NOT_CONNECTED response: destroying connection")
            connection.close()
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

                if not command_line:
                    w("Empty command line")
                    continue

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
            except PyroError:
                v("Pyro error occurred")
                print_error(ClientErrors.CONNECTION_ERROR)
                # Close client connection anyway
                try:
                    if self.client.is_connected():
                        d("Trying to close connection gracefully")
                        self.client.close()
                except PyroError:
                    d("Cannot communicate with remote: invalidating connection")
                    self.client.connection = None
            except KeyboardInterrupt:
                v("CTRL+C detected")
                print()
            except EOFError:
                v("CTRL+D detected: exiting")
                if self.client.is_connected():
                    self.client.close()
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

    init_colors(ClientArguments.NO_COLOR not in args)

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
    cli_command_line = args.get_params()

    start_shell = True if not cli_command_line else False

    if not start_shell:
        command = cli_command_line.pop(0)

        if command not in CLI_COMMANDS:
            abort("Unknown command: {}".format(command))

        start_shell = (command == Commands.OPEN)

        # Execute directly
        # Take out the first token as "command" and leave
        # everything else as it is
        d("Executing command directly from command line: %s (%s)", command, args)
        client.execute_command(command, args)

    # Start the shell
    # 1. If a command was not specified
    # 2. We are connected (due to open from a direct command)
    if start_shell:
        # Start the shell
        v("Executing shell")
        shell = Shell(client)
        shell.input_loop()


def main_wrapper(dump_pyro_exceptions=False):
    # if not dump_pyro_exceptions:
    main()
    # else:
    #     try:
    #         main()
    #     except Exception as ex:
    #         traceback = Pyro4.util.getPyroTraceback()
    #         if traceback:
    #             # e("--- PYRO4 TRACEBACK ---\n%s", red("".join(traceback)))


if __name__ == "__main__":
    main_wrapper(dump_pyro_exceptions=True)
