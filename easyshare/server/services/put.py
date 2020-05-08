import os
import queue
import threading
import zlib
from typing import Callable

from Pyro5.server import expose

from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors, TransferOutcomes
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
from easyshare.utils.types import bytes_to_int

log = get_logger(__name__)

class PutService(IPutService, ClientSharingService):
    BUFFER_SIZE = 4096

    def __init__(self,
                 check: bool,
                 port: int,
                 sharing: Sharing,
                 sharing_rcwd,
                 client: ClientContext,
                 end_callback: Callable[[ClientService], None]):
        super().__init__(sharing, sharing_rcwd, client, end_callback)
        self._check = check
        self._incomings = queue.Queue()
        self._transfer_acceptor_sock = SocketTcpAcceptor(
            port=port,
            ssl_context=get_ssl_context()
        )
        self._transfer_sock = None
        self._outcome_sync = threading.Semaphore(0)
        self._outcome = None

    def run(self):
        th = threading.Thread(target=self._run, daemon=True)
        th.start()

    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def outcome(self) -> Response:
        log.d("Waiting for completion for outcome...")

        self._outcome_sync.acquire()
        outcome = self._outcome
        self._outcome_sync.release()

        log.i("Transaction outcome: %d", outcome)

        self._notify_service_end()

        return create_success_response(outcome)


    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def next(self, finfo: FileInfo, force: bool = False) -> Response:
        client_endpoint = pyro_client_endpoint()

        if not self._transfer_acceptor_sock and not self._transfer_sock:
            return create_error_response(ServerErrors.NOT_CONNECTED)

        if not finfo:
            log.i("<< PUT_NEXT DONE [%s]", str(client_endpoint))
            self._incomings.put(None)
            return create_success_response()

        if self._sharing.ftype == FTYPE_FILE:
            # Cannot put within a file
            log.e("Cannot put within a file sharing")
            return create_error_response(ServerErrors.NOT_ALLOWED)


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
            if not force:
                log.w("File already exists, asking whether overwrite it")
                return create_success_response("ask_overwrite")
            else:
                log.d("File already exists but overwriting it since force=True")


        self._incomings.put((real_path, fsize))

        return create_success_response()



    def _run(self):
        if not self._transfer_acceptor_sock:
            log.e("Socket acceptor invalid")
            self._finish(TransferOutcomes.ERROR)
            return

        log.d("Starting PutService")

        self._wait_connection()

        if not self._transfer_sock:
            self._finish(TransferOutcomes.ERROR)
            return

        go_ahead = True

        while go_ahead:
            log.d(" blocking wait on next_servings")

            # Recv files until the servings buffer is empty
            # Wait on the blocking queue for the next file to recv
            next_incoming = self._incomings.get()

            if not next_incoming:
                log.i("No more files: END")
                break

            incoming_file, incoming_size = next_incoming

            log.i("Next incoming: %s", next_incoming)

            f = open(incoming_file, "wb")
            cur_pos = 0
            crc = 0

            # Recv file
            while cur_pos < incoming_size:
                readlen = min(incoming_size - cur_pos, PutService.BUFFER_SIZE)

                chunk = self._transfer_sock.recv(readlen)

                if self._check:
                    crc = zlib.crc32(chunk, crc)

                if not chunk:
                    # EOF
                    log.i("Finished %s", incoming_file)
                    break

                log.i("Read chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                f.write(chunk)

                log.i("%d/%d (%.2f%%)", cur_pos, incoming_size, cur_pos / incoming_size * 100)

            log.i("Closing file %s", incoming_file)

            f.close()

            # Eventually do CRC check
            if self._check:
                # CRC check on the received bytes
                expected_crc = bytes_to_int(self._transfer_sock.recv(4))
                if expected_crc != crc:
                    log.e("Wrong CRC; transfer failed. expected=%d | written=%d",
                          expected_crc, crc)
                    self._finish(TransferOutcomes.CHECK_FAILED)
                    break
                else:
                    log.d("CRC check: OK")

                # Length check on the written file
                written_size = os.path.getsize(incoming_file)
                if written_size != incoming_size:
                    log.e("File length mismatch expected=%s ; written=%d", incoming_size, written_size)
                    self._finish(TransferOutcomes.CHECK_FAILED)
                    break
                else:
                    log.d("File length check: OK")


        log.i("Transaction handler job finished")
        self._transfer_sock.close()

        self._finish(0)


        # DO not self._notify_service_end()
        # wait for outcome() call before unregister from the daemon

    def _wait_connection(self):
        while True:
            log.d("Waiting client connection...")
            transfer_sock, client_endpoint = self._transfer_acceptor_sock.accept(5)

            if transfer_sock:
                # Check that the new client endpoint matches the expect one
                if client_endpoint[0] == self._client.endpoint[0]:
                    log.i("Received connection from valid client %s", client_endpoint)
                    self._transfer_sock = transfer_sock
                    break
                else:
                    log.e("Unexpected client connected: forbidden")
                    transfer_sock.close()
                    continue
            else:
                log.w("No connection received; closing service")
                break

        # Close the acceptor anyway
        self._transfer_acceptor_sock.close()
        self._transfer_acceptor_sock = None

    def _finish(self, outcome):
        self._outcome = outcome
        self._outcome_sync.release()

    # def abort(self):
    #     log.i("aborting transaction")
    #     with self._incomings.mutex:
    #         self._incomings.queue.clear()
    #         self._incomings.put(None)