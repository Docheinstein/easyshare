from typing import Optional, Any, Tuple

import Pyro5.api as pyro
from Pyro5 import socketutil

from easyshare.logging import get_logger
from easyshare.utils.str import uuid

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


_pyro_daemon: Optional[EsdDaemon] = None


def init_pyro_daemon(address: str,
                     port: int = 0,
                     nat_address: str = None,
                     nat_port: int = None):
    global _pyro_daemon
    log.i("Initializing pyro daemon\n"
          "\tAddress: %s\n"
          "\tPort: %s\n"
          "\tNat address: %s\n"
          "\tNat port: %s",
          address, port, nat_address, nat_port
      )
    _pyro_daemon = EsdDaemon(
        host=address,
        port=port,
        nathost=nat_address,
        natport=nat_port
    )


def get_pyro_daemon() -> Optional[EsdDaemon]:
    return _pyro_daemon

