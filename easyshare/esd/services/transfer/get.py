import os
import zlib
from pathlib import Path
from queue import Queue
from typing import List, Tuple, Union, BinaryIO

from Pyro5.server import expose

from easyshare.common import BEST_BUFFER_SIZE
from easyshare.esd.common import Client, Sharing
from easyshare.esd.services import check_sharing_service_owner_endpoint, FPath
from easyshare.esd.services.transfer import TransferService
from easyshare.logging import get_logger
from easyshare.protocol.responses import create_success_response, TransferOutcomes, create_error_response, Response, \
    create_error_of_response, ServerErrors
from easyshare.protocol.services import IGetService
from easyshare.protocol.types import create_file_info
from easyshare.utils.os import os_error_str
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

    def name(self) -> str:
        return "get"

    # TODO - known bugs
    #   1.  client can submit ../sharing_name and see if the transfer works for
    #       figure out the name of folder of the sharing (and eventually the complete path
    #       with consecutive attempts such as ../../something/sharing_name)
    def __init__(self,
                 # files: List[Tuple[str, str]], # local path, remote prefix
                 files: List[str],  # fpath, prefix
                 check: bool,
                 sharing: Sharing,
                 sharing_rcwd: FPath,
                 client: Client):
        super().__init__(sharing, sharing_rcwd, client)
        self._check = check
        self._next_servings: List[Tuple[FPath, FPath, str]] = [] # fpath, basedir, prefix (only for is_root case)
        self._active_servings: Queue[Union[Tuple[FPath, BinaryIO], None]] = Queue() # fpath, fd

        for f in files:

            # "." is equal to "" and means get the rcwd wrapped into a folder
            # "*" means get everything inside the rcwd without wrapping it into a folder
            log.d("f = %s", f)

            p = Path(f)

            take_all_unwrapped = True if (p.parts and p.parts[len(p.parts) - 1]) == "*" else False

            log.d("is * = %s", take_all_unwrapped)

            if take_all_unwrapped:
                # Consider the path without the last *
                p = p.parent

            log.d("p(f) = %s", p)

            # Compute the absolute path depending on the user request (p)
            # and our current rcwd
            fpath = self._fpath_joining_rcwd_and_spath(p)

            is_root = fpath == self._sharing.path
            log.d("is root = %s", is_root)

            # Compute the basedir: the directory from which the user takes
            # the files (this will have effect on the location of the files on
            # the client)
            # If the last component is a *, consider the entire content of the folder (unwrapped)
            # Otherwise the basedir is the parent (so that the folder will be wrapped)

            prefix = ""

            if take_all_unwrapped:
                basedir = fpath
            else:
                if is_root: # don't go outside "."
                    basedir = fpath
                    prefix = self._sharing.name
                else:
                    basedir = fpath.parent

            log.d("fpath(f)         = %s", fpath)
            log.d("basedir(f)  = %s", basedir)
            log.d("prefix = %s", self._sharing.name)

            # Do domain check now, after this check it should not be
            # necessary to check it since we can only go deeper

            if self._is_fpath_allowed(fpath) and self._is_fpath_allowed(basedir):
                self._next_servings.append((fpath, basedir, prefix))
            else:
                log.e("Path %s is invalid (out of sharing domain)", f)
                self._add_error(create_error_of_response(ServerErrors.INVALID_PATH,
                                                         q(f)))

    @expose
    @trace_api
    @check_sharing_service_owner_endpoint
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
            next_fpath, next_basedir, prefix = self._next_servings[len(self._next_servings) - 1]

            log.d("Next file fpath: %s", next_fpath)
            log.d("Next file basedir: %s", next_basedir)

            # Check domain validity
            # Should never fail since we have already checked in __init__
            if not self._is_fpath_allowed(next_fpath) or \
                    not self._is_fpath_allowed(next_basedir):
                log.e("Path is invalid (out of sharing domain)")
                self._next_servings.pop()
                # can't even provide a name since we only have fpath at this point
                self._add_error(create_error_of_response(ServerErrors.INVALID_PATH))
                continue

            log.d("Sharing domain check OK")

            # Compute the path relative to the basedir (depends on the user request)
            # e.g. can be public/f1 or ../public or /path/to/dir ...
            next_spath_str = os.path.join(prefix, next_fpath.relative_to(next_basedir))

            log.d("Next file spath: %s", next_spath_str)

            finfo = create_file_info(
                next_fpath,
                name=next_spath_str
            )



            # Case: FILE
            if finfo and next_fpath.is_file():
                log.i("NEXT FILE: %s", next_fpath)

                # Pop only if transfer or skip is specified
                if transfer or skip:
                    log.d("Popping file out (transfer OR skip specified for FTYPE_FILE)")
                    self._next_servings.pop()
                    if transfer:
                        # Actually put the file on the queue of the files
                        # to be send through the transfer socket

                        # Before doing so, try to open the file for real.
                        # At least we are able to detect any error (e.g. perm denied)
                        # before say the client that the transfer is began
                        # We have to report the error now (create_error_response)
                        # not later (_add_error()) because the user have to
                        # take a decision based on this (skip the file)
                        log.d("Trying to open file before initializing transfer")

                        try:
                            fd = next_fpath.open("rb")
                            log.d("Able to open file: %s", next_fpath)
                        except FileNotFoundError:
                            log.w("Can't open file - not transferring file (file not found error)")
                            return create_error_response(ServerErrors.NOT_EXISTS,
                                                         q(next_spath_str))
                        except PermissionError:
                            log.w("Can't open file - not transferring file (permission error)")
                            return create_error_response(ServerErrors.PERMISSION_DENIED,
                                                         q(next_spath_str))
                        except OSError as oserr:
                            log.w("Can't open file - not transferring file (oserror)")
                            return create_error_response(ServerErrors.ERR_2,
                                                         os_error_str(oserr),
                                                         q(next_spath_str))
                        except Exception as exc:
                            log.w("Can't open file - not transferring file")
                            return create_error_response(ServerErrors.ERR_2,
                                                         exc,
                                                         q(next_spath_str))

                        log.d("Actually adding file to the transfer queue")
                        self._active_servings.put((next_fpath, fd))

                return create_success_response(finfo)

            # Case: DIR
            elif finfo and next_fpath.is_dir():
                # Pop it now; it doesn't make sense ask the user whether
                # skip or overwrite as for files
                self._next_servings.pop()

                # Directory found
                try:
                    dir_files: List[FPath] = list(next_fpath.iterdir())
                except FileNotFoundError:
                    self._add_error(create_error_of_response(ServerErrors.NOT_EXISTS,
                                                             q(next_spath_str)))
                    continue
                except PermissionError:
                    self._add_error(create_error_of_response(ServerErrors.PERMISSION_DENIED,
                                                             q(next_spath_str)))
                    continue
                except OSError as oserr:
                    self._add_error(create_error_of_response(ServerErrors.ERR_2,
                                                             os_error_str(oserr),
                                                             q(next_spath_str)))
                    continue
                except Exception as exc:
                    self._add_error(create_error_of_response(ServerErrors.ERR_2,
                                                             exc,
                                                             q(next_spath_str)))
                    continue


                if dir_files:
                    log.i("Found a filled directory: adding all inner files to remaining_files")
                    for file_in_dir in dir_files:
                        log.i("Adding %s", file_in_dir)
                        self._next_servings.append((file_in_dir, next_basedir, prefix))
                else:
                    log.i("Found an empty directory")
                    log.d("Returning an info for the empty directory")

                    return create_success_response(finfo)
            # Case: UNKNOWN (non-existing/link/special files/...)
            else:
                # Pop it now
                self._next_servings.pop()
                log.w("Not file nor dir? skipping %s", next_fpath)
                self._add_error(create_error_of_response(ServerErrors.TRANSFER_SKIPPED,
                                                         q(next_spath_str)))
                continue

        log.i("No remaining files")
        self._active_servings.put(None)

        # Notify the client about it
        return create_success_response()


    def _run(self):
        while True:
            log.d("Blocking and waiting for a file to handle...")


            next_serving = self._active_servings.get()

            if not next_serving:
                log.i("No more files: transfer completed")
                break

            next_serving_fpath: FPath
            next_serving_f: BinaryIO

            next_serving_fpath, next_serving_f = next_serving

            log.i("Next outgoing file to handle: %s", next_serving_fpath)

            # Report it
            print(f"[{self.client.tag}] get '{next_serving_fpath}'")

            file_len = next_serving_fpath.stat().st_size

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

            # Send file
            while cur_pos < file_len:
                readlen = min(file_len - cur_pos, BEST_BUFFER_SIZE)

                # Read from file
                chunk = next_serving_f.read(readlen)

                if not chunk:
                    # EOF
                    log.i("Finished to handle: %s", next_serving_fpath)
                    break

                log.i("Read chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                if self._check:
                    # Eventually update the CRC
                    crc = zlib.crc32(chunk, crc)

                log.d("%d/%d (%.2f%%)", cur_pos, file_len, cur_pos / file_len * 100)

                self._transfer_sock.send(chunk)

            log.i("Closing file %s", next_serving_fpath)
            next_serving_f.close()

            # Eventually send the CRC in-band
            if self._check:
                log.d("Sending CRC: %d", crc)
                self._transfer_sock.send(int_to_bytes(crc, 4))

        log.i("GET finished")

        self._success()

