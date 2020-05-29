import string
from pathlib import Path
from typing import Optional
from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.protocol.stream import Stream
from easyshare.protocol.types import SharingInfo, FTYPE_FILE, FTYPE_DIR, FileType, ftype
from easyshare.sockets import SocketTcp
from easyshare.utils.json import j
from easyshare.utils.path import LocalPath
from easyshare.utils.rand import randstring

log = get_logger(__name__)


# =============================================
# ============== CLIENT CONTEXT ===============
# =============================================


class ClientContext:
    """ Contains the server-side information kept for a connected client """

    def __init__(self, sock: SocketTcp):
        self.socket: SocketTcp = sock
        self.stream = Stream(sock)
        self.endpoint: Optional[Endpoint] = sock.remote_endpoint()
        self.tag = randstring(4, alphabet=string.ascii_lowercase) # not an unique id, just a tag


    def __str__(self):
        return f"{self.endpoint[0]}:{self.endpoint[1]} [{self.tag}]"

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

        path = path.resolve() # resolve so that we can user path.name safely

        sh_name = name if name else path.name
        if not name:
            log.w("Name of sharing not provided, generating a default from path '%s' => '%s'", path, sh_name)

        sh = Sharing(
            name=sh_name,
            ftype=sh_ftype,
            path=path,
            read_only=True if read_only else False,
        )

        log.i("Created sharing: %s", j(sh.info()))

        return sh

    def info(self) -> SharingInfo:
        """ Returns information ('SharingInfo') for this sharing """
        return {
            "name": self.name,
            "ftype": self.ftype,
            "read_only": self.read_only,
        }