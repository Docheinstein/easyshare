import os
import zlib
from typing import Callable

from queue import Queue
from Pyro5.server import expose

from easyshare.common import BEST_BUFFER_SIZE
from easyshare.esd.services import BaseClientService, check_sharing_service_owner

from easyshare.esd.common import ClientContext, Sharing
from easyshare.esd.services.transfer import TransferService
from easyshare.logging import get_logger
from easyshare.protocol.services import OverwritePolicy, IPutService
from easyshare.protocol.responses import TransferOutcomes, create_success_response, ServerErrors, create_error_response, \
    Response
from easyshare.protocol.types import FTYPE_FILE, FTYPE_DIR, FileInfo
from easyshare.utils.pyro.server import pyro_client_endpoint, trace_api, try_or_command_failed_response
from easyshare.utils.types import bytes_to_int

log = get_logger(__name__)


# =============================================
# ================ PUT SERVICE ================
# =============================================


class PutService(IPutService, TransferService):
    """
    Implementation of 'IPutService' interface that will be published with Pyro.
    Handles a single execution of a put command.
    """
    def __init__(self,
                 check: bool,
                 sharing: Sharing,
                 sharing_rcwd,
                 client: ClientContext,
                 end_callback: Callable[[BaseClientService], None]):
        super().__init__(sharing, sharing_rcwd, client, end_callback)
        self._check = check
        self._incomings = Queue()

    @expose
    @trace_api
    @check_sharing_service_owner
    @try_or_command_failed_response
    def next(self,
             finfo: FileInfo,
             overwrite_policy: OverwritePolicy = OverwritePolicy.PROMPT) -> Response:

        if self._outcome:
            log.e("Transfer already closed")
            return create_error_response(TransferOutcomes.TRANSFER_CLOSED)

        client_endpoint = pyro_client_endpoint()

        if not finfo:
            log.i("<< PUT_NEXT DONE [%s]", str(client_endpoint))
            self._incomings.put(None)
            return create_success_response()

        log.i("<< PUT_NEXT [%s]", str(client_endpoint))

        # Check whether is a dir or a file
        fname = finfo.get("name")
        ftype = finfo.get("ftype")
        fsize = finfo.get("size")
        fmtime = finfo.get("mtime")

        real_path = self._real_path_from_rcwd(fname)

        if ftype == FTYPE_DIR:
            log.i("Creating dirs %s", real_path)
            os.makedirs(real_path, exist_ok=True)
            return create_success_response("accepted")

        if ftype == FTYPE_FILE:
            parent_dirs, _ = os.path.split(real_path)
            if parent_dirs:
                log.i("Creating parent dirs %s", parent_dirs)
                os.makedirs(parent_dirs, exist_ok=True)
        else:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        # Check whether it already exists
        if os.path.isfile(real_path):
            log.w("File already exists; deciding what to do based on overwrite policy: %s",
                  overwrite_policy)

            # Take a decision based on the overwrite policy
            if overwrite_policy == OverwritePolicy.PROMPT:
                log.d("Overwrite policy is PROMPT, asking the es whether overwrite")
                return create_success_response("ask_overwrite")

            if overwrite_policy == OverwritePolicy.NEWER:
                log.d("Overwrite policy is NEWER, checking mtime")
                stat = os.lstat(real_path)
                if stat.st_mtime_ns >= fmtime:
                    # Our version is newer, won't accept the file
                    return create_success_response("refused")
                else:
                    log.d("Our version is older, will accept file")

            elif overwrite_policy == OverwritePolicy.YES:
                log.d("Overwrite policy is YES, overwriting it unconditionally")

        self._incomings.put((real_path, fsize))

        return create_success_response("accepted")


    def _run(self):
        while True:
            log.d("Blocking and waiting for a file to handle...")

            # Recv files until the incomings buffer is empty
            # Wait on the blocking queue for the next file to recv
            next_incoming = self._incomings.get()

            if not next_incoming:
                log.i("No more files: transfer completed")
                break

            log.i("Next incoming file to handle: %s", next_incoming)
            incoming_file, incoming_file_len = next_incoming

            f = open(incoming_file, "wb")
            cur_pos = 0
            crc = 0

            # Recv file
            while cur_pos < incoming_file_len:
                readlen = min(incoming_file_len - cur_pos, BEST_BUFFER_SIZE)

                # Read from the remote
                log.d("Waiting a chunk of %dB", readlen)
                chunk = self._transfer_sock.recv(readlen)

                if not chunk:
                    # EOF
                    log.i("Finished to handle: %s", incoming_file)
                    break

                log.d("Received chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                if self._check:
                    # Eventually update the CRC
                    crc = zlib.crc32(chunk, crc)

                f.write(chunk)

                log.d("%d/%d (%.2f%%)", cur_pos, incoming_file_len, cur_pos / incoming_file_len * 100)

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
                if written_size != incoming_file_len:
                    log.e("File length mismatch; transfer failed. expected=%s ; written=%d",
                          incoming_file_len, written_size)
                    self._finish(TransferOutcomes.CHECK_FAILED)
                    break
                else:
                    log.d("File length check: OK")

        log.i("PUT finished")

        self._success()
