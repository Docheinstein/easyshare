import subprocess
import threading
from typing import Optional, Union, List

import Pyro4

from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.pyro import IRexecTransaction
from easyshare.protocol.response import Response, create_success_response, create_error_response
from easyshare.server.common import trace_pyro_api
from easyshare.utils.os import run_detached

log = get_logger(__name__)


class RexecTransaction(IRexecTransaction):
    def __init__(self, cmd: str):
        self.cmd = cmd
        self.output_buffer = []
        self.output_buffer_sync = threading.Semaphore(0)
        self.output_buffer_lock = threading.RLock()
        self.proc: Optional[subprocess.Popen] = None
        self.proc_handler: Optional[threading.Thread] = None

    @Pyro4.expose
    @trace_pyro_api
    def recv(self) -> Response:
        log.i(">> REXEC RECV (%s)")

        data = self._read()

        return create_success_response(data)


    @Pyro4.expose
    @trace_pyro_api
    def send(self, data: str) -> Response:
        log.i(">> REXEC SEND (%s)")

        if not data:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        self._write(data)

        return create_success_response()


    def run(self):
        self.proc, self.proc_handler = run_detached(
            self.cmd, stdout_hook=self._stdout_hook, end_hook=self._end_hook)
        return self.proc, self.proc_handler

    def _read(self, timeout=None) -> Union[List[str], int]:
        log.d("rexec poll()")
        return self._buffer_pull(timeout)

    def _write(self, data: str):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def _stdout_hook(self, line):
        log.d("> %s", line)
        self._buffer_push(line)

    def _end_hook(self, retcode):
        log.d("END %d", retcode)
        self._buffer_push(retcode)

    def _buffer_pull(self, timeout=None) -> List[Union[str, int]]:
        ret: List[str] = []

        self.output_buffer_sync.acquire()
        self.output_buffer_lock.acquire()

        while self.output_buffer:
            val = self.output_buffer.pop(0)
            log.d("< %s", val)
            ret.append(val)

        self.output_buffer_lock.release()

        return ret

    def _buffer_push(self, val: Union[str, int]):
        self.output_buffer_lock.acquire()

        self.output_buffer.append(val)
        # time.sleep(0.3)

        self.output_buffer_sync.release()
        self.output_buffer_lock.release()