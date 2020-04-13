import os
import queue
import sys
import socket
import threading
import time

import Pyro4 as Pyro4

from typing import Dict, Optional, List

from easyshare.protocol.filetype import FTYPE_FILE
from easyshare.protocol.response import create_success_response, create_error_response, Response
from easyshare.server.sharing import Sharing
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
from easyshare.socket.tcp import SocketTcpAcceptor
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

    def close(self):
        pass

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
        return create_error_response(ServerErrors.NOT_IMPLEMENTED)

    @Pyro4.expose
    def get(self, files: List[str]) -> Response:
        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        i("<< GET %s (%s)", str(files), str(client))

        if len(files) == 0:
            files = ["."]

        # Compute real path for each name
        normalized_files = []
        for f in files:
            normalized_files.append(self._path_for_client(client, f))

        d("Normalized files:\n%s", normalized_files)

        # Return a transaction ID for identify the transfer
        transaction = randstring()
        v("Transaction ID: %s", transaction)

        # Create a transaction handler
        transaction_handler = GetTransactionHandler(normalized_files)
        transaction_handler.start()

        self.gets[transaction] = transaction_handler

        return create_success_response({
            "transaction": transaction,
            "port": transaction_handler.get_port()
        })

    @Pyro4.expose
    def get_next(self, transaction) -> Response:
        client = self._current_request_client()
        if not client:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        i("<< GET_NEXT_METADATA %s (%s)", transaction, str(client))

        if transaction not in self.gets:
            return create_error_response(ServerErrors.INVALID_TRANSACTION)

        transaction_handler = self.gets[transaction]
        remaining_files = transaction_handler.next_files

        # if len(self.gets[transaction]) == 0:
        #     return server_create_success_response()  # Nothing else

        while len(remaining_files) > 0:

            # Get next file (or dir)
            next_file_path = remaining_files.pop()

            d("Next file path: %s", next_file_path)

            # Check domain validity
            if not self._is_path_allowed_for_client(client, next_file_path):
                w("Invalid file found: skipping %s", next_file_path)
                continue

            if os.path.isdir(next_file_path):
                # Directory found
                v("Found a directory: adding all inner files to remaining_files")
                for f in os.listdir(next_file_path):
                    f_path = os.path.join(next_file_path, f)
                    d("Adding %s", f_path)
                    remaining_files.append(f_path)
                continue

            if not os.path.isfile(next_file_path):
                w("Not file nor dir? skipping %s", next_file_path)
                continue

            # We are handling a valid file, report the metadata to the client
            d("NEXT FILE: %s", next_file_path)

            trail = self._trailing_path_for_client_from_rpwd(client, next_file_path)
            d("Trail: %s", trail)

            transaction_handler.push_file(next_file_path)

            return create_success_response({
                "name": trail,
                "ftype": FTYPE_FILE,
                "size": os.path.getsize(next_file_path)
            })

        v("No remaining files")
        transaction_handler.pushes_completed()
        # Notify the handler about it
        return create_success_response()

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

    def _trailing_path_for_client_from_root(self, client: ClientContext, path: str) -> Optional[str]:
        """
        Returns the trailing part of the 'path' by stripping the path of the
        sharing from the string's beginning.
        The path is relative w.r.t the root of the sharing path.
        e.g.
            client sharing path = /home/stefano/Applications
            client rpwd         =                            AnApp
            (client path        = /home/stefano/Applications/AnApp          )
            path                = /home/stefano/Applications/AnApp/afile.mp4
                                =>                           AnApp/afile.mp4
        """

        sh = self._current_client_sharing(client)

        if not sh:
            return None

        if not path.startswith(sh.path):
            return None

        return relpath(unprefix(path, sh.path))

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
        client_path = self._current_client_path(client)

        if not client_path:
            return None

        if not path.startswith(client_path):
            return None

        return relpath(unprefix(path, client_path))

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

    def _endpoint(self) -> Endpoint:
        """
        Returns the current endpoint (ip, port) the server (Pyro deamon) is bound to.
        :return: the current server endpoint
        """
        return self.pyro_deamon.sock.getsockname()


class GetTransactionHandler(threading.Thread):
    BUFFER_SIZE = 4096

    def __init__(self, files: List[str]):
        self.next_files = files
        self.sock = SocketTcpAcceptor()
        self.servings = queue.Queue()
        threading.Thread.__init__(self)

    def get_port(self):
        return self.sock.port()

    def run(self) -> None:
        if not self.sock:
            e("Invalid socket")
            return

        d("Starting GetTransactionHandler")
        client_sock, endpoint = self.sock.accept()
        i("Connection established with %s", endpoint)

        while True:
            # Send files until the servings buffer is empty
            # Wait on the blocking queue for the next file to send
            next_serving = self.servings.get()

            if not next_serving:
                v("No more files: END")
                break

            d("Next serving: %s", next_serving)

            f = open(next_serving, "rb")
            cur_pos = 0
            file_len = os.path.getsize(next_serving)

            # Send file
            while True:
                time.sleep(0.1)
                chunk = f.read(GetTransactionHandler.BUFFER_SIZE)
                if not chunk:
                    d("Finished %s", next_serving)
                    break

                d("Read chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                try:
                    d("sending chunk...")
                    client_sock.send(chunk)
                    d("sending chunk DONE")
                except Exception as ex:
                    e("send error %s", ex)
                    break

                d("%d/%d (%.2f%%)", cur_pos, file_len, cur_pos / file_len * 100)

            f.close()

        v("Transaction handler job finished")

        client_sock.close()
        self.sock.close()

    def push_file(self, path: str):
        d("Pushing file to handler %s", path)
        self.servings.put(path)

    def pushes_completed(self):
        v("end(): no more files")
        self.servings.put(None)


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
            return s.strip('"\'')

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
                    w("Invalid or incomplete sharing config; skipping %s", str(sharing))
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
                w("Invalid or incomplete sharing config; skipping %s", str(sharing))
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
