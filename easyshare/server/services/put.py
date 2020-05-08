import os
import queue
import zlib
from typing import Callable

from Pyro5.server import expose

from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors, TransferOutcomes
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.filetype import FTYPE_FILE, FTYPE_DIR
from easyshare.protocol.response import Response, create_error_response, create_success_response
from easyshare.server.client import ClientContext
from easyshare.server.common import try_or_command_failed_response
from easyshare.server.services.base.service import check_service_owner, ClientService
from easyshare.server.services.base.transfer import TransferService
from easyshare.server.sharing import Sharing
from easyshare.utils.pyro import trace_api, pyro_client_endpoint
from easyshare.utils.types import bytes_to_int

log = get_logger(__name__)

class PutService(TransferService):
    def __init__(self,
                 check: bool,
                 port: int,
                 sharing: Sharing,
                 sharing_rcwd,
                 client: ClientContext,
                 end_callback: Callable[[ClientService], None]):
        super().__init__(port, sharing, sharing_rcwd, client, end_callback)
        self._check = check
        self._incomings = queue.Queue()

    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def next(self, finfo: FileInfo, force: bool = False) -> Response:
        client_endpoint = pyro_client_endpoint()

        if self._outcome:
            log.e("Transfer already closed")
            return create_error_response(TransferOutcomes.TRANSFER_CLOSED)

        if not finfo:
            log.i("<< PUT_NEXT DONE [%s]", str(client_endpoint))
            self._incomings.put(None)
            return create_success_response()

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
        while True:
            log.d("Blocking and waiting for a file to handle...")

            # Recv files until the incomings buffer is empty
            # Wait on the blocking queue for the next file to recv
            next_incoming = self._incomings.get()

            if not next_incoming:
                log.i("No more files: transfer completed")
                break

            incoming_file, incoming_size = next_incoming

            log.i("Next incoming file to handle: %s", next_incoming)

            f = open(incoming_file, "wb")

            cur_pos = 0
            crc = 0

            # Recv file
            while cur_pos < incoming_size:
                readlen = min(incoming_size - cur_pos, PutService.BUFFER_SIZE)

                chunk = self._transfer_sock.recv(readlen)

                if self._check:
                    # Eventually update the CRC
                    crc = zlib.crc32(chunk, crc)

                if not chunk:
                    # EOF
                    log.i("Finished to handle: %s", incoming_file)
                    break

                log.d("Received chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                f.write(chunk)

                log.d("%d/%d (%.2f%%)", cur_pos, incoming_size, cur_pos / incoming_size * 100)

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
                    log.e("File length mismatch; transfer failed. expected=%s ; written=%d",
                          incoming_size, written_size)
                    self._finish(TransferOutcomes.CHECK_FAILED)
                    break
                else:
                    log.d("File length check: OK")

        log.i("Transaction handler job finished")

        self._success()