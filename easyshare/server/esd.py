import os
import queue
import sys
import socket
import threading
import time
import Pyro4 as Pyro4

from typing import Dict, Optional

from easyshare import utils
from easyshare.shared.args import Args
from easyshare.shared.conf import APP_VERSION, APP_NAME_SERVER_SHORT, APP_NAME_SERVER, DEFAULT_DISCOVER_PORT, \
    SERVER_NAME_ALPHABET
from easyshare.config.parser import parse_config
from easyshare.shared.log import init_logging_from_args, e, w, i, d, t
from easyshare.server.client import ClientContext
from easyshare.server.discoverdeamon import DiscoverDeamon
from easyshare.server.sharing import Sharing
from easyshare.shared.endpoint import Endpoint
from easyshare.protocol.iserver import IServer
from easyshare.protocol.serverinfo import ServerInfo
from easyshare.protocol.response import response_success, response_error, Response
from easyshare.protocol.errors import ServerErrors
from easyshare.utils.app import terminate, abort
from easyshare.utils.json import to_json_str
from easyshare.utils.net import get_primary_ip, is_valid_port
from easyshare.utils.str import randstring, strip, satisfy
from easyshare.utils.types import bytes_to_int, str_to_bytes, to_int, to_bool, is_valid_list

APP_INFO = APP_NAME_SERVER + " (" + APP_NAME_SERVER_SHORT + ") v. " + APP_VERSION

HELP = """easyshare deamon (esd)
...
"""


class ServerArguments:
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


class ErrorsStrings:
    INVALID_PORT = "Invalid port"
    INVALID_SERVER_NAME = "Invalid server name"


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

        response_data: ServerInfo = {
            "uri": self.uri,
            "name": self.name,
            "ip": server_endpoint[0],
            "port": server_endpoint[1],
            "sharings": list(self.sharings.keys())
        }

        response = response_success(response_data)

        client_discover_response_port = bytes_to_int(data)

        if not is_valid_port(client_discover_response_port):
            w("Invalid DISCOVER message received, ignoring it")
            return

        d("Client response port is %d", client_discover_response_port)

        discover_response = str_to_bytes(to_json_str(response))

        # Respond to the port the client says in the paylod
        # (not necessary the one from which the request come)
        resp_endpoint = (client_endpoint[0], client_discover_response_port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        d("Sending DISCOVER response back to %s\n%s",
          resp_endpoint, to_json_str(response, pretty=True))
        sock.sendto(discover_response, resp_endpoint)

    def start(self):
        i("Starting DISCOVER deamon")
        self.discover_deamon.start()

        i("Starting PYRO request loop")
        self.pyro_deamon.requestLoop()

    @Pyro4.expose
    def list(self):
        i("<< LIST %s", str(self._current_request_endpoint()))
        time.sleep(0.5)
        return response_success(self.sharings)

    @Pyro4.expose
    def open(self, sharing_name: str):
        if not sharing_name:
            return response_error(ServerErrors.INVALID_COMMAND_SYNTAX)

        if sharing_name not in self.sharings:
            return response_error(ServerErrors.SHARING_NOT_FOUND)

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

        return response_success()

    def close(self):
        pass

    @Pyro4.expose
    def rpwd(self) -> Response:
        # NOT NEEDED
        i("<< RPWD %s", str(self._current_request_endpoint()))

        client = self._current_request_client()
        if not client:
            return response_error(ServerErrors.NOT_CONNECTED)

        return response_success(client.rpwd)

    @Pyro4.expose
    def rcd(self, path) -> Response:
        if not path:
            return response_error(ServerErrors.INVALID_COMMAND_SYNTAX)

        client = self._current_request_client()
        if not client:
            return response_error(ServerErrors.NOT_CONNECTED)

        i("<< RCD %s (%s)", path, str(client))

        new_path = self._path_for_client(client, path)

        d("Sharing path: %s", new_path)

        if not self._is_path_allowed_for_client(client, new_path):
            e("Path is invalid (out of sharing domain)")
            return response_error(ServerErrors.INVALID_PATH)

        if not os.path.isdir(new_path):
            e("Path does not exists")
            return response_error(ServerErrors.INVALID_PATH)

        d("Path exists, success")

        client.rpwd = self._trailing_path_for_client(client, new_path)
        d("New rpwd: %s", client.rpwd)

        return response_success(client.rpwd)

    @Pyro4.expose
    def rls(self, sort_by="name") -> Response:
        client = self._current_request_client()
        if not client:
            w("Client not connected: %s", self._current_request_endpoint())
            return response_error(ServerErrors.NOT_CONNECTED)

        i("<< RLS (%s)",  str(client))

        try:
            client_path = self._current_client_path(client)

            d("Going to ls on %s", client_path)

            # Check path legality (it should be valid, if he rcd into it...)
            if not self._is_path_allowed_for_client(client, client_path):
                return response_error(ServerErrors.INVALID_PATH)

            ls_result = utils.os.ls(os.getcwd(), sort_by=sort_by)
            if not ls_result:
                return response_error(ServerErrors.COMMAND_EXECUTION_FAILED)

            d("RLS response %s", str(ls_result))

            return response_success(ls_result)
        except Exception as ex:
            e("RLS error: %s", str(ex))
            return response_error(ServerErrors.COMMAND_EXECUTION_FAILED)

    @Pyro4.expose
    def rmkdir(self, directory) -> Response:
        client = self._current_request_client()
        if not client:
            return response_error(ServerErrors.NOT_CONNECTED)

        i("<< RMKDIR %s (%s)", directory, str(client))

        try:
            full_path = os.path.join(self._current_client_path(client), directory)

            d("Going to mkdir on %s", full_path)

            if not self._is_path_allowed_for_client(client, full_path):
                return response_error(ServerErrors.INVALID_PATH)

            os.mkdir(full_path)
            return response_success()
        except Exception as ex:
            e("RMKDIR error: %s", str(ex))
            return response_error(ServerErrors.COMMAND_EXECUTION_FAILED)

    @Pyro4.expose
    def get(self, files) -> Response:
        client = self._current_request_client()
        if not client:
            return response_error(ServerErrors.NOT_CONNECTED)

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

        # Create a socket
        transaction_handler = GetTransactionHandler(normalized_files)
        transaction_handler.files_server.start()

        self.gets[transaction] = transaction_handler

        return response_success({
            "transaction": transaction,
            "port": transaction_handler.files_server.sock.getsockname()[1]
        })

    @Pyro4.expose
    def get_next(self, transaction) -> Response:
        client = self._current_request_client()
        if not client:
            return response_error(ServerErrors.NOT_CONNECTED)

        i("<< GET_NEXT_METADATA %s (%s)", transaction, str(client))

        if transaction not in self.gets:
            return response_error(ServerErrors.INVALID_TRANSACTION)

        transaction_handler = self.gets[transaction]
        remaining_files = transaction_handler.next_files

        # if len(self.gets[transaction]) == 0:
        #     return server_response_success()  # Nothing else

        while len(remaining_files) > 0:

            # Get next file (or dir)
            next_file_path = remaining_files.pop()

            d("Next file path: %s", next_file_path)

            # Check domain validity
            if not self._is_path_allowed_for_client(client, next_file_path):
                w("Invalid file found: skipping %s", next_file_path)
                continue

            if os.path.isdir(next_file_path):
                d("Found a directory: adding all inner files to remaining_files")
                for f in os.listdir(next_file_path):
                    f_path = os.path.join(next_file_path, f)
                    d("Adding %s", f_path)
                    remaining_files.append(f_path)
                continue

            if not os.path.isfile(next_file_path):
                w("Not file nor dir? skipping")
                continue

            # We are handling a valid file, report the metadata to the client
            d("NEXT FILE: %s", next_file_path)

            trail = self._trailing_path_for_client(client, next_file_path)
            d("Trail: %s", trail)

            transaction_handler.files_server.push_file(next_file_path)

            return response_success({
                "name": trail,
                "length": os.path.getsize(next_file_path)
            })

        d("No remaining files")
        transaction_handler.files_server.pushes_completed()
        # Notify the handler about it
        return response_success("ok")

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
        :param client: the client
        :return: the path of the client, relatively to the server's filesystem
        """
        if not client:
            return None

        sharing: Sharing = self._current_client_sharing(client)

        if not sharing:
            return None

        return os.path.join(sharing.path, client.rpwd)

    def _path_for_client(self, client: ClientContext, path: str):
        sharing = self._current_client_sharing(client)

        if not sharing:
            return None

        if path.startswith(os.sep):
            # If path begins with / it refers to the root of the current sharing
            trail = path.lstrip(os.sep)
        else:
            # Otherwise it refers to a subdirectory starting from the current rpwd
            trail = os.path.join(client.rpwd, path)

        return os.path.normpath(os.path.join(sharing.path, trail))

    def _trailing_path_for_client(self, client: ClientContext, path: str):
        # with [home] = /home/stefano
        #   /home/stefano/Applications -> Applications
        return path.split(self._current_client_sharing(client))[1].lstrip(os.sep)

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


class GetTransactionHandler:
    def __init__(self, files):
        self.files_server = GetFilesServer()
        self.next_files = files


class GetFilesServer(threading.Thread):
    BUFFER_SIZE = 1024 * 4

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((get_primary_ip(), 0))
        self.sock.listen(1)

        self.servings = queue.Queue()
        threading.Thread.__init__(self)

    def create_socket(self) -> Endpoint:
        return self.sock.getsockname()

    def run(self) -> None:
        if not self.sock:
            e("Invalid socket")
            return

        t("Starting GetHandler")
        client_sock, addr = self.sock.accept()
        i("Connection established with %s", addr)

        while True:
            # Send files until the servings buffer is fulfilled
            # Wait on the blocking queue for the next file to send
            next_serving = self.servings.get()

            if not next_serving:
                d("No more files: END")
                break

            d("Next serving: %s", next_serving)

            f = open(next_serving, "rb")
            cur_pos = 0
            file_len = os.path.getsize(next_serving)

            # Send file
            while True:
                chunk = f.read(GetFilesServer.BUFFER_SIZE)
                if not chunk:
                    d("Finished %s", next_serving)
                    break

                d("Read chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                try:
                    t("sendall() ...")
                    client_sock.sendall(chunk)
                    t("sendall() OK")
                except Exception as ex:
                    e("sendall error %s", ex)
                    break

                d("%d/%d (%.2f%%)", cur_pos, file_len, cur_pos / file_len * 100)

            f.close()

        # client_sock.shutdown(socket.SHUT_RDWR)
        # self.sock.close()

    def push_file(self, path: str):
        d("Pushing file to handler %s", path)
        self.servings.put(path)

    def pushes_completed(self):
        d("end(): no more files")
        self.servings.put(None)


def main():
    if len(sys.argv) <= 1:
        terminate(HELP)

    args = Args(sys.argv[1:])

    if ServerArguments.HELP in args:
        terminate(HELP)

    if ServerArguments.VERSION in args:
        terminate(APP_INFO)

    init_logging_from_args(args, ServerArguments.VERBOSE)

    i(APP_INFO)

    # Init stuff with default values
    sharings = {}
    port = DEFAULT_DISCOVER_PORT
    name = socket.gethostname()

    # Eventually parse config file
    config_path = args.get_param(ServerArguments.CONFIG)

    if config_path:
        def strip_quotes(s: str) -> str:
            return strip(s, '"\'')

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
                read_only=False)

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


if __name__ == "__main__":
    main()
