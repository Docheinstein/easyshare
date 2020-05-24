import string
import threading
from pathlib import Path
from typing import Optional, Set

from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.protocol.types import SharingInfo, FTYPE_FILE, FTYPE_DIR, FileType, create_file_info, ftype
from easyshare.utils.json import j
from easyshare.utils.path import LocalPath
from easyshare.utils.rand import randstring

log = get_logger(__name__)


# =============================================
# ============== CLIENT CONTEXT ===============
# =============================================


class ClientContext:
    """ Contains the server-side information kept for a connected client """

    def __init__(self, endpoint: Endpoint):
        # Actually the endpoint it's just the first of the endpoints the client
        # can have due to different connections to server/sharing, transfer, rexec, ...
        # We have to bind all the endpoints to client in the server logic for
        # handle disconnection properly
        self.endpoint: Optional[Endpoint] = endpoint
        self.services: Set[str] = set() # list of services published for this client
        self.tag = randstring(4, alphabet=string.ascii_lowercase) # not an unique id, just a tag
        self.lock = threading.Lock() # for atomic operations on services


    def __str__(self):
        return f"{self.endpoint} [{self.tag}]"


    def add_service(self, service_id: str):
        """
        Bounds a service to this client (in order to unpublish
        the service when the user connection is down)
        """
        log.d("Service [%s] added to client ctx", service_id)
        with self.lock:
            self.services.add(service_id)


    def remove_service(self, service_id: str):
        """ Unbounds a previously added service from this client"""
        log.d("Service [%s] removed from client ctx", service_id)
        with self.lock:
            self.services.remove(service_id)


# =============================================
# ================== SHARING ==================
# =============================================


class Sharing:
    """
    The concept of shared file or directory.
    Basically contains the path of the file/dir to share and the assigned name.
    """
    def __init__(self, name: str, ftype: FileType, path: Path, read_only: bool):
        self.name = name
        self.ftype = ftype
        self.path = path
        self.read_only = read_only

    def __str__(self):
        return j(self.info())

    @staticmethod
    def create(name: str, path: str, read_only: bool = False) -> Optional['Sharing']:
        """
        Creates a sharing for the given 'name' and 'path'.
        Ensures that the path exists and sanitize the sharing name.
        """
        # Ensure path existence
        if not path:
            log.e("Sharing creation failed; path not provided")
            return None

        path = LocalPath(path)

        if not path.exists():
            log.w("Nothing exists at path %s", path)
            return None

        sh_ftype = ftype(path)
        if sh_ftype != FTYPE_FILE and sh_ftype != FTYPE_DIR:
            log.e("Invalid sharing path")
            return None

        return Sharing(
            name=name or path.name,
            ftype=sh_ftype,
            path=path,
            read_only=True if read_only else False,
        )

    def info(self) -> SharingInfo:
        """ Returns information ('SharingInfo') for this sharing """
        return {
            "name": self.name,
            "ftype": self.ftype,
            "read_only": self.read_only,
        }