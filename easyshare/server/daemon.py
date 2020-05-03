from typing import Optional, Any, Tuple, List, Set, Callable, Union

import Pyro5.api as pyro
from Pyro5 import socketutil

from easyshare.logging import get_logger
from easyshare.utils.str import uuid
from easyshare.utils.types import is_str

log = get_logger(__name__)


class EsdDaemon(pyro.Daemon):
    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self.disconnection_callbacks = set()

    def add_disconnection_callback(self, callback):
        self.disconnection_callbacks.add(callback)

    def remove_disconnection_callback(self, callback):
        self.disconnection_callbacks.remove(callback)

    def publish(self, obj: Any, uid: str = None) -> Tuple[str, str]:  # uri, uid
        obj_id = uid or uuid()
        log.i("Publishing pyro object %s with uid='%s'",
              obj.__class__.__name__, obj_id[:6] + "..." + obj_id[-6:])

        return str(super().register(obj, objectId=obj_id)), obj_id

    def unpublish(self, obj_id):
        log.i("Unpublishing pyro object with uid='%s'",
              obj_id[:6] + "..." + obj_id[-6:])
        self.unregister(obj_id)

    def clientDisconnect(self, conn: socketutil.SocketConnection):
        log.i("Client disconnected: %s", conn.sock.getpeername())
        log.d("Notifying %d listeners", len(self.disconnection_callbacks))
        for cb in self.disconnection_callbacks:
            cb(conn)


pyro_daemon: Optional[EsdDaemon] = None


def init_pyro_daemon(host: str):
    global pyro_daemon
    log.i("Initializing pyro daemon at %s", host)
    pyro_daemon = EsdDaemon(host=host)


def get_pyro_daemon() -> Optional[EsdDaemon]:
    return pyro_daemon

