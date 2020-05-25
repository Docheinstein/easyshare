import threading
from typing import List

from easyshare.logging import get_logger

log = get_logger(__name__)

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
