import os
import queue
import random
import threading
import time
from typing import List, Optional, Callable

from easyshare.logging import get_logger
from easyshare.protocol.fileinfo import FileInfo
from easyshare.server.client import ClientContext
from easyshare.ssl import get_ssl_context
from easyshare.socket.tcp import SocketTcpAcceptor
from easyshare.utils.str import randstring

log = get_logger()

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
        self._sock = SocketTcpAcceptor(ssl_context=get_ssl_context())
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
        # TODO useless
        return self._next_files

    def transaction_id(self) -> str:
        return self._transaction_id

    def port(self) -> int:
        return self._sock.port()

    def run(self) -> None:
        if not self._sock:
            log.e("Invalid socket")
            return

        log.d("Starting GetTransactionHandler")
        client_sock, endpoint = self._sock.accept()
        log.i("Connection established with %s", endpoint)

        go_ahead = True

        while go_ahead:
            log.d("blocking wait on next_servings")

            # Send files until the servings buffer is empty
            # Wait on the blocking queue for the next file to send
            next_serving = self._servings.get()

            if not next_serving:
                log.i("No more files: END")
                break

            log.i("Next serving: %s", next_serving)

            f = open(next_serving, "rb")
            cur_pos = 0
            file_len = os.path.getsize(next_serving)

            # Send file
            while cur_pos < file_len:
                r = random.random() * 0.001
                time.sleep(0.001 + r)
                chunk = f.read(GetTransactionHandler.BUFFER_SIZE)
                if not chunk:
                    log.i("Finished %s", next_serving)
                    break

                log.i("Read chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                try:
                    log.d("sending chunk...")
                    client_sock.send(chunk)
                    log.d("sending chunk DONE")
                except Exception as ex:
                    log.e("send error %s", ex)
                    # Abort transaction
                    go_ahead = False
                    break

                log.i("%d/%d (%.2f%%)", cur_pos, file_len, cur_pos / file_len * 100)

            log.i("Closing file %s", next_serving)
            f.close()

        log.i("Transaction handler job finished")

        client_sock.close()
        self._sock.close()

        # Callback
        if self._on_end:
            self._on_end(self)

    def push_file(self, path: str):
        log.i("Pushing file to handler %s", path)
        self._servings.put(path)

    def abort(self):
        log.i("aborting transaction")
        with self._servings.mutex:
            self._servings.queue.clear()
        self._servings.put(None)

    def done(self):
        log.i("end(): no more files")
        self._servings.put(None)


class PutTransactionHandler(threading.Thread):
    BUFFER_SIZE = 4096

    def __init__(self,
                 sharing_name: str,
                 owner: Optional[ClientContext] = None,
                 on_end: Callable[['GetTransactionHandler'], None] = None,
                 transaction_id: str = None):
        self._transaction_id = transaction_id or randstring()
        self._sock = SocketTcpAcceptor(ssl_context=get_ssl_context())
        self._incomings = queue.Queue()
        self._sharing_name = sharing_name
        self._owner = owner
        self._on_end = on_end
        threading.Thread.__init__(self)

    def sharing_name(self) -> str:
        return self._sharing_name

    def owner(self) -> Optional[ClientContext]:
        return self._owner

    def transaction_id(self) -> str:
        return self._transaction_id

    def port(self) -> int:
        return self._sock.port()

    def run(self) -> None:
        if not self._sock:
            log.e("Invalid socket")
            return

        log.d("Starting PutTransactionHandler")
        client_sock, endpoint = self._sock.accept()
        log.i("Connection established with %s", endpoint)

        go_ahead = True

        while go_ahead:
            log.d("blocking wait on next_servings")

            # Recv files until the servings buffer is empty
            # Wait on the blocking queue for the next file to recv
            next_incoming = self._incomings.get()

            if not next:
                log.i("No more files: END")
                break

            next_path, next_size = next_incoming

            log.i("Next incoming: %s", next_incoming)

            f = open(next_path, "wb")
            cur_pos = 0
            # file_len = os.path.getsize(next_serving)
            #
            # Recv file
            while cur_pos < next_size:
                r = random.random() * 0.001
                time.sleep(0.001 + r)

                chunk = client_sock.recv(GetTransactionHandler.BUFFER_SIZE)

                # chunk = f.read(PutTransactionHandler.BUFFER_SIZE)

                if not chunk:
                    log.i("Finished %s", next_path)
                    break

                log.i("Read chunk of %dB", len(chunk))
                cur_pos += len(chunk)

                f.write(chunk)

                #
                # try:
                #     log.d("sending chunk...")
                #     client_sock.send(chunk)
                #     log.d("sending chunk DONE")
                # except Exception as ex:
                #     log.e("send error %s", ex)
                #     # Abort transaction
                #     go_ahead = False
                #     break

                log.i("%d/%d (%.2f%%)", cur_pos, next_size, cur_pos / next_size * 100)

            log.i("Closing file %s", next_path)
            f.close()

        log.i("Transaction handler job finished")

        client_sock.close()
        self._sock.close()

        # Callback
        if self._on_end:
            self._on_end(self)

    def push_file(self, path: str, size: int):
        log.i("Pushing file info to handler %s (%d)", path, size)
        self._incomings.put((path, size))

    def abort(self):
        log.i("aborting transaction")
        with self._incomings.mutex:
            self._incomings.queue.clear()
        self._incomings.put(None)

    def done(self):
        log.i("end(): no more files")
        self._incomings.put(None)

