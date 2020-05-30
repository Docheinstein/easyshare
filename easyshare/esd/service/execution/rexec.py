import subprocess
import threading
from typing import Optional

from easyshare.esd.common import ClientContext
from easyshare.esd.services.execution import BlockingBuffer
from easyshare.logging import get_logger
from easyshare.protocol.types import RexecEventType
from easyshare.utils.os import run_detached
from easyshare.utils.types import stob, btos, itob

log = get_logger(__name__)

# =============================================
# ============== REXEC SERVICE ==============
# =============================================

class RexecService:

    def __init__(self, client: ClientContext, cmd: str):
        self._client = client
        self._cmd = cmd
        self._buffer = BlockingBuffer()
        self._proc: Optional[subprocess.Popen] = None
        self._proc_out_handler: Optional[threading.Thread] = None

    def run(self) -> int:
        # Bind server stdout/stderr and send those to client
        self._proc, self._proc_out_handler = run_detached(
            self._cmd,
            stdout_hook=self._stdout_hook,
            stderr_hook=self._stderr_hook,
            end_hook=self._end_hook
        )

        # Receive stdin from client
        stdin_th = threading.Thread(target=self._stdin_receiver)
        stdin_th.start()

        stdin_th.join()
        self._proc_out_handler.join()

        return self._proc.returncode

    def _stdin_receiver(self):
        while True:
            in_b = self._client.stream.read(trace=True)
            event_type: int = in_b[0]
            log.d("Event type = %d", event_type)

            if event_type == RexecEventType.TEXT:
                text = btos(in_b[1:])
                log.d("< %s", text)
                self._proc.stdin.write(text)
                self._proc.stdin.flush()
            elif event_type == RexecEventType.EOF:
                log.d("< EOF")
                self._proc.stdin.close()
            elif event_type == RexecEventType.KILL:
                log.d("< KILL")
                self._proc.terminate()
            elif event_type == RexecEventType.ENDACK:
                log.d("< ENDACK")
                break
            else:
                log.w("Can't handle event of type %d", event_type)

    def _stdout_hook(self, text: str):
        log.d("> %s", text)
        self._client.stream.write(RexecEventType.TEXT_B + stob(text), trace=True)

    def _stderr_hook(self, text: str):
        log.w("> %s", text)
        self._client.stream.write(RexecEventType.TEXT_B + stob(text), trace=True)


    def _end_hook(self, retcode):
        log.d("END %d", retcode)
        self._client.stream.write(
            RexecEventType.RETCODE_B + itob(retcode % 255, length=1),
            trace=True
        )

