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

import Pyro4

from commands import Commands
from conf import Conf, LoggingLevels
from consts import ADDR_ANY, ADDR_BROADCAST
from log import init_logging
from utils import eprint

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

class EasyshareServerInfo:
    def __init__(self):
        self.uri = None
        self.hostname = None
        self.address = None
        self.port = None
        self.sharings = None


class EasyshareDiscoverResponseListener(threading.Thread):
    def __init__(self, discover_handler, timeout=Conf.DISCOVER_DEFAULT_TIMEOUT_SEC):
        threading.Thread.__init__(self)
        # {
        #   handle_discover_response(addr, data)
        #   handle_discover_finished()
        # }
        self.discover_handler = discover_handler
        self.timeout=timeout

    def run(self) -> None:
        logging.debug("Starting DISCOVER listener")
        discover_client_addr = (ADDR_ANY, Conf.DISCOVER_PORT_CLIENT)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Do not wait more than a certain time anyway
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO,
                        struct.pack("LL", ceil(self.timeout), 0))
        sock.bind(discover_client_addr)

        discover_start_time = datetime.now()

        remaining_seconds = self.timeout

        while remaining_seconds > 0:
            logging.trace("Waiting for %.2f seconds...", remaining_seconds)

            read_fds, write_fds, error_fds = select.select([sock], [], [], remaining_seconds)

            if sock in read_fds:
                logging.trace("DISCOVER socket ready for recv")
                data, addr = sock.recvfrom(1024)
                logging.debug("Received DISCOVER response from: %s", addr)
                self.discover_handler.handle_discover_response(addr, data)
            else:
                logging.trace("DISCOVER timeout elapsed (%.2f)", self.timeout)

            remaining_seconds = \
                self.timeout - (datetime.now() - discover_start_time).total_seconds()

        logging.debug("Stopping DISCOVER listener")
        self.discover_handler.handle_discover_finished()


class EasyshareDiscoverer:
    def __init__(self, timeout=Conf.DISCOVER_DEFAULT_TIMEOUT_SEC):
        self.sharings = None
        self.discover_sync = None
        self.timeout = timeout

    def discover(self):
        # Start discover response deamon
        self.sharings = []
        self.discover_sync = threading.Semaphore(0)
        discover_deamon = EasyshareDiscoverResponseListener(self, self.timeout)
        discover_deamon.start()

        # Send discover
        discover_broadcast_address = (ADDR_BROADCAST, Conf.DISCOVER_PORT_SERVER)
        discover_message = bytes("DISCOVER", encoding="UTF-8")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        logging.debug("Sending DISCOVER message")
        sock.sendto(discover_message, discover_broadcast_address)

        # Wait until discover is finished
        self.discover_sync.acquire()

        return self.sharings

    def handle_discover_response(self, client, response):
        try:
            logging.info("Got DISCOVER response from %s: %s", client, response)

            if not response:
                logging.warning("Received unexpected response (null response)")
                return

            response_str = str(response, encoding="UTF-8")
            uri, hostname, port = response_str.split("\n")

            if not uri.startswith("PYRO"):
                logging.warning("Received unexpected response")
                return
        except Exception:
            logging.warning("Received unexpected response")
            return

        with Pyro4.Proxy(uri) as server:
            logging.trace("Retrieving sharings LIST from server %s(%s)", hostname, uri)
            server_sharings = server.list_sharings()
            logging.debug("Retrieved sharings LIST from server %s(%s)", hostname, uri)

            server_info = EasyshareServerInfo()
            server_info.uri = uri
            server_info.hostname = hostname
            server_info.address = client[0]
            server_info.port = int(port)
            server_info.sharings = server_sharings

            self.sharings.append(server_info)

    def handle_discover_finished(self):
        logging.info("DISCOVER finished")

        self.discover_sync.release()

class EasyshareConnection:
    def __init__(self, uri):
        self.uri = uri
        self.server = Pyro4.Proxy(uri)


    def open(self):
        self.server.connect()

# ========================

class EasyshareClient:
    def __init__(self):
        self.connection = None
        # self.pwd = os.getcwd()
        self.command_dispatcher = {
            Commands.HELP: self._execute_help,
            Commands.LOCAL_CHANGE_DIRECTORY: self._execute_cd,
            Commands.REMOTE_CHANGE_DIRECTORY: self._execute_rcd,
            Commands.LOCAL_LIST_DIRECTORY: self._execute_ls,
            Commands.LOCAL_CREATE_DIRECTORY: self._execute_mkdir,
            Commands.LOCAL_CURRENT_DIRECTORY: self._execute_pwd,
            Commands.REMOTE_CURRENT_DIRECTORY: self._execute_rpwd,
            Commands.OPEN: self._execute_open,
            Commands.SCAN: self._execute_scan
        }

    def execute_command(self, full_command):
        full_command = full_command.split()
        if len(full_command) < 1:
            return

        command = full_command[0]
        args = full_command[1:]
        if command in self.command_dispatcher:
            logging.trace("Handling command {%s}" % command)
            self.command_dispatcher[command](args)
            return True
        else:
            return False


    def _execute_help(self, _):
        print(HELP)

    def _execute_cd(self, args):
        if len(args) <= 0:
            eprint(EasyshareShell.INVALID_COMMAND_SYNTAX)
            return

        directory = args[0]
        logging.info("CD " + directory)
        try:
            os.chdir(directory)
        except Exception as e:
            logging.error(EasyshareShell.COMMAND_EXECUTION_ERROR)
            eprint(e)

    def _execute_rcd(self, args):
        pass

    def _execute_ls(self, args):
        try:
            for f in os.listdir("."):
                print(f)
        except Exception as e:
            logging.error(EasyshareShell.COMMAND_EXECUTION_ERROR)
            eprint(e)

    def _execute_mkdir(self, args):
        if len(args) <= 0:
            eprint(EasyshareShell.INVALID_COMMAND_SYNTAX)
            return

        directory = args[0]
        logging.info("MKDIR " + directory)
        try:
            os.mkdir(directory)
        except Exception as e:
            logging.error(EasyshareShell.COMMAND_EXECUTION_ERROR)
            eprint(e)

    def _execute_pwd(self, args):
        try:
            logging.info("PWD")
            print(os.getcwd())
        except Exception as e:
            logging.error(EasyshareShell.COMMAND_EXECUTION_ERROR)
            eprint(e)

    def _execute_rpwd(self, args):
        if not self.connection:
            eprint("Not connected")
            return

    def _execute_open(self, args):
        if len(args) <= 0:
            eprint(EasyshareShell.INVALID_COMMAND_SYNTAX)
            return

        sharing_name = args[0]
        logging.info("OPEN " + sharing_name)

        # Close connection if already established
        # ...

        # Discover the connection associated with the sharing name
        sharings = EasyshareDiscoverer(Conf.DISCOVER_DEFAULT_TIMEOUT_SEC).discover()

        found = False
        for server_info in sharings:
            for sharing in server_info.sharings:
                if sharing == sharing_name:
                    # Found the right sharing
                    found = True
                    logging.debug("Sharing [%s] found at %s:%d", sharing_name, server_info.address, server_info.port)

                    # Send OPEN
                    self.connection = EasyshareConnection(server_info.uri)
                    self.connection.open()


        if not found:
            eprint("Not found")


    def _execute_scan(self, args):
        timeout = Conf.DISCOVER_DEFAULT_TIMEOUT_SEC

        if len(args) > 0:
            timeout = args[0]

        try:
            timeout = float(timeout)
        except:
            eprint(EasyshareShell.INVALID_COMMAND_SYNTAX)
            return

        sharings = EasyshareDiscoverer(timeout).discover()

        # Print sharings
        logging.info("======================")
        for idx, server_info in enumerate(sharings):
            print("{} ({}:{})"
                  .format(server_info.hostname, server_info.address, server_info.port))
            longest_sharing_name = 0

            for sharing_name, sharing_path in server_info.sharings.items():
                longest_sharing_name = max(longest_sharing_name, len(sharing_name))

            for sharing_name, sharing_path in server_info.sharings.items():
                print(("  {}" + (" " * (longest_sharing_name - len(sharing_name))) + "  |  {}")
                      .format(sharing_name, sharing_path))

            if idx < len(sharings) - 1:
                print("")

        logging.info("======================")


    def handle_discover_response(self, client, response):
        try:
            logging.info("Got DISCOVER response from %s: %s", client, response)

            if not response:
                logging.warning("Received unexpected response (null response)")
                return

            response_str = str(response, encoding="UTF-8")
            uri, hostname, port = response_str.split("\n")

            if not uri.startswith("PYRO"):
                logging.warning("Received unexpected response")
                return
        except Exception:
            logging.warning("Received unexpected response")
            return

        server = Pyro4.Proxy(uri)

        logging.trace("Retrieving sharings LIST from server %s(%s)", hostname, uri)
        server_sharings = server.list_sharings()
        logging.debug("Retrieved sharings LIST from server %s(%s)", hostname, uri)

        # if not hostname in self.sharings:
        #     self.sharings[hostname] = {}
        # self.sharings[hostname].update(server_sharings)

        server_info = EasyshareServerInfo()
        server_info.uri = uri
        server_info.hostname = hostname
        server_info.address = client[0]
        server_info.port = port
        server_info.sharings = server_sharings

        self.sharings.append(server_info)


    def handle_discover_finished(self):
        logging.info("DISCOVER finished")

        self.discover_sync.release()

# ========================

class EasyshareShell:
    COMMAND_NOT_RECOGNIZED = "Command not recognized"
    INVALID_COMMAND_SYNTAX = "Invalid command syntax"
    COMMAND_EXECUTION_ERROR = "Command execution error"

    COMMANDS = sorted([v for k, v in Commands.__dict__.items() if not k.startswith("__")])

    def __init__(self):
        self.connection = None
        self.available_commands = []
        self.client = EasyshareClient()

    def setup(self):
        readline.set_completer(self.next_suggestion)
        readline.parse_and_bind("tab: complete")

    def next_suggestion(self, text, state):
        if state == 0:
            self.available_commands = [c for c in EasyshareShell.COMMANDS if c.startswith(text)]
        if len(self.available_commands) > 0:
            return self.available_commands.pop()
        return None

    def input_loop(self):
        command = None
        while command != Commands.EXIT:
            command = input("es> ")
            if not self.client.execute_command(command):
                eprint(EasyshareShell.COMMAND_NOT_RECOGNIZED)

if __name__ == "__main__":
    init_logging(enabled=True, level=LoggingLevels.TRACE)

    if len(sys.argv) <= 1:
        # Start in interactive mode
        shell = EasyshareShell()
        shell.setup()
        shell.input_loop()

    #
    # discover_response_deamon = DiscoverResponseDeamon()
    # discover_response_deamon.start()
    # broadcast_discover()

    #
    # print("DONE")

    # uri = input("URI: ")
    # server = Pyro4.Proxy(uri)
    #
    # print("LIST")
    # print(server.list())