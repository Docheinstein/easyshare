import os
import queue
import random
import threading
import time
from typing import List, Callable

from Pyro5.server import expose

from easyshare.logging import get_logger
from easyshare.protocol.exposed import IGetService
from easyshare.protocol.filetype import FTYPE_FILE, FTYPE_DIR
from easyshare.protocol.response import Response, create_success_response
from easyshare.server.client import ClientContext
from easyshare.server.common import try_or_command_failed_response
from easyshare.server.services.base.service import check_service_owner, ClientService

from easyshare.server.services.base.sharingservice import ClientSharingService
from easyshare.server.sharing import Sharing
from easyshare.socket.tcp import SocketTcpAcceptor
from easyshare.ssl import get_ssl_context
from easyshare.utils.pyro import trace_api, pyro_client_endpoint

log = get_logger(__name__)


class GetService(IGetService, ClientSharingService):
    BUFFER_SIZE = 4096

    def __init__(self,
                 files: List[str],
                 sharing: Sharing,
                 sharing_rcwd,
                 client: ClientContext,
                 end_callback: Callable[[ClientService], None]):
        super().__init__(sharing, sharing_rcwd, client, end_callback)
        self._next_servings = files
        self._active_servings = queue.Queue()
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
    def next(self) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i("<< GET_NEXT [%s]", str(client_endpoint))

        while len(self._next_servings) > 0:

            # Get next file (or dir)
            next_file_path = self._next_servings.pop()

            log.i("Next file path: %s", next_file_path)

            # Check domain validity
            if not self._is_real_path_allowed(next_file_path):
                log.e("Path is invalid (out of sharing domain)")
                continue

            if self._sharing.path == next_file_path:
                # Getting (file) sharing
                sharing_path_head, _ = os.path.split(self._sharing.path)
                log.d("sharing_path_head: %s", sharing_path_head)
                trail = self._trailing_path(sharing_path_head, next_file_path)
            else:
                trail = self._trailing_path_from_rcwd(next_file_path)

            log.d("Trail: %s", trail)

            # Case: FILE
            if os.path.isfile(next_file_path):

                log.i("NEXT FILE: %s", next_file_path)

                self._active_servings.put(next_file_path)

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
                        self._next_servings.append(f_path)
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
        self._active_servings.put(None)

        # Notify the client about it
        return create_success_response()


    def _run(self):
        if not self._transfer_acceptor_sock:
            log.e("Socket acceptor invalid")
            return

        log.d("Starting GetService")

        while True:
            log.d("Waiting client connection...")
            transfer_sock, client_endpoint = self._transfer_acceptor_sock.accept()
            self._transfer_acceptor_sock.close()

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

            # Send files until the servings buffer is empty
            # Wait on the blocking queue for the next file to send
            next_serving = self._active_servings.get()

            if not next_serving:
                log.i("No more files: END")
                break

            log.i("Next serving: %s", next_serving)

            f = open(next_serving, "rb")
            cur_pos = 0
            file_len = os.path.getsize(next_serving)

            # Send file
            while cur_pos < file_len:
                r = random.random() * 0.001
                time.sleep(0.001 + r)
                chunk = f.read(GetService.BUFFER_SIZE)
                if not chunk:
                    log.i("Finished %s", next_serving)
                    break

                log.i("Read chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                try:
                    log.d("sending chunk...")
                    transfer_sock.send(chunk)
                    log.d("sending chunk DONE")
                except Exception as ex:
                    log.e("send error %s", ex)
                    # Abort transaction
                    go_ahead = False
                    break

                log.i("%d/%d (%.2f%%)", cur_pos, file_len, cur_pos / file_len * 100)

            log.i("Closing file %s", next_serving)
            f.close()

        log.i("Transaction handler job finished")

        transfer_sock.close()

        self._notify_service_end()

    def abort(self):
        log.i("aborting transaction")
        with self._active_servings.mutex:
            self._active_servings.queue.clear()
            self._active_servings.put(None)