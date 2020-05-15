import os
import queue
import zlib
from typing import Callable, List, Tuple

from Pyro5.server import expose

from easyshare.esd.common import ClientContext, Sharing
from easyshare.esd.services import BaseClientService, check_service_owner
from easyshare.esd.services.transfer import TransferService
from easyshare.logging import get_logger
from easyshare.protocol import create_error_response, Response, create_success_response, \
    TransferOutcomes, FTYPE_FILE, FTYPE_DIR, IGetService
from easyshare.utils.os import relpath
from easyshare.utils.pyro.server import pyro_client_endpoint, trace_api, try_or_command_failed_response
from easyshare.utils.types import int_to_bytes

log = get_logger(__name__)


# =============================================
# ================ GET SERVICE ================
# =============================================


class GetService(IGetService, TransferService):
    def __init__(self,
                 files: List[Tuple[str, str]], # local path, remote prefix
                 check: bool,
                 port: int,
                 sharing: Sharing,
                 sharing_rcwd,
                 client: ClientContext,
                 end_callback: Callable[[BaseClientService], None]):
        super().__init__(port, sharing, sharing_rcwd, client, end_callback)
        self._check = check
        self._next_servings = files
        self._active_servings = queue.Queue()

    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def next(self, transfer: bool = False, skip: bool = False) -> Response:
        if self._outcome:
            log.e("Transfer already closed")
            return create_error_response(TransferOutcomes.TRANSFER_CLOSED)

        client_endpoint = pyro_client_endpoint()

        log.i("<< GET_NEXT mode = %s [%s]", str(client_endpoint),
              "transfer" if transfer else ("skip" if skip else "seek"))

        while len(self._next_servings) > 0:
            # Get next file (or dir)
            # Do not pop it now: either transfer os skip must be specified
            # for a regular file before being popped out
            # (In this way we can handle cases in which the es don't
            # want to receive the file (because of overwrite, or anything else)
            next_file = self._next_servings[len(self._next_servings) - 1]

            next_file_local_path, next_file_client_prefix = next_file[0], next_file[1]

            next_file_client_prefix = next_file_client_prefix or ""

            log.i("Next file local path:          %s", next_file_local_path)
            log.i("Next file es prefix: %s", next_file_client_prefix)

            # Check domain validity
            if not self._is_real_path_allowed(next_file_local_path):
                log.e("Path is invalid (out of sharing domain)")
                self._next_servings.pop()
                continue

            if self._sharing.path == next_file_local_path:
                # Getting (file) sharing
                sharing_path_head, _ = os.path.split(self._sharing.path)
                log.d("sharing_path_head: %s", sharing_path_head)
                next_file_client_path = self._trailing_path(sharing_path_head, next_file_local_path)
            else:
                trail = self._trailing_path_from_rcwd(next_file_local_path)
                log.d("Trail: %s", trail)
                # Eventually add a starting prefix (for wrap into a folder)
                next_file_client_path = relpath(os.path.join(next_file_client_prefix, trail))

            log.d("File path for es is: %s", next_file_client_path)

            # Case: FILE
            if os.path.isfile(next_file_local_path):
                log.i("NEXT FILE: %s", next_file_local_path)

                # Pop only if transfer or skip is specified
                if transfer or skip:
                    log.d("Popping file out (transfer OR skip specified for FTYPE_FILE)")
                    self._next_servings.pop()
                    if transfer:
                        # Actually put the file on the queue of the files
                        # to be send through the transfer socket
                        log.d("Actually adding file to the transfer queue")
                        self._active_servings.put(next_file_local_path)

                stat = os.lstat(next_file_local_path)
                return create_success_response({
                    "name": next_file_client_path,
                    "ftype": FTYPE_FILE,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime_ns
                })

            # Case: DIR
            elif os.path.isdir(next_file_local_path):
                # Pop it now
                self._next_servings.pop()

                # Directory found
                dir_files = sorted(os.listdir(next_file_local_path), reverse=True)

                if dir_files:

                    log.i("Found a filled directory: adding all inner files to remaining_files")
                    for f in dir_files:
                        f_path = os.path.join(next_file_local_path, f)
                        log.i("Adding %s", f_path)
                        self._next_servings.append((f_path, next_file_client_prefix))
                else:
                    log.i("Found an empty directory")
                    log.d("Returning an info for the empty directory")

                    return create_success_response({
                        "name": next_file_client_path,
                        "ftype": FTYPE_DIR,
                    })
            # Case: UNKNOWN (non-existing/link/special files/...)
            else:
                # Pop it now
                self._next_servings.pop()
                log.w("Not file nor dir? skipping %s", next_file_local_path)

        log.i("No remaining files")
        self._active_servings.put(None)

        # Notify the es about it
        return create_success_response()


    def _run(self):
        while True:
            log.d("Blocking and waiting for a file to handle...")

            # Send
            # # =============================================
            # # ============= TRANSFER SERVICE ==============
            # # =============================================
            #
            # class TransferService(ITransferService, BaseClientSharingService, ABC):
            #
            #     # Close the connection on the transfer port if none connects within this timeout
            #     TRANSFER_ACCEPT_CONNECTION_TIMEOUT = 10
            #
            #     BUFFER_SIZE = 4096
            #
            #     def __init__(self,
            #                  port: int,
            #                  sharing: Sharing,
            #                  sharing_rcwd,
            #                  client: ClientContext,
            #                  end_callback: Callable[[BaseClientService], None]):
            #         super().__init__(sharing, sharing_rcwd, client, end_callback)
            #         get_transfer_daemon().add_callback(self._handle_new_connection)
            #         self._outcome_sync = threading.Semaphore(0)
            #         self._outcome = None
            #
            #     @expose
            #     @trace_api
            #     @check_service_owner
            #     @try_or_command_failed_response
            #     def outcome(self) -> Response:
            #         log.d("Blocking and waiting for outcome...")
            #
            #         self._outcome_sync.acquire()
            #         outcome = self._outcome
            #         self._outcome_sync.release()
            #
            #         log.i("Transfer outcome: %d", outcome)
            #
            #         self._notify_service_end()
            #
            #         return create_success_response(outcome)
            #
            #     def run(self):
            #         th = threading.Thread(target=self._accept_connection_and_run, daemon=True)
            #         th.start()
            #
            #     def _handle_new_connection(self, sock: SocketTcpIn):
            #         if not sock:
            #             self._finish(TransferOutcomes.CONNECTION_ESTABLISHMENT_ERROR)
            #             return
            #
            #
            #         if sock.remote_endpoint()[0] != self._client.endpoint[0]:
            #             log.e("Unexpected es connected: forbidden")
            #             return False
            #
            #         log.i("Received connection from valid es %s", sock.remote_endpoint())
            #         self._transfer_sock = sock
            #
            #         # Finally execute the transfer logic
            #         self._run()
            #
            #
            #     def _success(self):
            #         self._finish(0)
            #
            #     def _finish(self, outcome):
            #         self._outcome = outcome
            #         self._outcome_sync.release()files until the servings buffer is empty
            # Wait on the blocking queue for the next file to send
            next_serving = self._active_servings.get()

            if not next_serving:
                log.i("No more files: transfer completed")
                break

            log.i("Next outgoing file to handle: %s", next_serving)
            file_len = os.path.getsize(next_serving)

            f = open(next_serving, "rb")
            cur_pos = 0
            crc = 0

            # Send file
            while cur_pos < file_len:
                readlen = min(file_len - cur_pos, TransferService.BUFFER_SIZE)

                # Read from file
                chunk = f.read(readlen)

                if not chunk:
                    # EOF
                    log.i("Finished to handle: %s", next_serving)
                    break

                log.i("Read chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                if self._check:
                    # Eventually update the CRC
                    crc = zlib.crc32(chunk, crc)

                log.d("%d/%d (%.2f%%)", cur_pos, file_len, cur_pos / file_len * 100)

                self._transfer_sock.send(chunk)

            log.i("Closing file %s", next_serving)
            f.close()

            # Eventually send the CRC in-band
            if self._check:
                log.d("Sending CRC: %d", crc)
                self._transfer_sock.send(int_to_bytes(crc, 4))

        log.i("GET finished")

        self._success()
