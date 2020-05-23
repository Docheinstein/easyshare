import os
import queue
import zlib
from typing import Callable, List, Tuple, Union

from Pyro5.server import expose

from easyshare.common import BEST_BUFFER_SIZE
from easyshare.esd.common import ClientContext, Sharing
from easyshare.esd.services import BaseClientService, check_sharing_service_owner, FPath, SPath
from easyshare.esd.services.transfer import TransferService
from easyshare.logging import get_logger
from easyshare.protocol.services import IGetService
from easyshare.protocol.responses import create_success_response, TransferOutcomes, create_error_response, Response, \
    create_error_of_response, ServerErrors
from easyshare.protocol.types import FTYPE_DIR, FTYPE_FILE, create_file_info
from easyshare.utils.os import relpath, os_error_str
from easyshare.utils.pyro.server import pyro_client_endpoint, trace_api, try_or_command_failed_response
from easyshare.utils.str import q
from easyshare.utils.types import int_to_bytes

log = get_logger(__name__)


# =============================================
# ================ GET SERVICE ================
# =============================================


class GetService(IGetService, TransferService):
    """
    Implementation of 'IGetService' interface that will be published with Pyro.
    Handles a single execution of a get command.
    """
    def __init__(self,
                 # files: List[Tuple[str, str]], # local path, remote prefix
                 files: List[Tuple[FPath, str]], # fpath, prefix
                 check: bool,
                 sharing: Sharing,
                 sharing_rcwd: FPath,
                 client: ClientContext,
                 end_callback: Callable[[BaseClientService], None]):
        super().__init__(sharing, sharing_rcwd, client, end_callback)
        self._check = check
        self._next_servings: List[Tuple[FPath, str]] = files # fpath, prefix
        self._active_servings: queue.Queue[Union[FPath, None]] = queue.Queue()

    @expose
    @trace_api
    @check_sharing_service_owner
    @try_or_command_failed_response
    def next(self, transfer: bool = False, skip: bool = False) -> Response:
        if self._outcome is not None:
            log.e("Transfer already closed")
            return create_error_response(TransferOutcomes.TRANSFER_CLOSED)

        client_endpoint = pyro_client_endpoint()

        log.i("<< GET_NEXT mode = %s [%s]", str(client_endpoint),
              "transfer" if transfer else ("skip" if skip else "seek"))

        while len(self._next_servings) > 0:
            # Get next file (or dir)
            # Do not pop it now: either transfer os skip must be specified
            # for a regular file before being popped out
            # (In this way we can handle cases in which the client don't
            # want to receive the file (because of overwrite, or anything else)
            next_fpath, prefix = self._next_servings[len(self._next_servings) - 1]
            # next_fpath: FPath = self._fpath_joining_rcwd_and_spath(next_spath)
            next_spath = self._spath_rel_to_rcwd_of_fpath(next_fpath)


            log.i("Next file spath: %s", next_spath)
            log.i("Next file fpath: %s", next_fpath)
            log.d("Prefix: '%s'", prefix)

            # Check domain validity
            if not self._is_fpath_allowed(next_fpath):
                log.e("Path is invalid (out of sharing domain)")
                self._next_servings.pop()
                self._add_error(create_error_of_response(ServerErrors.INVALID_PATH,
                                                         q(next_spath)))
                continue

            # Check whether is a file or a directory sharing
            # if self._sharing.path == next_file_local_path:
            #     # Getting (file) sharing
            #     sharing_path_head, _ = os.path.split(self._sharing.path)
            #     log.d("sharing_path_head: %s", sharing_path_head)
            #     next_file_client_path = self._trailing_path(sharing_path_head, next_file_local_path)
            # else:
            #     trail = self._trailing_path_from_rcwd(next_file_local_path)
            #     log.d("Trail: %s", trail)
            #     # Eventually add a starting prefix (for wrap into a folder)
            #     next_file_client_path = relpath(os.path.join(next_file_client_prefix, trail))
            #
            # log.d("File path for client is: %s", next_file_client_path)

            # Case: FILE
            if next_fpath.is_file():
                log.i("NEXT FILE: %s", next_fpath)

                # Pop only if transfer or skip is specified
                if transfer or skip:
                    log.d("Popping file out (transfer OR skip specified for FTYPE_FILE)")
                    self._next_servings.pop()
                    if transfer:
                        # Actually put the file on the queue of the files
                        # to be send through the transfer socket
                        log.d("Actually adding file to the transfer queue")
                        self._active_servings.put(next_fpath)

                return create_success_response(create_file_info(next_fpath, name=q(next_spath)))
                # stat = os.lstat(next_file_local_path)
                # return create_success_response({
                #     "name": next_file_client_path,
                #     "ftype": FTYPE_FILE,
                #     "size": stat.st_size,
                #     "mtime": stat.st_mtime_ns
                # })

            # Case: DIR
            elif next_fpath.is_dir():
                # Pop it now; it doesn't make sense ask the user whether
                # skip or overwrite as for files
                self._next_servings.pop()

                # Directory found
                try:
                    # os.listdir is all what we want (instead of next_fpath.iterdir or ls())
                    dir_files: List[FPath] = list(next_fpath.iterdir())
                    # dir_files = sorted(os.listdir(str(next_fpath)), reverse=True)
                except FileNotFoundError:
                    self._add_error(create_error_of_response(ServerErrors.NOT_EXISTS,
                                                             q(next_spath)))
                    continue
                except PermissionError:
                    self._add_error(create_error_of_response(ServerErrors.PERMISSION_DENIED,
                                                             q(next_spath)))
                    continue
                except OSError as oserr:
                    self._add_error(create_error_of_response(ServerErrors.ERR_2,
                                                             os_error_str(oserr),
                                                             q(next_spath)))
                    continue
                except Exception as exc:
                    self._add_error(create_error_of_response(ServerErrors.ERR_2,
                                                             exc,
                                                             q(next_spath)))
                    continue


                if dir_files:
                    log.i("Found a filled directory: adding all inner files to remaining_files")
                    for file_in_dir in dir_files:
                        # file_in_dir_fpath = next_fpath.joinpath(file_in_dir)
                        # f_path = os.path.join(next_file_local_path, f)
                        log.i("Adding %s", file_in_dir)
                        self._next_servings.append((file_in_dir, prefix))
                else:
                    log.i("Found an empty directory")
                    log.d("Returning an info for the empty directory")

                    return create_success_response(create_file_info(next_fpath, name=q(next_spath)))
                    # return create_success_response({
                    #     "name": next_file_client_path,
                    #     "ftype": FTYPE_DIR,
                    # })
            # Case: UNKNOWN (non-existing/link/special files/...)
            else:
                # Pop it now
                self._next_servings.pop()
                log.w("Not file nor dir? skipping %s", next_fpath)
                self._add_error(create_error_of_response(ServerErrors.TRANSFER_SKIPPED,
                                                         q(next_spath)))
                continue

        log.i("No remaining files")
        self._active_servings.put(None)

        # Notify the client about it
        return create_success_response()


    def _run(self):
        while True:
            log.d("Blocking and waiting for a file to handle...")

            next_serving: FPath = self._active_servings.get()

            if not next_serving:
                log.i("No more files: transfer completed")
                break

            log.i("Next outgoing file to handle: %s", next_serving)

            # Report it
            print(f"[{self._client.tag}] get '{next_serving}'")

            file_len = next_serving.stat().st_size

            f = next_serving.open("rb")
            cur_pos = 0
            crc = 0

            # Send file
            while cur_pos < file_len:
                readlen = min(file_len - cur_pos, BEST_BUFFER_SIZE)

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
