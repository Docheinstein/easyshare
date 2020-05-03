from typing import Optional, Any, Tuple, List

import Pyro5.api as pyro

from easyshare.logging import get_logger
from easyshare.utils.str import uuid

log = get_logger(__name__)

pyro_daemon: Optional[pyro.Daemon] = None

def init_pyro_daemon(host: str):
    global pyro_daemon
    log.i("Initializing pyro daemon at %s", host)
    pyro_daemon = pyro.Daemon(host=host)


def get_pyro_daemon():
    return pyro_daemon


def publish_pyro_object(obj: Any, uid: str = None) -> Tuple[str, str]: # uri, uid
    obj_id = uid or uuid()
    log.i("Publishing pyro object %s with uid='%s'", obj.__class__.__name__, obj_id[:6] + "..." + obj_id[-6:])

    return str(pyro_daemon.register(obj, objectId=obj_id)), obj_id


def unpublish_pyro_object(obj_id: str):
    log.i("Unpublishing pyro object with uid='%s'", obj_id[:6] + "..." + obj_id[-6:])
    pyro_daemon.unregister(objectOrId=obj_id)


def unpublish_pyro_objects(obj_ids: List[str]):
    for obj_id in obj_ids:
        unpublish_pyro_object(obj_id)