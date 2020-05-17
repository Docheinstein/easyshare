import os
import threading
from typing import Optional, Set

from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.protocol.protocol import FileType, FTYPE_DIR, FTYPE_FILE, SharingInfo
from easyshare.utils.json import j
from easyshare.utils.os import pathify
from easyshare.utils.str import randstring


log = get_logger(__name__)

# =============================================
# ============== CLIENT CONTEXT ===============
# =============================================




class ClientContext:

    def __init__(self, endpoint: Endpoint):
        self.endpoint: Optional[Endpoint] = endpoint
        self.services: Set[str] = set()
        self.tag = randstring(8)
        self.lock = threading.Lock()


    def __str__(self):
        return "{} : {}".format(self.endpoint, self.tag)


    def add_service(self, service_id: str):
        log.d("Service [%s] added", service_id)
        with self.lock:
            self.services.add(service_id)


    def remove_service(self, service_id: str):
        log.d("Service [%s] removed", service_id)
        with self.lock:
            self.services.remove(service_id)


# =============================================
# ================== SHARING ==================
# =============================================


class Sharing:
    def __init__(self, name: str, ftype: FileType, path: str, read_only: bool):
        self.name = name
        self.ftype = ftype
        self.path = path
        self.read_only = read_only

    def __str__(self):
        return j(self.info())

    @staticmethod
    def create(name: str, path: str, read_only: bool = False) -> Optional['Sharing']:
        # Ensure path existence
        if not path:
            log.w("Sharing creation failed; path not provided")
            return None

        path = pathify(path)

        if os.path.isdir(path):
            ftype = FTYPE_DIR
        elif os.path.isfile(path):
            ftype = FTYPE_FILE
        else:
            log.w("Sharing creation failed; invalid path")
            return None

        if not name:
            # Generate the sharing name from the path
            _, name = os.path.split(path)

        # Sanitize the name anyway (only alphanum and _ is allowed)
        # name = keep(name, SHARING_NAME_ALPHABET)

        read_only = True if read_only else False

        return Sharing(
            name=name,
            ftype=ftype,
            path=path,
            read_only=read_only,
        )

    def info(self) -> SharingInfo:
        return {
            "name": self.name,
            "ftype": self.ftype,
            "read_only": self.read_only,
        }
