import os
import queue
import socket
import subprocess
import threading
import zlib
from abc import ABC
from typing import Callable, Optional, Union, List, Tuple

from Pyro5.server import expose

from easyshare.common import transfer_port
from easyshare.consts.os import STDOUT, STDERR

from easyshare.esd.common import ClientContext, Sharing
from easyshare.esd.daemons import get_pyro_daemon, get_transfer_daemon
from easyshare.logging import get_logger
from easyshare.protocol import create_error_response, ServerErrors, ITransferService, Response, create_success_response, \
    TransferOutcomes, IRexecService, ISharingService, FTYPE_FILE, IGetService, FTYPE_DIR, OverwritePolicy, FileInfo, \
    IPutService
from easyshare.sockets import SocketTcpIn
from easyshare.utils.json import j
from easyshare.utils.os import is_relpath, relpath, run_detached, rm, mv, cp, tree, ls
from easyshare.utils.pyro.server import pyro_client_endpoint, trace_api, try_or_command_failed_response
from easyshare.utils.str import unprefix
from easyshare.utils.types import is_int, is_str, is_list, is_bool, int_to_bytes, bytes_to_int

log = get_logger(__name__)

# =============================================
# ============ BASE CLIENT SERVICE ============
# =============================================

class BaseClientService:
    def __init__(self, client: ClientContext,
                 end_callback: Callable[['BaseClientService'], None]):
        self.service_uri = None
        # self.service_uid = "esd_" + uuid()
        self.service_uid = None
        self.published = False

        self._client = client
        self._end_callback = end_callback

        self._lock = threading.Lock()


    def publish(self) -> str:
        with self._lock:
            self.service_uri, self.service_uid = \
                get_pyro_daemon().publish(self, uid=self.service_uid)
            self.published = True
            self._client.add_service(self.service_uid)
            return self.service_uid

    def unpublish(self):
        with self._lock:
            if self.is_published():
                get_pyro_daemon().unpublish(self.service_uid)
                self.published = False
                self._client.remove_service(self.service_uid)


    def is_published(self) -> bool:
        return self.published

    def _notify_service_end(self):
        if self._end_callback:
            self._end_callback(self)

    def _is_request_allowed(self):
        # Check whether the es that tries to access this publication
        # has the same IP of the original es the first time it access
        # and has the same IP and PORT for the rest of the time
        # log.d("Checking publication owner (original_owner: %s | current_owner: %s)", self._client, self._real_client_endpoint)
        #
        # current_client_endpoint = pyro_client_endpoint()
        #
        # if not self._real_client_endpoint:
        #     # First request: the port could be different from the original
        #     # one but the es IP must remain the same
        #     allowed = self._client.endpoint[0] == current_client_endpoint[0]
        #     log.d("First request, allowed: %s", allowed)
        #     if allowed:
        #         self._real_client_endpoint = current_client_endpoint
        #     return allowed
        #
        # # Not the first request: both IP and port must match
        # log.d("Further request, allowed: %s", self._real_client_endpoint == current_client_endpoint)
        # allowed = self._real_client_endpoint == current_client_endpoint
        # if not allowed:
        #     log.w("Not allowed since %s != %s", self._real_client_endpoint, current_client_endpoint)
        # return allowed
        current_client_endpoint = pyro_client_endpoint()
        allowed = self._client.endpoint[0] == current_client_endpoint[0]

        if allowed:
            log.d("Service owner check OK")
        else:
            log.w("Not allowed, address mismatch between %s and %s", current_client_endpoint, self._client.endpoint)
        return allowed


# decorator
def check_service_owner(api):
    def check_service_owner_wrapper(client_service: BaseClientService, *vargs, **kwargs):
        if not client_service._is_request_allowed():
            return create_error_response(ServerErrors.NOT_ALLOWED)
        return api(client_service, *vargs, **kwargs)
    check_service_owner_wrapper.__name__ = api.__name__
    return check_service_owner_wrapper




# =============================================
# ========= BASE CLIENT SHARING SERVICE =======
# =============================================



class BaseClientSharingService(BaseClientService):
    def __init__(self,
                 sharing: Sharing,
                 sharing_rcwd: str,
                 client: ClientContext,
                 end_callback: Callable[['BaseClientService'], None]):
        super().__init__(client, end_callback)
        self._sharing = sharing
        self._rcwd = sharing_rcwd


    def _current_real_path(self):
        return self._real_path_from_rcwd("")

    def _real_path_from_rcwd(self, path: str) -> Optional[str]:
        """
        Returns the path of the location composed by the 'path' of the
        sharing the es is currently on and the 'path' itself.
        The method allows:
            * 'path' starting with a leading / (absolute w.r.t the sharing path)
            * 'path' not starting with a leading / (relative w.r.t the rpwd)

        e.g.
            (ABSOLUTE)
            es sharing path =  /home/stefano/Applications
            es rpwd =                                     InsideAFolder
            path                =  /AnApp
                                => /home/stefano/Applications/AnApp

            (RELATIVE)
            es sharing path =  /home/stefano/Applications
            es rpwd =                                     InsideAFolder
            path                =  AnApp
                                => /home/stefano/Applications/InsideAFolder/AnApp

        """

        if is_relpath(path):
            # It refers to a subdirectory starting from the es's current directory
            path = os.path.join(self._rcwd, path)

        # Take the trail part (without leading /)
        trail = relpath(path)

        return os.path.normpath(os.path.join(self._sharing.path, trail))


    def _trailing_path_from_rcwd(self, path: str) -> Optional[str]:
        """
        Returns the trailing part of the 'path' by stripping the path of the
        sharing from the string's beginning.
        The path is relative w.r.t the rpwd of the sharing path the es
        is currently on.
        e.g.
            es sharing path = /home/stefano/Applications
            es rpwd         =                            AnApp
            (es path        = /home/stefano/Applications/AnApp          )
            path                = /home/stefano/Applications/AnApp/afile.mp4
                                =>                                 afile.mp4
        """
        return self._trailing_path(self._current_real_path(), path)


    def _is_real_path_allowed(self, path: str) -> bool:
        """
        Returns whether the given path is legal for the given es, based
        on the its sharing and rpwd.

        e.g. ALLOWED
            es sharing path = /home/stefano/Applications
            es rpwd         =                            AnApp
            path                = /home/stefano/Applications/AnApp/AFile.mp4

        e.g. NOT ALLOWED
            es sharing path = /home/stefano/Applications
            es rpwd         =                            AnApp
            path                = /home/stefano/Applications/AnotherApp/AFile.mp4

            es sharing path = /home/stefano/Applications
            es rpwd         =                           AnApp
            path                = /tmp/afile.mp4

        :param path: the path to check
        :param es: the es
        :return: whether the path is allowed for the es
        """
        normalized_path = os.path.normpath(path)

        try:
            common_path = os.path.commonpath([normalized_path, self._sharing.path])
            log.d("Common path between '%s' and '%s' = '%s'",
                  normalized_path, self._sharing.path, common_path)

            return self._sharing.path == common_path
        except:
            return False

    def _trailing_path(self, prefix: str, full: str) -> Optional[str]:
        """
        Returns the trailing part of the path 'full' by stripping the path 'prefix'.
        The path is relative w.r.t the root of the sharing path.
        e.g.
            prefix                = /home/stefano/Applications
            full                  = /home/stefano/Applications/AnApp/afile.mp4
                                  =>                           AnApp/afile.mp4
        """

        if not full or not prefix:
            return None

        if not full.startswith(prefix):
            return None

        return relpath(unprefix(full, prefix))

    def _trailing_path_from_root(self, path: str) -> Optional[str]:
        """
        Returns the trailing part of the 'path' by stripping the path of the
        sharing from the string's beginning.
        The path is relative w.r.t the root of the sharing path.
        e.g.
            sharing path        = /home/stefano/Applications
            path                = /home/stefano/Applications/AnApp/afile.mp4
                                =>                           AnApp/afile.mp4
        """
        return self._trailing_path(self._sharing.path, path)


    def _create_sharing_error_response(self, err: Union[int, str]):
        if is_int(err):
            return create_error_response(err)

        if is_str(err):
            safe_err = err.replace(self._sharing.path, "")
            return create_error_response(safe_err)

        return create_error_response()

# =============================================
# ============== REXEC SERVICE ==============
# =============================================


class RexecService(IRexecService, BaseClientService):
    class BlockingBuffer:
        def __init__(self):
            self._buffer = []
            self._sync = threading.Semaphore(0)
            self._lock = threading.Lock()

        def pull(self) -> List:
            ret = []

            self._sync.acquire()
            self._lock.acquire()

            while self._buffer:
                val = self._buffer.pop(0)
                log.d("[-] %s", val)
                ret.append(val)

            self._lock.release()

            return ret

        def push(self, val):
            self._lock.acquire()

            log.d("[+] %s", val)
            self._buffer.append(val)

            self._sync.release()
            self._lock.release()

    def __init__(self, cmd: str, *,
                 client: ClientContext,
                 end_callback: Callable[[BaseClientService], None]):
        super().__init__(client, end_callback)
        self._cmd = cmd
        self._buffer = RexecService.BlockingBuffer()
        self.proc: Optional[subprocess.Popen] = None
        self.proc_handler: Optional[threading.Thread] = None

    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def recv(self) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i(">> REXEC RECV [%s]", client_endpoint)

        buf = None
        while not buf:  # avoid spurious wake ups
            buf = self._buffer.pull()

        stdout = []
        stderr = []
        retcode = None

        for v in buf:
            if is_int(v):
                retcode = v
            elif len(v) == 2:
                if v[1] == STDOUT:
                    stdout.append(v[0])
                elif v[1] == STDERR:
                    stderr.append(v[0])

        data = {
            "stdout": stdout,
            "stderr": stderr,
        }

        if retcode is not None:
            # Command finished, notify the remote and close the service
            data["retcode"] = retcode

            self._notify_service_end()

        return create_success_response(data)

    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def send_data(self, data: str) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i(">> REXEC SEND (%s) [%s]", data, client_endpoint)

        if not data:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        self.proc.stdin.write(data)
        self.proc.stdin.flush()

        return create_success_response()

    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def send_event(self, ev: int) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i(">> REXEC SEND EVENT (%d) [%s]", ev, client_endpoint)

        if ev == IRexecService.Event.TERMINATE:
            log.d("Sending SIGTERM")
            self.proc.terminate()
        elif ev == IRexecService.Event.EOF:
            log.d("Sending EOF")
            self.proc.stdin.close()
        else:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        return create_success_response()

    def run(self):
        self.proc, self.proc_handler = run_detached(
            self._cmd,
            stdout_hook=self._stdout_hook,
            stderr_hook=self._stderr_hook,
            end_hook=self._end_hook
        )
        return self.proc, self.proc_handler

    def _stdout_hook(self, line):
        log.d("> %s", line)
        self._buffer.push((line, STDOUT))

    def _stderr_hook(self, line):
        log.w("> %s", line)
        self._buffer.push((line, STDERR))

    def _end_hook(self, retcode):
        log.d("END %d", retcode)
        self._buffer.push(retcode)


# =============================================
# ============= TRANSFER SERVICE ==============
# =============================================

class TransferService(ITransferService, BaseClientSharingService, ABC):

    # Close the connection on the transfer port if none connects within this timeout
    TRANSFER_ACCEPT_CONNECTION_TIMEOUT = 10

    BUFFER_SIZE = 4096

    def __init__(self,
                 port: int,
                 sharing: Sharing,
                 sharing_rcwd,
                 client: ClientContext,
                 end_callback: Callable[[BaseClientService], None]):
        super().__init__(sharing, sharing_rcwd, client, end_callback)
        log.d("Creating a transfer service")
        get_transfer_daemon().add_callback(self._handle_new_connection)
        self._outcome_sync = threading.Semaphore(0)
        self._outcome = None

    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def outcome(self) -> Response:
        log.d("Blocking and waiting for outcome...")

        self._outcome_sync.acquire()
        outcome = self._outcome
        self._outcome_sync.release()

        log.i("Transfer outcome: %d", outcome)

        self._notify_service_end()

        return create_success_response(outcome)


    def _handle_new_connection(self, sock: SocketTcpIn) -> bool:
        if not sock:
            self._finish(TransferOutcomes.CONNECTION_ESTABLISHMENT_ERROR)
            return False # not handled

        if sock.remote_endpoint()[0] != self._client.endpoint[0]:
            log.e("Unexpected es connected: forbidden")
            return False # not handled

        log.i("Received connection from valid endpoint %s", sock.remote_endpoint())
        self._transfer_sock = sock

        # Finally execute the transfer logic
        th = threading.Thread(target=self._run, daemon=True)
        th.start()

        return True # handled


    def _success(self):
        self._finish(0)

    def _finish(self, outcome):
        self._outcome = outcome
        self._outcome_sync.release()



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

# =============================================
# ================ PUT SERVICE ================
# =============================================


class PutService(IPutService, TransferService):
    def __init__(self,
                 check: bool,
                 port: int,
                 sharing: Sharing,
                 sharing_rcwd,
                 client: ClientContext,
                 end_callback: Callable[[BaseClientService], None]):
        super().__init__(port, sharing, sharing_rcwd, client, end_callback)
        self._check = check
        self._incomings = queue.Queue()

    @expose
    @trace_api
    @check_service_owner
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
                log.d("Overwrite policy is PROMPT, overwriting it unconditionally")

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
                readlen = min(incoming_file_len - cur_pos, TransferService.BUFFER_SIZE)

                # Read from the remote
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


# =============================================
# ============== SHARING SERVICE ==============
# =============================================


def check_write_permission(api):
    def check_write_permission_wrapper(service: 'SharingService', *vargs, **kwargs):
        if service._sharing.read_only:
            log.e("Forbidden: write action on read only sharing by [%s]", pyro_client_endpoint())
            return service._create_sharing_error_response(ServerErrors.NOT_WRITABLE)
        return api(service, *vargs, **kwargs)

    check_write_permission_wrapper.__name__ = api.__name__

    return check_write_permission_wrapper



class SharingService(ISharingService, BaseClientSharingService):

    def __init__(self,
                 server_port: int,
                 sharing: Sharing,
                 sharing_rcwd: str,
                 client: ClientContext,
                 end_callback: Callable[[BaseClientService], None]):
        super().__init__(sharing, sharing_rcwd, client, end_callback)
        self._server_port = server_port

    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    def rls(self, *,
            path: str = None, sort_by: List[str] = None,
            reverse: bool = False, hidden: bool = False) -> Response:

        path = path or "."
        sort_by = sort_by or ["name"]
        reverse = reverse or False

        if not is_str(path) or not is_list(sort_by) or not is_bool(reverse):
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RLS %s %s%s [%s]",
              path, sort_by,
              " | reverse " if reverse else "",
              str(client_endpoint))

        # Compute real path and check path legality
        real_path = self._real_path_from_rcwd(path)

        if not self._is_real_path_allowed(real_path):
            log.e("Path is invalid (out of sharing domain)")
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        log.i("Going to ls on %s", real_path)

        ls_result = ls(real_path, sort_by=sort_by, reverse=reverse)
        if ls_result is None:  # Check is None, since might be empty
            return self._create_sharing_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

        log.i("RLS response %s", str(ls_result))

        return create_success_response(ls_result)


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    def rtree(self, *, path: str = None, sort_by: List[str] = None,
              reverse: bool = False, hidden: bool = False,
              max_depth: int = None, ) -> Response:

        path = path or "."
        sort_by = sort_by or ["name"]
        reverse = reverse or False

        if not is_str(path) or not is_list(sort_by) or not is_bool(reverse):
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RTREE %s %s%s [%s]",
              path, sort_by,
              " | reverse " if reverse else "",
              str(client_endpoint))

        # Compute real path and check path legality
        real_path = self._real_path_from_rcwd(path)

        if not self._is_real_path_allowed(real_path):
            log.e("Path is invalid (out of sharing domain)")
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        log.i("Going to tree on %s", real_path)

        tree_root = tree(real_path, sort_by=sort_by, reverse=reverse, max_depth=max_depth)
        if tree_root is None:  # Check is None, since might be empty
            return self._create_sharing_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

        log.i("RTREE response %s", j(tree_root))

        return create_success_response(tree_root)


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    def rpwd(self) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i("<< RPWD %s", str(client_endpoint))
        return create_success_response(self._rcwd)


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    def rcd(self, path: str) -> Response:
        path = path or "."

        if not is_str(path):
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RCD %s [%s]", path, str(client_endpoint))

        new_real_path = self._real_path_from_rcwd(path)

        if not self._is_real_path_allowed(new_real_path):
            log.e("Path is invalid (out of sharing domain)")
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        if not os.path.isdir(new_real_path):
            log.e("Path does not exists")
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        log.i("New rcwd real path: %s", new_real_path)

        self._rcwd = self._trailing_path_from_root(new_real_path)
        log.i("New rcwd: %s", self._rcwd)

        return create_success_response(self._rcwd)


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    @check_write_permission
    def rmkdir(self, directory: str) -> Response:
        if not is_str(directory):
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RMKDIR %s [%s]", directory, str(client_endpoint))

        real_path = self._real_path_from_rcwd(directory)

        if not self._is_real_path_allowed(real_path):
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        log.i("Going to mkdir on %s", real_path)

        try:
            os.makedirs(real_path, exist_ok=True)
        except Exception as ex:
            log.exception("mkdir exception")
            return self._create_sharing_error_response(str(ex))

        return create_success_response()

    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    @check_write_permission
    def rcp(self, sources: List[str], destination: str) -> Response:
        return self._rmvcp(sources, destination, cp, "CP")


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    @check_write_permission
    def rmv(self, sources: List[str], destination: str) -> Response:
        return self._rmvcp(sources, destination, mv, "MV")


    def _rmvcp(self, sources: List[str], destination: str,
               primitive: Callable[[str, str], bool],
               primitive_name: str = "MV/CP"):

        if not is_list(sources) or len(sources) < 1 or not is_str(destination):
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        dest_real_path = self._real_path_from_rcwd(destination)

        if not self._is_real_path_allowed(dest_real_path):
            log.e("Path is invalid (out of sharing domain)")
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        # C1/C2 check: with 3+ arguments
        if len(sources) >= 2:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not os.path.isdir(dest_real_path):
                log.e("'%s' must be an existing directory", dest_real_path)
                return self._create_sharing_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

        errors = []

        client_endpoint = pyro_client_endpoint()

        log.i("<< %s %s %s [%s]",
              primitive_name, sources, destination, str(client_endpoint))

        for src in sources:

            src_real_path = self._real_path_from_rcwd(src)

            # Path validity check
            if not self._is_real_path_allowed(src_real_path):
                log.e("Path is invalid (out of sharing domain)")
                errors.append(ServerErrors.INVALID_PATH)
                continue

            try:
                log.i("%s %s -> %s", primitive_name, src_real_path, dest_real_path)
                primitive(src_real_path, dest_real_path)
            except Exception as ex:
                errors.append(str(ex))

        # Eventually report errors
        response_data = None

        if errors:
            log.e("Reporting %d errors to the es", len(errors))

            if len(sources) == 1:
                # Only a request with a fail: global fail
                return self._create_sharing_error_response(errors[0])

            response_data = {"errors": errors}

        return create_success_response(response_data)


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    @check_write_permission
    def rrm(self, paths: List[str]) -> Response:
        client_endpoint = pyro_client_endpoint()

        if not is_list(paths) or len(paths) < 1:
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        log.i("<< RRM %s [%s]", paths, str(client_endpoint))

        errors = []

        def handle_rm_error(err):
            log.i("RM error: %s", err)
            errors.append(str(err))


        for path in paths:
            rm_path = self._real_path_from_rcwd(path)

            log.i("RM on path: %s", rm_path)

            if not self._is_real_path_allowed(rm_path):
                log.e("Path is invalid (out of sharing domain)")
                errors.append(ServerErrors.INVALID_PATH)
                continue

            # Do not allow to remove the entire sharing
            try:
                if os.path.samefile(self._sharing.path, rm_path):
                    log.e("Cannot delete the sharing's root directory")
                    errors.append(ServerErrors.INVALID_PATH)
                    continue
            except:
                # Maybe the file does not exists, don't worry and pass
                # it to rm that will handle it properly with error_callback
                # and report the error description
                pass
            finally:
                rm(rm_path, error_callback=handle_rm_error)

        # Eventually put errors in the response
        response_data = None

        if errors:
            log.e("Reporting %d errors to the es", len(errors))

            if len(paths) == 1:
                # Only a request with a fail: global fail
                return self._create_sharing_error_response(errors[0])

            response_data = {"errors": errors}

        return create_success_response(response_data)

    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    def get(self, paths: List[str], check: bool = False) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i("<< GET %s [%s]", str(paths), str(client_endpoint))

        if not paths:
            paths = ["."]


        # Compute real path for each name
        real_paths: List[Tuple[str, str]] = []
        for f in paths:
            if f == ".":
                # get the sharing, wrapped into a folder with this sharing name
                real_paths.append((self._current_real_path(), self._sharing.name))  # no prefixes
            else:
                f = f.replace("*", ".")  # glob
                real_paths.append((self._real_path_from_rcwd(f), ""))  # no prefixes

        normalized_paths = sorted(real_paths, reverse=True)
        log.i("Normalized paths:\n%s", normalized_paths)

        get = GetService(
            normalized_paths,
            check=check,
            port=transfer_port(self._server_port),
            sharing=self._sharing,
            sharing_rcwd=self._rcwd,
            client=self._client,
            end_callback=lambda getserv: getserv.unpublish()
        )

        uid = get.publish()

        return create_success_response({
            "uid": uid,
        })


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    def put(self, check: bool = False) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i("<< PUT [%s]", str(client_endpoint))

        if self._sharing.ftype == FTYPE_FILE:
            # Cannot put within a file
            log.e("Cannot put within a file sharing")
            return create_error_response(ServerErrors.NOT_ALLOWED)

        put = PutService(
            check=check,
            port=transfer_port(self._server_port),
            sharing=self._sharing,
            sharing_rcwd=self._rcwd,
            client=self._client,
            end_callback=lambda putserv: putserv.unpublish()
        )

        uid = put.publish()

        return create_success_response({
            "uid": uid,
        })

    @expose
    @trace_api
    @check_service_owner
    def close(self):
        client_endpoint = pyro_client_endpoint()

        log.i("<< CLOSE [%s]", str(client_endpoint))
        log.i("Deallocating es resources...")

        # TODO remove gets/puts

        self._notify_service_end()
