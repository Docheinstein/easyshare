import ssl
from abc import ABC, abstractmethod
from typing import Optional, Any, Tuple

import Pyro5.api as pyro
from Pyro5 import socketutil

from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.utils.pyro.server import pyro_context
from easyshare.utils.rand import uuid

log = get_logger(__name__)


class PyroObject(ABC):
    @abstractmethod
    def close(self):
        pass

# =============================================
# ============== PYRO DAEMON ================
# =============================================


_pyro_daemon: Optional['PyroDaemon'] = None


class PyroDaemon(pyro.Daemon):
    """
    Main daemon that listens to new requests from clients (by default on port 12020),
    actually is a Pyro.Daemon which adds some facility to handle client disconnections.
    Each 'Service' will be registered to to daemon for being exposed outside.
    """


    def __init__(self, *vargs, **kwargs):
        super().__init__(*vargs, **kwargs)
        self._disconnection_callbacks = set()
        self._published = {}

    def add_disconnection_callback(self, callback):
        """ Adds a callback to invoke when a client disconnects """
        self._disconnection_callbacks.add(callback)

    def remove_disconnection_callback(self, callback):
        """ Removes a callback from the set of callbacks """
        self._disconnection_callbacks.remove(callback)

    def publish(self, obj: PyroObject, uid: str = None, track: bool = True) -> Tuple[str, str]: # uri, uid
        """ Publishes an object which will be available through a remote Pyro.Proxy """

        obj_id = uid or uuid()

        log.i("Publishing pyro object %s with uid='%s'",
              obj.__class__.__name__, obj_id[:6] + "..." + obj_id[-6:])

        setattr(obj, "_publish_id", obj_id)

        if track:
            pyro_context().track_resource(obj)

        return str(self.register(obj, obj_id)), obj_id

    def unpublish(self, obj: PyroObject):
        """ Unpublishes an object from the set of published pyro objects """

        obj_id = getattr(obj, "_publish_id")
        if obj_id:
            log.i("Unpublishing pyro object %s with uid='%s'",
                  obj.__class__.__name__, obj_id[:6] + "..." + obj_id[-6:])
        else:
            log.w("Object does not have a _publish_id, is it really published?")

        pyro_context().untrack_resource(obj)

        self.unregister(obj)

        obj.close()

    def clientDisconnect(self, conn: socketutil.SocketConnection):
        """ Callback which will be invoked by pyro when a client disconnects """
        log.d("Pyro endpoint disconnected: %s", conn.sock.getpeername())
        log.d("Notifying %d listeners", len(self._disconnection_callbacks))
        for cb in self._disconnection_callbacks:
            cb(conn)

    def endpoint(self) -> Endpoint:
        return self.sock.getsockname()

    def address(self) -> str:
        return self.endpoint()[0]

    def port(self) -> int:
        return self.endpoint()[1]

    def has_ssl(self) -> bool:
        return isinstance(self.sock, ssl.SSLSocket)


def init_pyro_daemon(address: str,
                     port: int = 0):
    """ Initializes the global pyro daemon on the given address/port """

    global _pyro_daemon
    log.i("Initializing pyro daemon\n"
          "\tAddress: %s\n"
          "\tPort: %s\n",
          address, port)

    _pyro_daemon = PyroDaemon(
        host=address,
        port=port,
    )


def get_pyro_daemon() -> Optional[PyroDaemon]:
    """ Get the global pyro daemon instance """
    return _pyro_daemon

