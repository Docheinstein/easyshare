import threading
from typing import Callable, Optional, List

from Pyro5.server import expose
from ptyprocess import PtyProcess

from easyshare.esd.services import BaseClientService, check_sharing_service_owner


from easyshare.esd.common import ClientContext
from easyshare.logging import get_logger
from easyshare.protocol.services import IRexecService, IRshellService
from easyshare.protocol.responses import create_success_response, ServerErrors, create_error_response, Response
from easyshare.utils.os import pty_detached, get_passwd
from easyshare.utils.pyro.server import pyro_client_endpoint, trace_api, try_or_command_failed_response
from easyshare.utils.types import is_int

log = get_logger(__name__)

# =============================================
# ============== RSHELL SERVICE ==============
# =============================================



class BlockingBuffer:
    """
    Implementation of a blocking queue for a buffer of  lines.
    (probably python Queue will do the job as well).
    """
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

class RshellService(IRshellService, BaseClientService):
    """
    Implementation of 'IRshellService' interface that will be published with Pyro.
    Handles a single execution of a rshell command.
    """

    def name(self) -> str:
        return "rshell"


    def __init__(self, client: ClientContext):
        super().__init__(client)
        self._buffer = BlockingBuffer()
        self._ptyproc: Optional[PtyProcess] = None

    @expose
    @trace_api
    @check_sharing_service_owner
    @try_or_command_failed_response
    def recv(self) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i(">> RSHELL RECV [%s]", client_endpoint)

        buf = None
        while not buf:  # avoid spurious wake ups
            buf = self._buffer.pull()

        out = []
        retcode = None

        for v in buf:
            if is_int(v):
                retcode = v
            else:
                out.append(v)

        data = {
            "out": out,
        }

        if retcode is not None:
            # Command finished, notify the remote and close the service
            data["retcode"] = retcode

            self.unpublish()  # job finished

        return create_success_response(data)

    @expose
    @trace_api
    @check_sharing_service_owner
    @try_or_command_failed_response
    def send_data(self, data: str) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i(">> RSHELL SEND (%s) [%s]", data, client_endpoint)

        if not data:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        while data:
            n = self._ptyproc.write(data)
            data = data[n:]

        return create_success_response()

    @expose
    @trace_api
    @check_sharing_service_owner
    @try_or_command_failed_response
    def send_event(self, ev: int) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i(">> REXEC SEND EVENT (%d) [%s]", ev, client_endpoint)

        if ev == IRexecService.Event.TERMINATE:
            log.d("Sending SIGTERM")
            self._ptyproc.terminate()
        elif ev == IRexecService.Event.EOF:
            log.d("Sending EOF")
            self._ptyproc.close()
        else:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        return create_success_response()

    def run(self):
        self._ptyproc = pty_detached(
            out_hook=self._out_hook,
            end_hook=self._end_hook,
            cmd=f"{get_passwd().pw_shell}"
        )

    def _out_hook(self, content: str):
        log.d("> %s", content)
        self._buffer.push(content)

    def _end_hook(self, retcode):
        log.d("END %d", retcode)
        self._buffer.push(retcode)
