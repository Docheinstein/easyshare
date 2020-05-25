import string
from pathlib import Path
from typing import Optional
from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.protocol.types import SharingInfo, FTYPE_FILE, FTYPE_DIR, FileType, ftype
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
        # (is the one that calls connect())
        self.endpoint: Optional[Endpoint] = endpoint #
        self.tag = randstring(4, alphabet=string.ascii_lowercase) # not an unique id, just a tag

    def __str__(self):
        return f"{self.endpoint} [{self.tag}]"

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