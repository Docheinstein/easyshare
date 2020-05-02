import subprocess
import threading
from typing import Optional, Union, List, Callable

import Pyro4

from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.pyro import IRexecTransaction
from easyshare.protocol.response import Response, create_success_response, create_error_response
from easyshare.utils.os import run_detached
from easyshare.utils.pyro import pyro_client_endpoint, pyro_expose
from easyshare.utils.types import is_int


log = get_logger(__name__)


STDOUT = 1
STDERR = 2


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


class RexecTransaction(IRexecTransaction):
    def __init__(self, cmd: str, owner_address: str, on_end: Callable[[int], None]):
        self._cmd = cmd
        self._owner_address = owner_address
        self._on_end = on_end
        self._buffer = BlockingBuffer()
        self.proc: Optional[subprocess.Popen] = None
        self.proc_handler: Optional[threading.Thread] = None

    @pyro_expose
    def recv(self) -> Response:
        if self._owner_address and \
                self._owner_address != pyro_client_endpoint()[0]:
            return create_error_response(ServerErrors.NOT_ALLOWED)

        log.i(">> REXEC RECV")

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
            data["retcode"] = retcode

            if self._on_end:
                self._on_end(retcode)

        return create_success_response(data)


    @Pyro4.expose
    @pyro_expose
    def send_data(self, data: str) -> Response:
        if self._owner_address and \
                self._owner_address != pyro_client_endpoint()[0]:
            return create_error_response(ServerErrors.NOT_ALLOWED)

        log.i(">> REXEC SEND (%s)", data)

        if not data:
            return create_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        self.proc.stdin.write(data)
        self.proc.stdin.flush()

        return create_success_response()

    @Pyro4.expose
    @pyro_expose
    def send_event(self, ev: int) -> Response:
        if self._owner_address and \
                self._owner_address != pyro_client_endpoint()[0]:
            return create_error_response(ServerErrors.NOT_ALLOWED)

        log.i(">> REXEC SEND EVENT (%d)", ev)

        if ev == IRexecTransaction.Event.TERMINATE:
            log.d("Sending SIGTERM")
            self.proc.terminate()
        elif ev == IRexecTransaction.Event.EOF:
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
