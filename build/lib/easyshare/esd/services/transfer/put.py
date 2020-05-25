import zlib
from typing import Callable, Tuple, BinaryIO

from queue import Queue
from Pyro5.server import expose

from easyshare.common import BEST_BUFFER_SIZE
from easyshare.esd.services import BaseClientService, check_sharing_service_owner, FPath

from easyshare.esd.common import ClientContext, Sharing
from easyshare.esd.services.transfer import TransferService
from easyshare.logging import get_logger
from easyshare.protocol.services import OverwritePolicy, IPutService
from easyshare.protocol.responses import TransferOutcomes, create_success_response, ServerErrors, create_error_response, \
    Response
from easyshare.protocol.types import FTYPE_FILE, FTYPE_DIR, FileInfo, PutNextResponse
from easyshare.utils.json import j
from easyshare.utils.os import os_error_str
from easyshare.utils.pyro.server import pyro_client_endpoint, trace_api, try_or_command_failed_response
from easyshare.utils.str import q
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

    def name(self) -> str:
        return "put"

    # TODO - known bugs
    #   1.  client can submit ../sharing_name and see if the transfer works for
    #       figure out the name of folder of the sharing (and eventually the complete path
    #       with consecutive attempts such as ../../something/sharing_name)
    def __init__(self,
                 check: bool,
                 sharing: Sharing,
                 sharing_rcwd,
                 client: ClientContext):
        super().__init__(sharing, sharing_rcwd, client)
        self._check = check
        self._incomings: Queue[Tuple[FPath, int, BinaryIO]] = Queue() # fpath, size, fd

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

        log.i("<< PUT_NEXT %s [%s]", j(finfo), str(client_endpoint))

        # Check whether is a dir or a file
        fname = finfo.get("name")
        ftype = finfo.get("ftype")
        fsize = finfo.get("size")
        fmtime = finfo.get("mtime")

        # real_path = self._real_path_from_rcwd(fname)
        fpath = self._fpath_joining_rcwd_and_spath(fname)

        if not self._is_fpath_allowed(fpath):
            log.e("Path %s is invalid (out of sharing domain)", fpath)
            return create_error_response(ServerErrors.INVALID_PATH, q(fname))

        log.d("Sharing domain check OK")

        if ftype == FTYPE_DIR:
            log.i("Creating dirs %s", fpath)
            fpath.mkdir(parents=True, exist_ok=True)
            return create_success_response(PutNextResponse.ACCEPTED)

        if not ftype == FTYPE_FILE: # wtf
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        if ftype == FTYPE_FILE:
            fpath_parent = fpath.parent
            if fpath_parent:
                log.i("Creating parent dirs %s", fpath_parent)
                fpath_parent.mkdir(parents=True, exist_ok=True)

        # Check whether it already exists
        if fpath.is_file():
            log.w("File already exists; deciding what to do based on overwrite policy: %s",
                  overwrite_policy)

            # Take a decision based on the overwrite policy
            if overwrite_policy == OverwritePolicy.PROMPT:
                log.d("Overwrite policy is PROMPT, asking the client whether overwrite")
                return create_success_response(PutNextResponse.ASK_OVERWRITE)

            if overwrite_policy == OverwritePolicy.NEWER:
                log.d("Overwrite policy is NEWER, checking mtime")
                stat = fpath.stat()
                if stat.st_mtime_ns >= fmtime:
                    # Our version is newer, won't accept the file
                    return create_success_response(PutNextResponse.REFUSED)
                else:
                    log.d("Our version is older, will accept file")

            elif overwrite_policy == OverwritePolicy.YES:
                log.d("Overwrite policy is YES, overwriting it unconditionally")

        # Before accept it for real, try to open the file.
        # At least we are able to detect any error (e.g. perm denied)
        # before say the the that the transfer is began.
        log.d("Trying to open file before initializing transfer")

        try:
            local_fd = fpath.open("wb")
            log.d("Able to open file: %s", fpath)
        except FileNotFoundError:
            return create_error_response(ServerErrors.NOT_EXISTS, q(fname))
        except PermissionError:
            return create_error_response(ServerErrors.PERMISSION_DENIED, q(fname))
        except OSError as oserr:
            return create_error_response(ServerErrors.ERR_2,
                                         os_error_str(oserr),
                                         q(fname))
        except Exception as exc:
            return create_error_response(ServerErrors.ERR_2,
                                         exc,
                                         q(fname))

        self._incomings.put((fpath, fsize, local_fd))

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

            incoming_fpath, incoming_size, local_fd = next_incoming
            log.i("Next incoming file to handle: %s", incoming_fpath)

            # Report it
            print(f"[{self.client.tag}] put '{incoming_fpath}'")

            # File is already opened

            # TODO:
            #  if something about IO goes wrong all the transfer is compromised
            #  since we can't tell the user about it.
            #  Open is already done so there should be no permissions problems
            # The solution is to notify the client on the pyro channel, but this
            # implies that the client use an async mechanism for get (while for
            # now is synchronous)

            cur_pos = 0
            crc = 0

            # Recv file
            while cur_pos < incoming_size:
                readlen = min(incoming_size - cur_pos, BEST_BUFFER_SIZE)

                # Read from the remote
                log.d("Waiting a chunk of %dB", readlen)
                chunk = self._transfer_sock.recv(readlen)

                if not chunk:
                    # EOF
                    log.i("Finished to handle: %s", incoming_fpath)
                    break

                log.d("Received chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                if self._check:
                    # Eventually update the CRC
                    crc = zlib.crc32(chunk, crc)

                local_fd.write(chunk)

                log.d("%d/%d (%.2f%%)", cur_pos, incoming_size, cur_pos / incoming_size * 100)

            log.i("Closing file %s", incoming_fpath)
            local_fd.close()

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
                written_size = incoming_fpath.stat().st_size
                if written_size != incoming_size:
                    log.e("File length mismatch; transfer failed. expected=%s ; written=%d",
                          incoming_size, written_size)
                    self._finish(TransferOutcomes.CHECK_FAILED)
                    break
                else:
                    log.d("File length check: OK")

        log.i("PUT finished")

        self._success()
