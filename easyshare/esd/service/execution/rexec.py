from easyshare.consts.os import STDOUT, STDERR

from easyshare.esd.common import ClientContext
from easyshare.esd.services.execution import BlockingBuffer
from easyshare.logging import get_logger
from easyshare.utils.os import run_detached
from easyshare.utils.types import stob

log = get_logger(__name__)

# =============================================
# ============== REXEC SERVICE ==============
# =============================================

class RexecService():

    def __init__(self, client: ClientContext, cmd: str):
        self._client = client
        self._cmd = cmd
        self._buffer = BlockingBuffer()
        # self.proc: Optional[subprocess.Popen] = None
        # self.proc_handler: Optional[threading.Thread] = None

    # @expose
    # @trace_api
    # @check_sharing_service_owner_address
    # @try_or_command_failed_response
    # def recv(self) -> Response:
    #     client_endpoint = pyro_client_endpoint()
    #
    #     log.i(">> REXEC RECV [%s]", client_endpoint)
    #
    #     buf = None
    #     while not buf:  # avoid spurious wake ups
    #         buf = self._buffer.pull()
    #
    #     stdout = []
    #     stderr = []
    #     retcode = None
    #
    #     for v in buf:
    #         if is_int(v):
    #             retcode = v
    #         elif len(v) == 2:
    #             if v[1] == STDOUT:
    #                 stdout.append(v[0])
    #             elif v[1] == STDERR:
    #                 stderr.append(v[0])
    #
    #     data = {
    #         "stdout": stdout,
    #         "stderr": stderr,
    #     }
    #
    #     if retcode is not None:
    #         # Command finished, notify the remote and close the service
    #         data["retcode"] = retcode
    #
    #         self.unpublish()  # job finished
    #
    #     return create_success_response(data)
    #
    # @expose
    # @trace_api
    # @check_sharing_service_owner_address
    # @try_or_command_failed_response
    # def send_data(self, data: str) -> Response:
    #     client_endpoint = pyro_client_endpoint()
    #
    #     log.i(">> REXEC SEND (%s) [%s]", data, client_endpoint)
    #
    #     if not data:
    #         return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)
    #
    #     self.proc.stdin.write(data)
    #     self.proc.stdin.flush()
    #
    #     return create_success_response()

    # @expose
    # @trace_api
    # @check_sharing_service_owner_address
    # @try_or_command_failed_response
    # def send_event(self, ev: int) -> Response:
    #     client_endpoint = pyro_client_endpoint()
    #
    #     log.i(">> REXEC SEND EVENT (%d) [%s]", ev, client_endpoint)
    #
    #     if ev == IRexecService.Event.TERMINATE:
    #         log.d("Sending SIGTERM")
    #         self.proc.terminate()
    #     elif ev == IRexecService.Event.EOF:
    #         log.d("Sending EOF")
    #         self.proc.stdin.close()
    #     else:
    #         return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)
    #
    #     return create_success_response()

    def run(self) -> int:
        proc, proc_handler = run_detached(
            self._cmd,
            stdout_hook=self._stdout_hook,
            stderr_hook=self._stderr_hook,
            end_hook=self._end_hook
        )
        proc_handler.join()
        return proc.returncode

    def _stdout_hook(self, text: str):
        log.d("> %s", text)
        # self._buffer.push((line, STDOUT))
        self._client.stream._write(stob(text))

    def _stderr_hook(self, text: str):
        log.w("> %s", text)
        # self._buffer.push((line, STDERR))
        self._client.stream._write(stob(text))


    def _end_hook(self, retcode):
        log.d("END %d", retcode)
        self._client.stream._write(b"")
        # self._buffer.push(retcode)

