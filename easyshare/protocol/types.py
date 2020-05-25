from os import stat_result
from pathlib import Path
from stat import S_ISDIR, S_ISREG

from easyshare.logging import get_logger
from easyshare.tree import TreeNodeDict

# Use advanced typing if possible (Literal, TypedDict)
# since offers a better developer experience
# But since they have been implemented only from
# python 3.8 and we support python 3.6, we have
# to do an ugly conditional definition

# ================================================
# ================= FILE INFO  ===================
# ================================================

log = get_logger(__name__)

FTYPE_FILE = "file"
FTYPE_DIR = "dir"

try:
    # From python 3.8
    from typing import Literal, List, Union, Dict, Optional

    FileType = Literal["file", "dir"]
except:
    FileType = str  # "file" | "dir"


def ftype(path: Path, stat = None) -> Optional[FileType]:
    """
    Helper that returns the ftype associated with the path.
    'stat' can be given for avoid a stat() call.
    """
    stat = stat or path.stat()
    if S_ISDIR(stat.st_mode):
        return FTYPE_DIR
    elif S_ISREG(stat.st_mode):
        return FTYPE_FILE
    return None

try:
    # From python 3.8
    from typing import TypedDict

    class FileInfo(TypedDict, total=False):
        """ Information of a file """
        name: str
        ftype: FileType
        size: int
        mtime: int          # last modification time

    class FileInfoTreeNode(FileInfo, TreeNodeDict, total=False):
        pass

except:
    FileInfo = Dict[str, Union[str, FileType, int]]
    FileInfoNode = Dict[str, Union[str, FileType, int, List['FileInfoNode']]]


def create_file_info(path: Path, stat: stat_result = None,
                     name: str = None, raise_exceptions=False) -> Optional[FileInfo]:
    """
    Helper that creates a 'FileInfo' for the given path;
    'stat' can be given for avoid a stat() call.
    If 'name' is given, then it will be used instead of path.name.
    """
    try:
        stat = stat or path.stat()
        return {
            "name": name or path.name,
            "ftype": ftype(path, stat),
            "size": stat.st_size,
            "mtime": stat.st_mtime_ns
        }
    except Exception as ex:
        log.w("Can't create file info - exception occurred")
        if raise_exceptions:
            raise ex
        return None

# ================================================
# ================ SHARING INFO  =================
# ================================================


try:
    # From python 3.8
    from typing import TypedDict

    class SharingInfo(TypedDict):
        """ Information of a sharing """

        name: str
        ftype: FileType
        read_only: bool
        auth: bool
except:
    SharingInfo = Dict[str, Union[str, FileType, bool]]



# ================================================
# ================ SERVER INFO  ==================
# ================================================


try:
    # From python 3.8
    from typing import TypedDict

    class ServerInfo(TypedDict):
        """ Partial information of a server """

        # Don't expose IP, port and discover info

        name: str

        ssl: bool
        auth: bool
        sharings: List[SharingInfo]

    class ServerInfoFull(ServerInfo):
        """ Complete information of a server """

        ip: str
        port: int

        discoverable: bool
        discover_port: int

    # The difference between ServerInfo and ServerInfoFull is that
    # ServerInfo doesn't expose IP, port and discover info since
    # this might be wrong from the client perspective if the server
    # is behind a NAT
    # A ServerInfoFull could be the result of a discover process
    # (since is performed on the same network of the server and thus
    # the ip and port are consistent)
except:
    ServerInfo = Dict[str, Union[str, bool, List[SharingInfo]]]
    ServerInfoFull = Dict[str, Union[str, bool, int, List[SharingInfo]]]


# ================================================
# ============== OVERWRITE POLICY  ===============
# ================================================


class OverwritePolicy:
    PROMPT = 0
    YES = 1
    NO = 2
    NEWER = 3


# ================================================
# ============== PUT NEXT RESPONSE ===============
# ================================================

class PutNextResponse:
    ACCEPTED = "accepted"
    ASK_OVERWRITE = "ask_overwrite"
    REFUSED = "refused"
