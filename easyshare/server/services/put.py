import os
import queue
import random
import threading
import time
from typing import Callable

from Pyro5.server import expose

from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.exposed import IPutService
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.filetype import FTYPE_FILE, FTYPE_DIR
from easyshare.protocol.response import Response, create_error_response, create_success_response
from easyshare.server.client import ClientContext
from easyshare.server.common import try_or_command_failed_response
from easyshare.server.services.base.service import check_service_owner, ClientService
from easyshare.server.services.base.sharingservice import ClientSharingService
from easyshare.server.sharing import Sharing
from easyshare.socket.tcp import SocketTcpAcceptor
from easyshare.ssl import get_ssl_context
from easyshare.utils.pyro import trace_api, pyro_client_endpoint

log = get_logger(__name__)

class PutService(IPutService, ClientSharingService):
    BUFFER_SIZE = 4096

    def __init__(self,
                 sharing: Sharing,
                 sharing_rcwd,
                 client: ClientContext,
                 end_callback: Callable[[ClientService], None]):
        super().__init__(sharing, sharing_rcwd, client, end_callback)
        self._incomings = queue.Queue()
        self._transfer_acceptor_sock = SocketTcpAcceptor(ssl_context=get_ssl_context())


    def transfer_port(self) -> int:
        return self._transfer_acceptor_sock.port()

    def run(self):
        th = threading.Thread(target=self._run, daemon=True)
        th.start()

    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def next(self, finfo: FileInfo) -> Response:

        if not finfo:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        if self._sharing.ftype == FTYPE_FILE:
            # Cannot put within a file
            log.e("Cannot put within a file sharing")
            return create_error_response(ServerErrors.NOT_ALLOWED)

        client_endpoint = pyro_client_endpoint()

        log.i("<< PUT_NEXT [%s]", str(client_endpoint))

        # Check whether is a dir or a file
        fname = finfo.get("name")
        ftype = finfo.get("ftype")
        fsize = finfo.get("size")

        real_path = self._real_path_from_rcwd(fname)

        if ftype == FTYPE_DIR:
            log.i("Creating dirs %s", real_path)
            os.makedirs(real_path, exist_ok=True)
            return create_success_response()

        if ftype == FTYPE_FILE:
            parent_dirs, _ = os.path.split(real_path)
            if parent_dirs:
                log.i("Creating parent dirs %s", parent_dirs)
                os.makedirs(parent_dirs, exist_ok=True)
        else:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        # Check whether it already exists
        if os.path.isfile(real_path):
            log.w("File already exists, asking whether overwrite it")
            return create_success_response("ask_overwrite")

        self._incomings.put((real_path, fsize))

        return create_success_response()



    def _run(self):

        if not self._transfer_acceptor_sock:
            log.e("Socket acceptor invalid")
            return

        log.d("Starting PutService")


        while True:
            log.d("Waiting client connection...")
            transfer_sock, client_endpoint = self._transfer_acceptor_sock.accept()

            # Check that the new client endpoint matches the expect one
            if client_endpoint[0] != self._client.endpoint[0]:
                log.e("Unexpected client connected: forbidden")
                transfer_sock.close()
                continue

            log.i("Received connection from valid client %s", client_endpoint)
            break

        go_ahead = True

        while go_ahead:
            log.d("blocking wait on next_servings")

            # Recv files until the servings buffer is empty
            # Wait on the blocking queue for the next file to recv
            next_incoming = self._incomings.get()

            if not next_incoming:
                log.i("No more files: END")
                break

            next_path, next_size = next_incoming

            log.i("Next incoming: %s", next_incoming)

            f = open(next_path, "wb")
            cur_pos = 0
            # file_len = os.path.getsize(next_serving)
            #
            # Recv file
            while cur_pos < next_size:
                r = random.random() * 0.001
                time.sleep(0.001 + r)

                chunk = transfer_sock.recv(PutService.BUFFER_SIZE)

                # chunk = f.read(PutTransactionHandler.BUFFER_SIZE)

                if not chunk:
                    log.i("Finished %s", next_path)
                    break

                log.i("Read chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                f.write(chunk)

                log.i("%d/%d (%.2f%%)", cur_pos, next_size, cur_pos / next_size * 100)

            log.i("Closing file %s", next_path)
            f.close()

        log.i("Transaction handler job finished")

        transfer_sock.close()
        self._transfer_acceptor_sock.close()

        self._notify_service_end()

    def abort(self):
        log.i("aborting transaction")
        with self._incomings.mutex:
            self._incomings.queue.clear()
            self._incomings.put(None)