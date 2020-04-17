import os
import queue
import random
import threading
import time
from typing import List, Optional, Callable

from easyshare.server.client import ClientContext
from easyshare.shared.log import e, d, i, v
from easyshare.socket.tcp import SocketTcpAcceptor
from easyshare.utils.str import randstring


class GetTransactionHandler(threading.Thread):
    BUFFER_SIZE = 4096

    def __init__(self,
                 files: List[str],
                 sharing_name: str,
                 owner: Optional[ClientContext] = None,
                 on_end: Callable[['GetTransactionHandler'], None] = None,
                 transaction_id: str = None):
        self._transaction_id = transaction_id or randstring()
        self._next_files = files
        self._sock = SocketTcpAcceptor()
        self._servings = queue.Queue()
        self._sharing_name = sharing_name
        self._owner = owner
        self._on_end = on_end
        threading.Thread.__init__(self)

    def sharing_name(self) -> str:
        return self._sharing_name

    def owner(self) -> Optional[ClientContext]:
        return self._owner

    def next_files(self) -> List[str]:
        return self._next_files

    def transaction_id(self) -> str:
        return self._transaction_id

    def port(self) -> int:
        return self._sock.port()

    def run(self) -> None:
        if not self._sock:
            e("Invalid socket")
            return

        d("Starting GetTransactionHandler")
        client_sock, endpoint = self._sock.accept()
        i("Connection established with %s", endpoint)

        go_ahead = True

        while go_ahead:
            d("blocking wait on next_servings")

            # Send files until the servings buffer is empty
            # Wait on the blocking queue for the next file to send
            next_serving = self._servings.get()

            if not next_serving:
                v("No more files: END")
                break

            d("Next serving: %s", next_serving)

            f = open(next_serving, "rb")
            cur_pos = 0
            file_len = os.path.getsize(next_serving)

            # Send file
            while True:
                r = random.random() * 0.001
                time.sleep(0.001 + r)
                chunk = f.read(GetTransactionHandler.BUFFER_SIZE)
                if not chunk:
                    d("Finished %s", next_serving)
                    break

                d("Read chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                try:
                    d("sending chunk...")
                    client_sock.send(chunk)
                    d("sending chunk DONE")
                except Exception as ex:
                    e("send error %s", ex)
                    # Abort transaction
                    go_ahead = False
                    break

                d("%d/%d (%.2f%%)", cur_pos, file_len, cur_pos / file_len * 100)

            d("Closing file %s", next_serving)
            f.close()

        v("Transaction handler job finished")

        client_sock.close()
        self._sock.close()

        # Callback
        if self._on_end:
            self._on_end(self)

    def push_file(self, path: str):
        d("Pushing file to handler %s", path)
        self._servings.put(path)

    def abort(self):
        v("aborting transaction")
        with self._servings.mutex:
            self._servings.queue.clear()
        self._servings.put(None)

    def done(self):
        v("end(): no more files")
        self._servings.put(None)

