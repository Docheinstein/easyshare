import os
import queue
import sys
import socket
import threading
import time

import Pyro4 as Pyro4

from typing import Dict, Optional, List

import colorama

from easyshare.protocol.filetype import FTYPE_FILE
from easyshare.protocol.response import create_success_response, create_error_response, Response
from easyshare.server.sharing import Sharing
from easyshare.server.transaction import GetTransactionHandler
from easyshare.shared.args import Args
from easyshare.shared.conf import APP_VERSION, APP_NAME_SERVER_SHORT, \
    APP_NAME_SERVER, DEFAULT_DISCOVER_PORT, SERVER_NAME_ALPHABET
from easyshare.config.parser import parse_config
from easyshare.shared.log import e, w, i, d, init_logging, v, VERBOSITY_VERBOSE
from easyshare.server.client import ClientContext
from easyshare.server.discover import DiscoverDeamon
from easyshare.shared.endpoint import Endpoint
from easyshare.protocol.iserver import IServer
from easyshare.protocol.errors import ServerErrors
from easyshare.shared.trace import init_tracing
from easyshare.socket.udp import SocketUdpOut
from easyshare.utils.app import terminate, abort
from easyshare.utils.json import json_to_str, json_to_bytes
from easyshare.utils.net import get_primary_ip, is_valid_port
from easyshare.utils.os import ls, relpath, is_relpath
from easyshare.utils.str import randstring, satisfy, unprefix
from easyshare.utils.types import bytes_to_int, to_int, to_bool, is_valid_list

# ==================================================================


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


class ServerConfigKeys:
    PORT = "port"
    NAME = "name"
    SHARING_PATH = "path"
    SHARING_READ_ONLY = "read-only"


# === ERRORS ===


class ErrorsStrings:
    INVALID_PORT = "Invalid port"
    INVALID_SERVER_NAME = "Invalid server name"


# ==================================================================


class Server(IServer):

    def __init__(self, discover_port, name):
        self.ip = get_primary_ip()
        self.name = name

        # sharing_name -> sharing
        self.sharings: Dict[str, Sharing] = {}
        self.clients: Dict[Endpoint, ClientContext] = {}
        self.gets: Dict[str, GetTransactionHandler] = {}

        self.pyro_deamon = Pyro4.Daemon(host=self.ip)
        self.discover_deamon = DiscoverDeamon(discover_port, self.handle_discover_request)

        self.uri = self.pyro_deamon.register(self).asString()

        d("Server's name: %s", name)
        d("Server's discover port: %d", discover_port)
        d("Primary interface IP: %s", self.ip)
        d("Server registered at URI: %s", self.uri)

    def add_sharing(self, sharing: Sharing):
        i("+ SHARING %s", sharing)
        self.sharings[sharing.name] = sharing

    def handle_discover_request(self, client_endpoint: Endpoint, data: bytes):
        i("<< DISCOVER %s", client_endpoint)
        d("Handling discover %s", str(data))

        server_endpoint = self._endpoint()

        response_data = {
            "uri": self.uri,
            "name": self.name,
            "ip": server_endpoint[0],
            "port": server_endpoint[1],
            "sharings": [sh.info() for sh in self.sharings.values()]
        }

        response = create_success_response(response_data)

        client_discover_response_port = bytes_to_int(data)

        if not is_valid_port(client_discover_response_port):
            w("Invalid DISCOVER message received, ignoring it")
            return

        d("Client response port is %d", client_discover_response_port)

        # Respond to the port the client says in the paylod
        # (not necessary the one from which the request come)
        sock = SocketUdpOut()

        d("Sending DISCOVER response back to %s:%d\n%s",
          client_endpoint[0], client_discover_response_port,
          json_to_str(response, pretty=True))

        sock.send(json_to_bytes(response), client_endpoint[0], client_discover_response_port)

    def start(self):
        i("Starting DISCOVER deamon")
        self.discover_deamon.start()

        i("Starting PYRO request loop")
        self.pyro_deamon.requestLoop()

    @Pyro4.expose
    def list(self) -> Response:
        i("<< LIST %s", str(self._current_request_endpoint()))
        time.sleep(0.5)
        return create_success_response([sh.info() for sh in self.sharings.values()])

    @Pyro4.expose
    def open(self, sharing_name: str) -> Response:
        if not sharing_name:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        if sharing_name not in self.sharings:
            return create_error_response(ServerErrors.SHARING_NOT_FOUND)

        client_endpoint = self._current_request_endpoint()
        i("<< OPEN %s %s", sharing_name, str(client_endpoint))

        client = self._current_request_client()
        if not client:
            # New client
            client = ClientContext()
            client.endpoint = client_endpoint
            client.sharing_name = sharing_name
            self.clients[client_endpoint] = client
            i("New client connected (%s) to sharing %s",
              str(client), client.sharing_name)
        else:
            client.sharing_name = sharing_name
            client.rpwd = ""
            i("Already connected client (%s) changed sharing to %s",
              str(client), client.sharing_name)

        return create_success_response()

    @Pyro4.expose
    @Pyro4.oneway
    def close(self):
        client_endpoint = self._current_request_endpoint()
        i("<< CLOSE %s", str(client_endpoint))
        client = self._current_request_client()

        if not client:
            w("Received a close request from an unknown client")
            return

        v("Deallocating client resources...")

        # Remove any pending transaction
        for get_trans_id in client.gets:
            # self._end_get_transaction(get_trans_id, client, abort=True)
            if get_trans_id in self.gets:
                v("Removing GET transaction = %s", get_trans_id)
                self.gets.pop(get_trans_id).abort()

        # Remove from clients
        d("Removing %s from clients", client)

        del self.clients[client_endpoint]
        v("Client connection closed gracefully")

        d("# clients = %d", len(self.clients))
        d("# gets = %d", len(self.gets))

    @Pyro4.expose
    def rpwd(self) -> Response:
        # NOT NEEDED
        i("<< RPWD %s", str(self._current_request_endpoint()))

        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        return create_success_response(client.rpwd)

    @Pyro4.expose
    def rcd(self, path: str) -> Response:
        if not path:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        i("<< RCD %s (%s)", path, str(client))

        new_path = self._path_for_client(client, path)

        d("Sharing path: %s", new_path)

        if not self._is_path_allowed_for_client(client, new_path):
            e("Path is invalid (out of sharing domain)")
            return create_error_response(ServerErrors.INVALID_PATH)

        if not os.path.isdir(new_path):
            e("Path does not exists")
            return create_error_response(ServerErrors.INVALID_PATH)

        v("Path exists, success")

        client.rpwd = self._trailing_path_for_client_from_root(client, new_path)
        d("New rpwd: %s", client.rpwd)

        return create_success_response(client.rpwd)

    @Pyro4.expose
    def rls(self, sort_by: List[str], reverse=False) -> Response:
        client = self._current_request_client()
        if not client:
            w("Client not connected: %s", self._current_request_endpoint())
            return create_error_response(ServerErrors.NOT_CONNECTED)

        i("<< RLS %s%s (%s)", sort_by, " | reverse " if reverse else "", str(client))

        try:
            client_path = self._current_client_path(client)

            d("Going to ls on %s", client_path)

            # Check path legality (it should be valid, if he rcd into it...)
            if not self._is_path_allowed_for_client(client, client_path):
                return create_error_response(ServerErrors.INVALID_PATH)

            ls_result = ls(client_path, sort_by=sort_by, reverse=reverse)
            if not ls_result:
                return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

            d("RLS response %s", str(ls_result))

            return create_success_response(ls_result)
        except Exception as ex:
            e("RLS error: %s", str(ex))
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

    @Pyro4.expose
    def rmkdir(self, directory: str) -> Response:
        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        i("<< RMKDIR %s (%s)", directory, str(client))

        try:
            full_path = os.path.join(self._current_client_path(client), directory)

            d("Going to mkdir on %s", full_path)

            if not self._is_path_allowed_for_client(client, full_path):
                return create_error_response(ServerErrors.INVALID_PATH)

            os.mkdir(full_path)
            return create_success_response()
        except Exception as ex:
            e("RMKDIR error: %s", str(ex))
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

    @Pyro4.expose
    def get_sharing(self, sharing_name: str) -> Response:
        client_endpoint = self._current_request_endpoint()

        if not sharing_name:
            w("Sharing name not specified")
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        i("<< GET [sharing] %s %s", sharing_name, str(client_endpoint))

        sharing = self.sharings.get(sharing_name)

        if not sharing:
            w("Sharing '%s' not found", sharing_name)
            return create_error_response(ServerErrors.SHARING_NOT_FOUND)

        d("Making %s available for GET", sharing.path)
        transaction_handler = self._add_get_transaction(
            [sharing.path],
            sharing_name=sharing_name)

        return create_success_response({
            "transaction": transaction_handler.transaction_id(),
            "port": transaction_handler.port()
        })

    @Pyro4.expose
    def get_files(self, files: List[str]) -> Response:
        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        i("<< GET [files] %s (%s)", str(files), str(client))

        if len(files) == 0:
            files = ["."]

        # Compute real path for each name
        normalized_files = []
        for f in files:
            normalized_files.append(self._path_for_client(client, f))

        d("Normalized files:\n%s", normalized_files)

        transaction_handler = self._add_get_transaction(
            normalized_files,
            client=client,
            sharing_name=client.sharing_name)

        return create_success_response({
            "transaction": transaction_handler.transaction_id(),
            "port": transaction_handler.port()
        })

    @Pyro4.expose
    def get_sharing_next_info(self, transaction_id) -> Response:
        client_endpoint = self._current_request_endpoint()

        i("<< GET_SHARING_NEXT_INFO %s %s", transaction_id, str(client_endpoint))

        return self._get_next_info(transaction_id)

    @Pyro4.expose
    def get_files_next_info(self, transaction_id) -> Response:
        client = self._current_request_client()

        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        i("<< GET_FILES_NEXT_INFO %s %s", transaction_id, str(client))

        return self._get_next_info(transaction_id,
                                   client=client)

    def _get_next_info(self,
                       transaction_id: str,
                       client: Optional[ClientContext] = None) -> Response:

        d("_get_next_if %s", transaction_id)

        if transaction_id not in self.gets:
            return create_error_response(ServerErrors.INVALID_TRANSACTION)

        transaction_handler = self.gets[transaction_id]

        sharing = self.sharings.get(transaction_handler.sharing_name())
        if not sharing:
            e("Sharing '%s' not found", transaction_handler.sharing_name())
            return create_error_response(ServerErrors.SHARING_NOT_FOUND)

        remaining_files = transaction_handler.next_files()

        while len(remaining_files) > 0:

            # Get next file (or dir)
            next_file_path = remaining_files.pop()

            d("Next file path: %s", next_file_path)

            # Check domain validity
            # (if client is null the domain is valid for sure since it should
            # be the sharing path we added ourself)
            if client and not self._is_path_allowed_for_client(client, next_file_path):
                w("Invalid file found: skipping %s", next_file_path)
                continue

            if os.path.isdir(next_file_path):
                # Directory found
                v("Found a directory: adding all inner files to remaining_files")
                for f in os.listdir(next_file_path):
                    f_path = os.path.join(next_file_path, f)
                    d("Adding %s", f_path)
                    # Push to the begin instead of the end
                    # In this way we perform a breadth-first search
                    # instead of a depth-first search, which makes more sense
                    # because we will push the files that belongs to the same
                    # directory at the same time
                    remaining_files.insert(0, f_path)
                continue

            if not os.path.isfile(next_file_path):
                w("Not file nor dir? skipping %s", next_file_path)
                continue

            # We are handling a valid file, report the metadata to the client
            d("NEXT FILE: %s", next_file_path)

            if client:
                trail = self._trailing_path_for_client_from_rpwd(client, next_file_path)
            else:
                sharing_path_head, _ = os.path.split(sharing.path)
                d("sharing_path_head: ", sharing_path_head)
                trail = self._trailing_path(sharing_path_head, next_file_path)

            d("Trail: %s", trail)

            # Push the file the transaction handler (make it available
            # for the actual download)
            transaction_handler.push_file(next_file_path)

            return create_success_response({
                "name": trail,
                "ftype": FTYPE_FILE,
                "size": os.path.getsize(next_file_path)
            })

        v("No remaining files")
        transaction_handler.done()

        # Notify the client about it
        return create_success_response()

    def _add_get_transaction(self,
                             files: List[str],
                             sharing_name: str,
                             client: Optional[ClientContext] = None) -> GetTransactionHandler:

        d("_add_get_transaction files: %s", files)
        # Create a transaction handler
        transaction_handler = GetTransactionHandler(
            files,
            sharing_name,
            on_end=self._on_get_transaction_end,
            owner=client)

        transaction_id = transaction_handler.transaction_id()
        v("Transaction ID: %s", transaction_id)

        transaction_handler.start()

        if client:
            client.gets.append(transaction_id)

        self.gets[transaction_id] = transaction_handler

        return transaction_handler

    def _on_get_transaction_end(self, finished_transaction: GetTransactionHandler):
        trans_id = finished_transaction.transaction_id()

        v("Finished transaction %s", trans_id)

        if trans_id in self.gets:
            d("Removing transaction from gets")
            del self.gets[trans_id]

        owner = finished_transaction.owner()

        if owner:
            d("Removing transaction from '%s' gets", owner)
            owner.gets.remove(trans_id)

    # def _end_get_transaction(self, transaction_id: str,
    #                          client: Optional[ClientContext], *,
    #                          abort: bool = False):
    #     if transaction_id not in self.gets:
    #         w("Transaction with id %s not found", transaction_id)
    #         return
    #
    #     transaction_handler = self.gets.pop(transaction_id)
    #
    #     if abort:
    #         d("_end_get_transaction: aborting transaction")
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
            w("Sharing not found %s", client.sharing_name)
            return False

        normalized_path = os.path.normpath(path)

        try:
            common_path = os.path.commonpath([normalized_path, sharing.path])
            d("Common path between '%s' and '%s' = '%s'",
              normalized_path, sharing.path, common_path)

            return sharing.path == common_path
        except:
            return False

    def _trace_request(self, function: str, *function_args, **function_kwargs):
        pass

    def trace_response(self):
        #
        # def _perform_request(self, ,
        #                      *remote_function_args,
        #                      **remote_function_kwargs) -> Optional[Response]:
        #     if is_tracing_enabled():
        #         remote_function_args_str = "{}{}".format(
        #             ", ".join([strstr(x) for x in remote_function_args])
        #             if remote_function_args else "",
        #
        #             ", ".join([str(k) + "=" + strstr(v) for k, v in remote_function_kwargs.items()])
        #             if remote_function_kwargs else ""
        #         )
        #         trace_out(ip=self.server_info.get("ip"),
        #                   port=self.server_info.get("port"),
        #                   name=self.server_info.get("name"),
        #                   message="{} ({})".format(remote_function, remote_function_args_str))
        #
        #     resp = self.server.__getattr__(remote_function)(*remote_function_args, **remote_function_kwargs)
        #
        #     if is_tracing_enabled() and resp:
        #         trace_in(ip=self.server_info.get("ip"),
        #                  port=self.server_info.get("port"),
        #                  name=self.server_info.get("name"),
        #                  message="{}\n{}".format(remote_function, json_to_str(resp, pretty=True)))

            return resp

    def _endpoint(self) -> Endpoint:
        """
        Returns the current endpoint (ip, port) the server (Pyro deamon) is bound to.
        :return: the current server endpoint
        """
        return self.pyro_deamon.sock.getsockname()


def main():
    if len(sys.argv) <= 1:
        terminate(HELP_APP)

    args = Args(sys.argv[1:])

    if ServerArguments.HELP in args:
        terminate(HELP_APP)

    if ServerArguments.VERSION in args:
        terminate(APP_INFO)

    verbosity = 0
    tracing = 0

    if ServerArguments.VERBOSE in args:
        verbosity = to_int(args.get_param(ServerArguments.VERBOSE, default=VERBOSITY_VERBOSE))
        if verbosity is None:
            abort("Invalid --verbose parameter value")

    if ServerArguments.TRACE in args:
        tracing = to_int(args.get_param(ServerArguments.TRACE, default=1))
        if tracing is None:
            abort("Invalid --trace parameter value")

    init_logging(verbosity)
    init_tracing(True if tracing else False)

    i(APP_INFO)

    # Init stuff with default values
    sharings = {}
    port = DEFAULT_DISCOVER_PORT
    name = socket.gethostname()

    # Eventually parse config file
    config_path = args.get_param(ServerArguments.CONFIG)

    if config_path:
        def strip_quotes(s: str) -> str:
            return s.strip('"\'') if s else s

        cfg = parse_config(config_path)
        if cfg:
            i("Parsed config file\n%s", str(cfg))

            # Globals
            global_section = cfg.pop(None)
            if global_section:
                if ServerConfigKeys.PORT in global_section:
                    port = to_int(global_section.get(ServerConfigKeys.PORT))

                if ServerConfigKeys.NAME in global_section:
                    name = global_section.get(ServerConfigKeys.NAME, name)

            # Sharings
            for sharing_name, sharing_settings in cfg.items():

                sharing = Sharing.create(
                    name=strip_quotes(sharing_name),
                    path=strip_quotes(sharing_settings.get(ServerConfigKeys.SHARING_PATH)),
                    read_only=to_bool(sharing_settings.get(ServerConfigKeys.SHARING_READ_ONLY, False))
                )

                if not sharing:
                    w("Invalid or incomplete sharing config; skipping '%s'", str(sharing))
                    continue

                d("Adding valid sharing %s", sharing_name)

                sharings[sharing_name] = sharing
        else:
            w("Parsing error; ignoring config file")

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
        e("Invalid server name %s", name)
        abort(ErrorsStrings.INVALID_SERVER_NAME)

    # Add sharings from command line
    # If a sharing with the same name already exists due to config file,
    # the values of the command line will overwrite those
    sharings_params = args.get_mparams(ServerArguments.SHARE)

    # sharings_mparams can contain more than one sharing params
    # e.g. [['home', '/home/stefano'], ['tmp', '/tmp']]

    if sharings_params:
        # Add sharings to server
        for sharing_params in sharings_params:
            if not is_valid_list(sharing_params):
                w("Skipping invalid sharing")
                d("Invalid sharing params: %s", sharing_params)
                continue

            sharing = Sharing.create(
                path=sharing_params[0],
                name=sharing_params[1] if len(sharing_params) > 1 else None,
                read_only=False
            )

            if not sharing:
                w("Invalid or incomplete sharing config; skipping sharing '%s'", str(sharing))
                continue

            d("Adding valid sharing [%s]", sharing)

            sharings[sharing.name] = sharing

    # Configure pyro server
    server = Server(port, name)

    if not sharings:
        w("No sharings found, it will be an empty server")

    # Add every sharing to the server
    for sharing in sharings.values():
        server.add_sharing(sharing)

    server.start()

#
# class CustomJsonEncoder(JSONEncoder):
#     def default(self, o):
#         return items(o)


if __name__ == "__main__":
    # sh = Sharing("sharingname", "file", "/tmp", False)
    # si = ServerInfo(
    #     "http",
    #     "nemo",
    #     "192.168.1.1",
    #     8001,
    #     [sh]
    # )
    #
    # print(json.dumps(si, separators=(",", ":"), cls=CustomJsonEncoder))
    main()
