import os
import ssl
import subprocess
import sys
import socket
import time

import Pyro4

from typing import Dict, Optional, List, Any, Callable, TypeVar

from easyshare import logging
from easyshare.logging import get_logger
from easyshare.passwd.auth import AuthFactory
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.filetype import FTYPE_FILE, FTYPE_DIR
from easyshare.protocol.response import create_success_response, create_error_response, Response
from easyshare.server.sharing import Sharing
from easyshare.server.transactions import GetTransactionHandler, PutTransactionHandler
from easyshare.shared.args import Args
from easyshare.shared.common import APP_VERSION, APP_NAME_SERVER_SHORT, \
    APP_NAME_SERVER, DEFAULT_DISCOVER_PORT, SERVER_NAME_ALPHABET, ENV_EASYSHARE_VERBOSITY
from easyshare.config.parser import parse_config
from easyshare.server.client import ClientContext
from easyshare.server.discover import DiscoverDeamon
from easyshare.shared.endpoint import Endpoint
from easyshare.protocol.iserver import IServer
from easyshare.protocol.errors import ServerErrors
from easyshare.ssl import set_ssl_context, get_ssl_context
from easyshare.tracing import enable_tracing, trace_in, trace_out
from easyshare.socket.udp import SocketUdpOut
from easyshare.utils.app import terminate, abort
from easyshare.utils.colors import enable_colors
from easyshare.utils.json import json_to_bytes, json_to_pretty_str
from easyshare.utils.net import get_primary_ip, is_valid_port, create_server_ssl_context
from easyshare.utils.os import ls, relpath, is_relpath, rm, tree, cp, mv
from easyshare.utils.str import satisfy, unprefix
from easyshare.utils.trace import args_to_str
from easyshare.utils.types import bytes_to_int, to_int, to_bool, is_valid_list, bytes_to_str

# ==================================================================

log = get_logger()

APP_INFO = APP_NAME_SERVER + " (" + APP_NAME_SERVER_SHORT + ") v. " + APP_VERSION


# === HELPS ===

HELP_APP = """easyshare deamon (esd)
...
"""


# === ARGUMENTS ===


class ServerArguments:
    TRACE = ["-t", "--trace"]
    VERBOSE = ["-v", "--verbose"]
    SHARE = ["-s", "--share"]
    CONFIG = ["-c", "--config"]
    PORT = ["-p", "--port"]
    NAME = ["-n", "--name"]
    READ_ONLY = ["-r", "--read-only"]
    HELP = ["-h", "--help"]
    VERSION = ["-V", "--version"]
    NO_COLOR = ["--no-color"]


class ServerConfigKeys:
    PORT = "port"
    NAME = "name"
    PASSWORD = "password"
    SHARING_PATH = "path"
    SHARING_READ_ONLY = "readonly"
    SSL = "ssl"
    SSL_CERT = "ssl_cert"
    SSL_PRIVKEY = "ssl_privkey"


# === ERRORS ===


class ErrorsStrings:
    INVALID_PORT = "Invalid port"
    INVALID_SERVER_NAME = "Invalid server name"


# ==================================================================

# === TRACING ===

API = TypeVar('API', bound=Callable[..., Any])


def trace_api(api: API) -> API:

    def wrapped_api(server: 'Server', *vargs, **kwargs) -> Optional[Response]:
        requester = server._current_request_endpoint()



        trace_in("{} ({})".format(api.__name__, args_to_str(vargs, kwargs)),
                 ip=requester[0],
                 port=requester[1])

        resp = api(server, *vargs, **kwargs)

        if resp:
            trace_out("{}\n{}".format(api.__name__, json_to_pretty_str(resp)),
                      ip=requester[0],
                      port=requester[1])
        # else: should be a one-way call without response
        return resp

    return wrapped_api


# def require_connection(api: API) -> API:
#     def wrapped_api(server: 'Server', *vargs, **kwargs) -> Optional[Response]:
#         client = server._current_request_client()
#         if not client:
#             log.e("Connection is required for '%s'", api.__name__)
#             return create_error_response(ServerErrors.NOT_CONNECTED)
#         return api(*vargs, **kwargs)
#     setattr(wrapped_api, "__name__", api.__name__)
#     return wrapped_api



class Server(IServer):

    def __init__(self, discover_port, name: str, ssl_context: ssl.SSLContext = None):
        self.ip = get_primary_ip()
        self.name = name

        # sharing_name -> sharing
        self.sharings: Dict[str, Sharing] = {}
        self.clients: Dict[Endpoint, ClientContext] = {}
        self.puts: Dict[str, PutTransactionHandler] = {}
        self.gets: Dict[str, GetTransactionHandler] = {}

        self.discover_deamon = DiscoverDeamon(discover_port, self.handle_discover_request)

        log.i("Server's name: %s", name)
        log.i("Server's discover port: %d", discover_port)
        log.i("Primary interface IP: %s", self.ip)

        set_ssl_context(ssl_context)
        self.ssl_context = get_ssl_context()

        self.pyro_deamon = Pyro4.Daemon(host=self.ip)
        self.uri = self.pyro_deamon.register(self).asString()
        log.i("Server registered at URI: %s", self.uri)

    def add_sharing(self, sharing: Sharing):
        log.i("+ SHARING %s", sharing)
        self.sharings[sharing.name] = sharing

    def handle_discover_request(self, client_endpoint: Endpoint, data: bytes):
        log.i("<< DISCOVER %s", client_endpoint)
        log.i("Handling discover %s", str(data))

        server_endpoint = self._endpoint()

        response_data = {
            "uri": self.uri,
            "name": self.name,
            "ip": server_endpoint[0],
            "port": server_endpoint[1],
            "sharings": [sh.info() for sh in self.sharings.values()],
            "ssl": True if self.ssl_context else False
        }

        response = create_success_response(response_data)

        client_discover_response_port = bytes_to_int(data)

        if not is_valid_port(client_discover_response_port):
            log.w("Invalid DISCOVER message received, ignoring it")
            return

        log.i("Client response port is %d", client_discover_response_port)

        # Respond to the port the client says in the paylod
        # (not necessary the one from which the request come)
        sock = SocketUdpOut()

        log.d("Sending DISCOVER response back to %s:%d\n%s",
          client_endpoint[0], client_discover_response_port,
          json_to_pretty_str(response))

        trace_out(
            "DISCOVER {}".format(json_to_pretty_str(response)),
            ip=client_endpoint[0],
            port=client_discover_response_port
        )

        sock.send(json_to_bytes(response), client_endpoint[0], client_discover_response_port)

    def start(self):
        log.i("Starting DISCOVER deamon")
        self.discover_deamon.start()

        log.i("Starting PYRO request loop")
        self.pyro_deamon.requestLoop()


    @Pyro4.expose
    @trace_api
    def open(self, sharing_name: str, password: str = None) -> Response:
        if not sharing_name:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        sharing = self.sharings.get(sharing_name)

        if not sharing:
            return create_error_response(ServerErrors.SHARING_NOT_FOUND)

        if not sharing.auth:
            return create_error_response(ServerErrors.INTERNAL_SERVER_ERROR)

        # Authentication
        log.i("Authentication check - type: %s", sharing.auth.algo_name())
        # Just ask the auth whether it matches or not
        # (The password can either be none/plain/hash, the auth handles them all)
        if not sharing.auth.authenticate(password):
            log.e("Auth FAILED")
            return create_error_response(ServerErrors.AUTHENTICATION_FAILED)

        log.i("Auth OK")

        client_endpoint = self._current_request_endpoint()
        log.i("<< OPEN %s %s", sharing_name, str(client_endpoint))

        client = self._current_request_client()
        if not client:
            # New client
            client = ClientContext()
            client.endpoint = client_endpoint
            client.sharing_name = sharing_name
            self.clients[client_endpoint] = client
            log.i("New client connected (%s) to sharing %s",
              str(client), client.sharing_name)
        else:
            client.sharing_name = sharing_name
            client.rpwd = ""
            log.i("Already connected client (%s) changed sharing to %s",
              str(client), client.sharing_name)

        return create_success_response()

    @Pyro4.expose
    @Pyro4.oneway
    @trace_api
    def close(self):
        client_endpoint = self._current_request_endpoint()
        log.i("<< CLOSE %s", str(client_endpoint))
        client = self._current_request_client()

        if not client:
            log.w("Received a close request from an unknown client")
            return

        log.i("Deallocating client resources...")

        # Remove any pending transaction
        for get_trans_id in client.gets:
            # self._end_get_transaction(get_trans_id, client, abort=True)
            if get_trans_id in self.gets:
                log.i("Removing GET transaction = %s", get_trans_id)
                self.gets.pop(get_trans_id).abort()

        # Remove from clients
        log.i("Removing %s from clients", client)

        del self.clients[client_endpoint]
        log.i("Client connection closed gracefully")

        log.i("# clients = %d", len(self.clients))
        log.i("# gets = %d", len(self.gets))

    @Pyro4.expose
    @trace_api
    def rpwd(self) -> Response:
        # NOT NEEDED
        log.i("<< RPWD %s", str(self._current_request_endpoint()))

        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        return create_success_response(client.rpwd)

    @Pyro4.expose
    @trace_api
    def rcd(self, path: str) -> Response:
        if not path:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        log.i("<< RCD %s (%s)", path, str(client))

        new_path = self._path_for_client(client, path)

        log.i("Sharing path: %s", new_path)

        if not self._is_path_allowed_for_client(client, new_path):
            log.e("Path is invalid (out of sharing domain)")
            return create_error_response(ServerErrors.INVALID_PATH)

        if not os.path.isdir(new_path):
            log.e("Path does not exists")
            return create_error_response(ServerErrors.INVALID_PATH)

        log.i("Path exists, success")

        client.rpwd = self._trailing_path_for_client_from_root(client, new_path)
        log.i("New rpwd: %s", client.rpwd)

        return create_success_response(client.rpwd)

    @Pyro4.expose
    @trace_api
    def rls(self, *, path: str = None, sort_by: List[str] = None,
            reverse: bool = False, hidden: bool = False, ) -> Response:
        client = self._current_request_client()
        if not client:
            log.w("Client not connected: %s", self._current_request_endpoint())
            return create_error_response(ServerErrors.NOT_CONNECTED)

        path = path or "."
        sort_by = sort_by or ["name"]

        log.i("<< RLS %s %s%s (%s)",
              path, sort_by, " | reverse " if reverse else "", str(client))

        try:
            ls_path = self._path_for_client(client, path)
            log.i("Going to ls on %s", ls_path)

            # Check path legality (it should be valid, if he rcd into it...)
            if not self._is_path_allowed_for_client(client, ls_path):
                return create_error_response(ServerErrors.INVALID_PATH)

            ls_result = ls(ls_path, sort_by=sort_by, reverse=reverse)
            if ls_result is None:
                return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

            log.i("RLS response %s", str(ls_result))

            return create_success_response(ls_result)
        except Exception as ex:
            log.e("RLS error: %s", str(ex))
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)


    @Pyro4.expose
    @trace_api
    def rtree(self, *,  path: str = None, sort_by: List[str] = None,
              reverse: bool = False, hidden: bool = False,
              max_depth: int = None,) -> Response:
        client = self._current_request_client()
        if not client:
            log.w("Client not connected: %s", self._current_request_endpoint())
            return create_error_response(ServerErrors.NOT_CONNECTED)

        path = path or "."
        sort_by = sort_by or ["name"]

        log.i("<< RTREE %s %s%s (%s)",
              path, sort_by, " | reverse " if reverse else "", str(client))

        try:
            tree_path = self._path_for_client(client, path)
            log.i("Going to tree on %s", tree_path)

            # Check path legality (it should be valid, if he rcd into it...)
            if not self._is_path_allowed_for_client(client, tree_path):
                return create_error_response(ServerErrors.INVALID_PATH)

            tree_root = tree(tree_path, sort_by=sort_by, reverse=reverse, max_depth=max_depth)
            if tree_root is None:
                return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

            log.i("RTREE response %s", json_to_pretty_str(tree_root))

            return create_success_response(tree_root)
        except Exception as ex:
            log.e("RTREE error: %s", str(ex))
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)


    @Pyro4.expose
    @trace_api
    def rmkdir(self, directory: str) -> Response:
        client = self._current_request_client()

        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        sharing = self._current_request_sharing()

        if sharing.read_only:
            return create_error_response(ServerErrors.NOT_WRITABLE)

        log.i("<< RMKDIR %s (%s)", directory, str(client))

        try:
            # full_path = os.path.join(self._current_client_path(client), directory)
            # TODO: test
            full_path = self._path_for_client(client, directory)

            log.i("Going to mkdir on %s", full_path)

            if not self._is_path_allowed_for_client(client, full_path):
                return create_error_response(ServerErrors.INVALID_PATH)

            os.mkdir(full_path)
            return create_success_response()
        except Exception as ex:
            log.e("RMKDIR error: %s", str(ex))
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

    @Pyro4.expose
    @trace_api
    def rrm(self, paths: List[str]) -> Response:
        client = self._current_request_client()

        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        sharing = self._current_client_sharing(client)

        log.i("<< RRM %s (%s)", paths, str(client))

        try:
            errors = []

            def handle_rm_error(err):
                log.i("RM error: adding error to notify to remote:\n%s", err)
                errors.append(str(err))

            for path in paths:

                rm_path = self._path_for_client(client, path)

                log.i("RM on path: %s", rm_path)

                if not self._is_path_allowed_for_client(client, rm_path):
                    log.e("Path is invalid (out of sharing domain)")
                    return create_error_response(ServerErrors.INVALID_PATH)

                # Do not allow to remove the entire sharing
                try:
                    if os.path.samefile(sharing.path, rm_path):
                        log.e("Cannot delete the sharing's root directory; aborting")
                        return create_error_response(ServerErrors.INVALID_PATH)
                    # Ok..
                except Exception:
                    pass
                    # Maybe the file does not exists, don't worry and pass
                    # it to rm that will handle it properly with error_callback

                rm(rm_path, error_callback=handle_rm_error)

            # Eventually put errors in the response

            response_data = None

            if errors:
                log.w("Reporting %d errors to the client", len(errors))
                response_data = {"errors": errors}

            return create_success_response(response_data)

        except Exception as ex:
            log.e("RRM error: %s", str(ex))
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

    @Pyro4.expose
    @trace_api
    def rmv(self, sources: List[str], destination: str) -> Response:
        client = self._current_request_client()

        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        if not sources or not destination:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        dest_full_path = self._path_for_client(client, destination)

        if not self._is_path_allowed_for_client(client, dest_full_path):
            log.e("Path is invalid (out of sharing domain)")
            return create_error_response(ServerErrors.INVALID_PATH)

        # C1/C2 check: with 3+ arguments
        if len(sources) >= 2:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not os.path.isdir(dest_full_path):
                log.e("'%s' must be an existing directory", dest_full_path)
                return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

        log.i("<< RMV %s -> %s (%s)", sources, destination, str(client))

        try:
            errors = []

            for src in sources:

                src_full_path = self._path_for_client(client, src)

                if not self._is_path_allowed_for_client(client, src_full_path):
                    if len(sources) == 1:
                        return create_error_response(ServerErrors.INVALID_PATH)

                    errors.append("Invalid path")
                    continue

                try:
                    log.i("MV %s -> %s", src_full_path, dest_full_path)

                    mv(src_full_path, dest_full_path)
                except Exception as ex:
                    errors.append(str(ex))

                if errors:
                    log.e("%d errors occurred", len(errors))

            response_data = None

            if errors:
                log.w("Reporting %d errors to the client", len(errors))
                response_data = {"errors": errors}

            return create_success_response(response_data)

        except Exception as ex:
            log.e("RMV error: %s", str(ex))
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

    @Pyro4.expose
    @trace_api
    def rcp(self, sources: List[str], destination: str) -> Response:
        client = self._current_request_client()

        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        if not sources or not destination:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)


        dest_full_path = self._path_for_client(client, destination)

        if not self._is_path_allowed_for_client(client, dest_full_path):
            log.e("Path is invalid (out of sharing domain)")
            return create_error_response(ServerErrors.INVALID_PATH)

        # C1/C2 check: with 3+ arguments
        if len(sources) >= 2:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not os.path.isdir(dest_full_path):
                log.e("'%s' must be an existing directory", dest_full_path)
                return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

        log.i("<< RCP %s -> %s (%s)", sources, destination, str(client))

        try:
            errors = []

            for src in sources:

                src_full_path = self._path_for_client(client, src)

                if not self._is_path_allowed_for_client(client, src_full_path):
                    if len(sources) == 1:
                        return create_error_response(ServerErrors.INVALID_PATH)

                    errors.append("Invalid path")
                    continue

                try:
                    log.i("CP %s -> %s", src_full_path, dest_full_path)

                    cp(src_full_path, dest_full_path)
                except Exception as ex:
                    errors.append(str(ex))

                if errors:
                    log.e("%d errors occurred", len(errors))

            response_data = None

            if errors:
                log.w("Reporting %d errors to the client", len(errors))
                response_data = {"errors": errors}

            return create_success_response(response_data)

        except Exception as ex:
            log.e("RCP error: %s", str(ex))
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

    @Pyro4.expose
    @trace_api
    def ping(self):
        for x in range(0, 10):
            log.i("[%d] Sleeping", x)
            time.sleep(1)
        log.d("Creating 'pong' response")
        return create_success_response("pong")


    @Pyro4.expose
    @trace_api
    def put(self) -> Response:
        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        log.i("<< PUT [files] (%s)",  str(client))

        # if len(files) == 0:
        #     files = ["."]
        #
        # # Compute real path for each name
        # normalized_files = []
        # for f in files:
        #     normalized_files.append(self._path_for_client(client, f))

        # log.i("Normalized files:\n%s", normalized_files)

        transaction_handler = self._add_put_transaction(
            client=client,
            sharing_name=client.sharing_name
        )

        return create_success_response({
            "transaction": transaction_handler.transaction_id(),
            "port": transaction_handler.port()
        })


    @Pyro4.expose
    @trace_api
    def get(self, files: List[str]) -> Response:
        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        log.i("<< GET [files] %s (%s)", str(files), str(client))

        if len(files) == 0:
            files = ["."]

        # Compute real path for each name
        normalized_files = []
        for f in files:
            normalized_files.append(self._path_for_client(client, f))

        normalized_files = sorted(normalized_files, reverse=True)
        log.i("Normalized files:\n%s", normalized_files)

        transaction_handler = self._add_get_transaction(
            normalized_files,
            client=client,
            sharing_name=client.sharing_name)

        return create_success_response({
            "transaction": transaction_handler.transaction_id(),
            "port": transaction_handler.port()
        })


    @Pyro4.expose
    @trace_api
    def put_next_info(self, transaction_id, finfo: FileInfo) -> Response:
        client = self._current_request_client()

        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        log.i("<< PUT_NEXT_INFO %s %s", transaction_id, str(client))

        if transaction_id not in self.puts:
            return create_error_response(ServerErrors.INVALID_TRANSACTION)

        transaction_handler = self.puts[transaction_id]

        sharing = self.sharings.get(transaction_handler.sharing_name())
        if not sharing:
            log.e("Sharing '%s' not found", transaction_handler.sharing_name())
            return create_error_response(ServerErrors.SHARING_NOT_FOUND)

        if not finfo:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        if sharing.ftype == FTYPE_FILE:
            # Cannot put within a file
            log.e("Cannot put within a file sharing")
            return create_error_response(ServerErrors.NOT_ALLOWED)

        # Check whether is a dir or a file
        fname = finfo.get("name")
        ftype = finfo.get("ftype")
        fsize = finfo.get("size")

        full_path = self._path_for_client(client, fname)

        if ftype == FTYPE_DIR:
            log.i("Creating dirs %s", full_path)
            os.makedirs(full_path, exist_ok=True)
            return create_success_response()

        if ftype == FTYPE_FILE:
            parent_dirs, _ = os.path.split(full_path)
            if parent_dirs:
                log.i("Creating parent dirs %s", parent_dirs)
                os.makedirs(parent_dirs, exist_ok=True)
        else:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        # Check wheter it already exists
        if os.path.isfile(full_path):
            log.w("File already exists, (should) asking whether overwrite it (if needed)")
            return create_success_response("ask_overwrite")

        transaction_handler.push_file(full_path, fsize)

        return create_success_response()


    @Pyro4.expose
    @trace_api
    def get_next_info(self, transaction_id) -> Response:
        client = self._current_request_client()

        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        log.i("<< GET_NEXT_INFO %s %s", transaction_id, str(client))

        if transaction_id not in self.gets:
            return create_error_response(ServerErrors.INVALID_TRANSACTION)

        transaction_handler = self.gets[transaction_id]

        sharing = self.sharings.get(transaction_handler.sharing_name())
        if not sharing:
            log.e("Sharing '%s' not found", transaction_handler.sharing_name())
            return create_error_response(ServerErrors.SHARING_NOT_FOUND)

        remaining_files = transaction_handler.next_files()

        while len(remaining_files) > 0:

            # Get next file (or dir)
            next_file_path = remaining_files.pop()

            log.i("Next file path: %s", next_file_path)

            # Check domain validity
            # (if client is null the domain is valid for sure since it should
            # be the sharing path we added ourself)
            if client and not self._is_path_allowed_for_client(client, next_file_path):
                log.w("Invalid file found: skipping %s", next_file_path)
                continue

            if sharing.path == next_file_path:
                # Getting (file) sharing
                sharing_path_head, _ = os.path.split(sharing.path)
                log.i("sharing_path_head: %s", sharing_path_head)
                trail = self._trailing_path(sharing_path_head, next_file_path)
            else:
                trail = self._trailing_path_for_client_from_rpwd(client, next_file_path)

            log.i("Trail: %s", trail)

            # Case: FILE
            if os.path.isfile(next_file_path):

                # We are handling a valid file, report the metadata to the client
                log.i("NEXT FILE: %s", next_file_path)

                # Push the file the transaction handler (make it available
                # for the download)
                transaction_handler.push_file(next_file_path)

                return create_success_response({
                    "name": trail,
                    "ftype": FTYPE_FILE,
                    "size": os.path.getsize(next_file_path)
                })

            # Case: DIR
            elif os.path.isdir(next_file_path):
                # Directory found
                dir_files = sorted(os.listdir(next_file_path), reverse=True)

                if dir_files:

                    log.i("Found a filled directory: adding all inner files to remaining_files")
                    for f in dir_files:
                        f_path = os.path.join(next_file_path, f)
                        log.i("Adding %s", f_path)
                        remaining_files.append(f_path)
                else:
                    log.i("Found an empty directory")
                    log.d("Returning an info for the empty directory")

                    return create_success_response({
                        "name": trail,
                        "ftype": FTYPE_DIR,
                    })
            # Case: UNKNOWN (non-existing/link/special files/...)
            else:
                log.w("Not file nor dir? skipping %s", next_file_path)

        log.i("No remaining files")
        transaction_handler.done()

        # Notify the client about it
        return create_success_response()

    def rexec(self, cmd: str) -> Response:
        log.i(">> REXEC %s", cmd)

        try:
            proc: subprocess.Popen = \
                subprocess.Popen(["/bin/sh", "-c", cmd],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)

            ret_str = bytes_to_str(proc.stdout.read())
            return create_success_response(ret_str)

        except Exception:
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

    def _add_put_transaction(self,
                             sharing_name: str,
                             client: Optional[ClientContext] = None) -> PutTransactionHandler:

        log.d("_add_put_transaction files")
        # Create a transaction handler
        transaction_handler = PutTransactionHandler(
            sharing_name,
            on_end=self._on_get_transaction_end,
            owner=client)

        transaction_id = transaction_handler.transaction_id()
        log.i("Transaction ID: %s", transaction_id)

        transaction_handler.start()

        if client:
            client.puts.append(transaction_id)

        self.puts[transaction_id] = transaction_handler

        return transaction_handler

    def _add_get_transaction(self,
                             files: List[str],
                             sharing_name: str,
                             client: Optional[ClientContext] = None) -> GetTransactionHandler:

        log.i("_add_get_transaction files: %s", files)
        # Create a transaction handler
        transaction_handler = GetTransactionHandler(
            files,
            sharing_name,
            on_end=self._on_get_transaction_end,
            owner=client)

        transaction_id = transaction_handler.transaction_id()
        log.i("Transaction ID: %s", transaction_id)

        transaction_handler.start()

        if client:
            client.gets.append(transaction_id)

        self.gets[transaction_id] = transaction_handler

        return transaction_handler

    def _on_get_transaction_end(self, finished_transaction: GetTransactionHandler):
        trans_id = finished_transaction.transaction_id()

        log.i("Finished transaction %s", trans_id)

        if trans_id in self.gets:
            log.d("Removing transaction from gets")
            del self.gets[trans_id]

        owner = finished_transaction.owner()

        if owner:
            log.i("Removing transaction from '%s' gets", owner)
            owner.gets.remove(trans_id)

    # def _end_get_transaction(self, transaction_id: str,
    #                          client: Optional[ClientContext], *,
    #                          abort: bool = False):
    #     if transaction_id not in self.gets:
    #         log.w("Transaction with id %s not found", transaction_id)
    #         return
    #
    #     transaction_handler = self.gets.pop(transaction_id)
    #
    #     if abort:
    #         log.d("_end_get_transaction: aborting transaction")
    #         transaction_handler.abort()
    #
    #     if client:
    #         client.gets.remove(transaction_id)


    def _current_request_endpoint(self) -> Optional[Endpoint]:
        """
        Returns the endpoint (ip, port) of the client that is making
        the request right now (provided by the underlying Pyro deamon)
        :return: the endpoint of the current client
        """
        return Pyro4.current_context.client_sock_addr

    def _current_request_client(self) -> Optional[ClientContext]:
        """
        Returns the client that belongs to the current request endpoint (ip, port)
        if exists among the known clients; otherwise returns None.
        :return: the client of the current request
        """
        return self.clients.get(self._current_request_endpoint())

    def _current_request_sharing(self) -> Optional[Sharing]:
        """
        Returns the client that belongs to the current request endpoint (ip, port)
        if exists among the known clients; otherwise returns None.
        :return: the client of the current request
        """
        return self._current_client_sharing(self._current_request_client())

    def _current_client_sharing(self, client: ClientContext) -> Optional[Sharing]:
        """
        Returns the current sharing the given client is placed on.
        Returns None if the client is invalid or its sharing doesn't exists
        :param client: the client
        :return: the sharing on which the client is placed
        """
        if not client:
            return None

        return self.sharings.get(client.sharing_name)

    def _current_client_path(self, client: ClientContext) -> Optional[str]:
        """
        Returns the current path the given client is placed on.
        It depends on the client's sharing and on the directory he is placed on
        (which he might have changed with rcd).
        e.g.
            client sharing path =  /home/stefano/Applications
            client rpwd         =                             AnApp
                                => /home/stefano/Applications/AnApp
        :param client: the client
        :return: the path of the client, relatively to the server's filesystem
        """
        if not client:
            return None

        sharing: Sharing = self._current_client_sharing(client)

        if not sharing:
            return None

        return os.path.join(sharing.path, client.rpwd)

    def _path_for_client(self, client: ClientContext, path: str) -> Optional[str]:
        """
        Returns the path of the location composed by the 'path' of the
        sharing the client is currently on and the 'path' itself.
        The method allows:
            * 'path' starting with a leading / (absolute w.r.t the sharing path)
            * 'path' not starting with a leading / (relative w.r.t the rpwd)

        e.g.
            (ABSOLUTE)
            client sharing path =  /home/stefano/Applications
            client rpwd =                                     InsideAFolder
            path                =  /AnApp
                                => /home/stefano/Applications/AnApp

            (RELATIVE)
            client sharing path =  /home/stefano/Applications
            client rpwd =                                     InsideAFolder
            path                =  AnApp
                                => /home/stefano/Applications/InsideAFolder/AnApp

        """
        sharing = self._current_client_sharing(client)

        if not sharing:
            return None

        if is_relpath(path):
            # It refers to a subdirectory starting from the current rpwd
            path = os.path.join(client.rpwd, path)

        # Take the trail part (without leading /)
        trail = relpath(path)

        return os.path.normpath(os.path.join(sharing.path, trail))

    def _trailing_path(self, prefix: str, full: str) -> Optional[str]:
        """
        Returns the trailing part of the path 'full' by stripping the path 'prefix'.
        The path is relative w.r.t the root of the sharing path.
        e.g.
            prefix                = /home/stefano/Applications
            full                  = /home/stefano/Applications/AnApp/afile.mp4
                                =>                           AnApp/afile.mp4
        """

        if not full or not prefix:
            return None

        if not full.startswith(prefix):
            return None

        return relpath(unprefix(full, prefix))

    def _trailing_path_for_sharing(self, sharing: Sharing, path: str) -> Optional[str]:
        """
        Returns the trailing part of the 'path' by stripping the path of the
        sharing from the string's beginning.
        The path is relative w.r.t the root of the sharing path.
        e.g.
            sharing path        = /home/stefano/Applications
            path                = /home/stefano/Applications/AnApp/afile.mp4
                                =>                           AnApp/afile.mp4
        """
        return self._trailing_path(sharing.path, path) if sharing else None

    def _trailing_path_for_client_from_root(self, client: ClientContext, path: str) -> Optional[str]:
        """
        Returns the trailing part of the 'path' by stripping the path of the
        sharing from the string's beginning.
        The path is relative w.r.t the root of the sharing path.
        e.g.
            client sharing path = /home/stefano/Applications
            [client rpwd         =                            AnApp         ]
            [client path        = /home/stefano/Applications/AnApp          ]
            path                = /home/stefano/Applications/AnApp/afile.mp4
                                =>                           AnApp/afile.mp4
        """
        return self._trailing_path_for_sharing(self._current_client_sharing(client), path)

    def _trailing_path_for_client_from_rpwd(self, client: ClientContext, path: str) -> Optional[str]:
        """
        Returns the trailing part of the 'path' by stripping the path of the
        sharing from the string's beginning.
        The path is relative w.r.t the rpwd of the sharing path the client
        is currently on.
        e.g.
            client sharing path = /home/stefano/Applications
            client rpwd         =                            AnApp
            (client path        = /home/stefano/Applications/AnApp          )
            path                = /home/stefano/Applications/AnApp/afile.mp4
                                =>                                 afile.mp4
        """
        return self._trailing_path(self._current_client_path(client), path)

    def _is_path_allowed_for_client(self, client: ClientContext, path: str) -> bool:
        """
        Returns whether the given path is legal for the given client, based
        on the its sharing and rpwd.

        e.g. ALLOWED
            client sharing path = /home/stefano/Applications
            client rpwd         =                            AnApp
            path                = /home/stefano/Applications/AnApp/AFile.mp4

        e.g. NOT ALLOWED
            client sharing path = /home/stefano/Applications
            client rpwd         =                            AnApp
            path                = /home/stefano/Applications/AnotherApp/AFile.mp4

            client sharing path = /home/stefano/Applications
            client rpwd         =                           AnApp
            path                = /tmp/afile.mp4

        :param path: the path to check
        :param client: the client
        :return: whether the path is allowed for the client
        """

        sharing = self._current_client_sharing(client)

        if not sharing:
            log.w("Sharing not found %s", client.sharing_name)
            return False

        normalized_path = os.path.normpath(path)

        try:
            common_path = os.path.commonpath([normalized_path, sharing.path])
            log.d("Common path between '%s' and '%s' = '%s'",
                  normalized_path, sharing.path, common_path)

            return sharing.path == common_path
        except:
            return False

    def _endpoint(self) -> Endpoint:
        """
        Returns the current endpoint (ip, port) the server (Pyro deamon) is bound to.
        :return: the current server endpoint
        """
        return self.pyro_deamon.sock.getsockname()


def main():
    starting_verbosity = os.environ.get(ENV_EASYSHARE_VERBOSITY)
    starting_verbosity = to_int(starting_verbosity,
                                raise_exceptions=False,
                                default=logging.VERBOSITY_NONE)
    log.set_verbosity(starting_verbosity)
    log.d("Starting with verbosity = %d", starting_verbosity)

    if len(sys.argv) <= 1:
        terminate(HELP_APP)

    args = Args(sys.argv[1:])

    enable_colors(ServerArguments.NO_COLOR not in args)

    if ServerArguments.HELP in args:
        terminate(HELP_APP)

    if ServerArguments.VERSION in args:
        terminate(APP_INFO)

    verbosity = 0
    tracing = 0

    # if ServerArguments.VERBOSE in args:
    #     verbosity = to_int(args.get_param(ServerArguments.VERBOSE, default=VERBOSITY_VERBOSE))
    #     if verbosity is None:
    #         abort("Invalid --verbose parameter value")
    #
    # if ServerArguments.TRACE in args:
    #     tracing = to_int(args.get_param(ServerArguments.TRACE, default=1))
    #     if tracing is None:
    #         abort("Invalid --trace parameter value")
    #
    # init_logging(verbosity)
    # enable_tracing(True if tracing else False)
    enable_tracing(True)

    log.i(APP_INFO)

    # Init stuff with default values
    sharings = {}
    port = DEFAULT_DISCOVER_PORT
    name = socket.gethostname()
    password = None
    ssl_enabled = False
    ssl_cert = None
    ssl_privkey = None

    # Eventually parse config file
    config_path = args.get_param(ServerArguments.CONFIG)

    if config_path:
        def strip_quotes(s: str) -> str:
            return s.strip('"\'') if s else s

        cfg = parse_config(config_path)
        if cfg:
            log.i("Parsed config file\n%s", str(cfg))

            # Globals
            global_section = cfg.pop(None)
            if global_section:
                if ServerConfigKeys.PORT in global_section:
                    port = to_int(global_section.get(ServerConfigKeys.PORT))

                if ServerConfigKeys.NAME in global_section:
                    name = strip_quotes(global_section.get(ServerConfigKeys.NAME, name))

                if ServerConfigKeys.PASSWORD in global_section:
                    password = strip_quotes(global_section.get(ServerConfigKeys.PASSWORD, name))

                    if password:
                        log.d("Global password found")

                if ServerConfigKeys.SSL in global_section:
                    # to_bool
                    ssl_enabled = to_bool(global_section.get(ServerConfigKeys.SSL, ssl_enabled))

                    if ssl_enabled:
                        log.i("SSL required on")
                        ssl_cert = strip_quotes(global_section.get(ServerConfigKeys.SSL_CERT, ssl_cert))
                        ssl_privkey = strip_quotes(global_section.get(ServerConfigKeys.SSL_PRIVKEY, ssl_privkey))

                        if not ssl_cert:
                            log.w("SSL required on, but ssl_cert has not been specified")

                        if not ssl_privkey:
                            log.w("SSL required on, but ssl_cert has not been specified")

            # Sharings
            for sharing_name, sharing_settings in cfg.items():

                sharing_password = strip_quotes(sharing_settings.get(ServerConfigKeys.PASSWORD))

                if sharing_password:
                    log.i("Sharing %s is protected by password", sharing_name)

                sharing = Sharing.create(
                    name=strip_quotes(sharing_name),
                    path=strip_quotes(sharing_settings.get(ServerConfigKeys.SHARING_PATH)),
                    read_only=to_bool(sharing_settings.get(ServerConfigKeys.SHARING_READ_ONLY, False)),
                    auth=AuthFactory.parse(sharing_password if sharing_password else password)
                )

                if not sharing:
                    log.w("Invalid or incomplete sharing config; skipping '%s'", str(sharing))
                    continue

                log.i("Adding valid sharing %s", sharing_name)

                sharings[sharing_name] = sharing
        else:
            log.w("Parsing error; ignoring config file")

    # Read arguments from command line (overwrite config)

    # Globals (port, name, ...)

    # Port
    if ServerArguments.PORT in args:
        port = to_int(args.get_param(ServerArguments.PORT))

    # Name
    if ServerArguments.NAME in args:
        name = args.get_param(ServerArguments.NAME)

    # Validation
    if not is_valid_port(port):
        abort(ErrorsStrings.INVALID_PORT)

    if not satisfy(name, SERVER_NAME_ALPHABET):
        log.e("Invalid server name %s", name)
        abort(ErrorsStrings.INVALID_SERVER_NAME)

    # Add sharings from command line
    # If a sharing with the same name already exists due to config file,
    # the values of the command line will overwrite those

    sharings_noarg_params = args.get_params()

    # sharings_arg_mparams can contain more than one sharing params
    # e.g. [['home', '/home/stefano'], ['tmp', '/tmp']]
    sharings_arg_mparams = args.get_mparams(ServerArguments.SHARE)

    sharings_params = []

    # Eventually add sharing specified without -s (the first one)
    if sharings_noarg_params:
        sharings_params.append(sharings_noarg_params)

    # Eventually add sharings specified with -s or --sharing
    if sharings_arg_mparams:
        for sh_params in sharings_arg_mparams:
            sharings_params.append(sh_params)

    if sharings_params:
        # Add sharings to server
        for sharing_params in sharings_params:
            if not is_valid_list(sharing_params):
                log.w("Skipping invalid sharing")
                log.i("Invalid sharing params: %s", sharing_params)
                continue

            sharing = Sharing.create(
                path=sharing_params[0],
                name=sharing_params[1] if len(sharing_params) > 1 else None,
                auth=AuthFactory.parse(password)  # allow parameters...
            )

            if not sharing:
                log.w("Invalid or incomplete sharing config; skipping sharing '%s'", str(sharing))
                continue

            log.i("Adding valid sharing [%s]", sharing)

            sharings[sharing.name] = sharing

    # SSL

    ssl_context = None
    if ssl_enabled and ssl_cert and ssl_privkey:
        log.i("Creating SSL context")
        log.i("SSL cert: %s", ssl_cert)
        log.i("SSL privkey: %s", ssl_privkey)
        ssl_context = create_server_ssl_context(cert=ssl_cert, privkey=ssl_privkey)

    # Configure pyro server
    server = Server(port, name, ssl_context)

    if not sharings:
        log.w("No sharings found, it will be an empty server")

    # Add every sharing to the server
    for sharing in sharings.values():
        print("+ " + sharing.name + " --> " + sharing.path)
        server.add_sharing(sharing)

    server.start()


if __name__ == "__main__":
    main()
