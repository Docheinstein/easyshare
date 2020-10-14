from os import stat_result
from typing import List, Union, Dict, Optional
from pathlib import Path
from stat import S_ISDIR, S_ISREG

from easyshare.utils.env import is_unix
from easyshare.utils.types import itob
from easyshare.logging import get_logger
from easyshare.tree import TreeNodeDict


if is_unix():
    from pwd import getpwuid
    from grp import getgrgid

log = get_logger(__name__)


# Use advanced typing if possible (Literal, TypedDict)
# since offers a better developer experience
# But since they have been implemented only from
# python 3.8 and we support python 3.6, we have
# to do an ugly conditional definition

# ================================================
# ================= FILE INFO  ===================
# ================================================


FTYPE_FILE = "file"
FTYPE_DIR = "dir"

try:
    # From python 3.8
    from typing import Literal

    FileType = Literal["file", "dir"]
except:
    FileType = str  # "file" | "dir"


def ftype_of(path: Path, stat = None) -> Optional[FileType]:
    """
    Helper that returns the ftype associated with the path.
    'stat' can be given for avoid a stat() call.
    """
    try:
        stat = stat or path.stat()
        if S_ISDIR(stat.st_mode):
            return FTYPE_DIR
        elif S_ISREG(stat.st_mode):
            return FTYPE_FILE
    except:
        pass
    return None

try:
    # From python 3.8
    from typing import TypedDict

    class FileInfo(TypedDict, total=False):
        """ Information of a file """
        name: str           # usually the filename
        ftype: FileType     # "file" or "dir"
        size: int           # size in bytes
        mtime: int          # last modification time
        perm: str           # permissions
        user: str           # user owner
        group: str          # group owner

    class FileInfoTreeNode(FileInfo, TreeNodeDict, total=False):
        pass

except:
    FileInfo = Dict[str, Union[str, FileType, int]]
    FileInfoTreeNode = Dict[str, Union[str, FileType, int, List['FileInfoTreeNode']]]


_users_cache = {}
_groups_cache = {}

def create_file_info(path: Path, *,
                     fstat: stat_result = None,
                     name: str = None,
                     fetch_size: bool = True,
                     fetch_time: bool = True,
                     fetch_perm: bool = False,
                     fetch_owner: bool = False,
                     raise_exceptions: bool = False) -> Optional[FileInfo]:
    """
    Helper that creates a 'FileInfo' for the given path;
    'stat' can be given for avoid a stat() call.
    If 'name' is given, then it will be used instead of path.name.
    """
    try:
        fstat = fstat or path.stat()
        finfo = {
            "name": name or path.name,
            "ftype": ftype_of(path, fstat),
        }

        if fetch_size:
            finfo["size"] = fstat.st_size
        if fetch_time:
            finfo["mtime"] = fstat.st_mtime_ns
        if fetch_perm:
            finfo["perm"] = oct(fstat.st_mode & 0o777)[-3:]

        if fetch_owner:
            user_name = _users_cache.get(fstat.st_uid)
            if not user_name:
                try:
                    user_name = getpwuid(fstat.st_uid).pw_name
                except:
                    # Don't fail globally if user name can't be retrieved (permission problems?)
                    # User the UID as fallback
                    log.w(f"User name for UID {fstat.st_uid} can't be retrieved, "
                          "using itself as fallback")
                    user_name = str(fstat.st_uid)
                _users_cache[fstat.st_uid] = user_name
                log.i(f"UID {fstat.st_gid} = '{user_name}'")

            group_name = _groups_cache.get(fstat.st_gid)
            if not group_name:
                try:
                    group_name = getgrgid(fstat.st_gid).gr_name
                except:
                    # Don't fail globally if group id can't be retrieved (permission problems?)
                    # User the UID as fallback
                    log.w(f"Group name for GID {fstat.st_gid} can't be retrieved, "
                          "using itself as fallback")
                    group_name = str(fstat.st_gid)
                _groups_cache[fstat.st_gid] = group_name
                log.i(f"GID {fstat.st_gid} = '{group_name}'")

            finfo["user"] = user_name
            finfo["group"] = group_name


        return finfo

    except Exception as ex:
        log.w(f"Can't create file info - exception occurred: {ex}")
        if raise_exceptions:
            raise ex
        return None

def create_file_info_full(path: Path, *,
                     fstat: stat_result = None,
                     name: str = None,
                     raise_exceptions: bool = False):
    return create_file_info(
        path,
        fstat=fstat,
        name=name,
        fetch_size=True,
        fetch_time=True,
        fetch_perm=True,
        fetch_owner=True,
        raise_exceptions=raise_exceptions
    )

# ================================================
# ================ SHARING INFO  =================
# ================================================


try:
    # From python 3.8
    from typing import TypedDict

    class SharingInfo(TypedDict, total=False):
        """ Information of a sharing """

        name: str
        ftype: FileType
        read_only: bool
        # auth: bool
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




# ================================================
# ============== PUT NEXT RESPONSE ===============
# ================================================

class PutNextResponse:
    ACCEPTED = "accepted"
    ASK_OVERWRITE = "ask_overwrite"
    REFUSED = "refused"


class RexecEventType:
    DATA =      0
    DATA_B =    itob(DATA, length=1)

    RETCODE =   1
    RETCODE_B = itob(RETCODE, length=1)

    KILL =      2
    KILL_B =    itob(KILL, length=1)

    EOF =       3
    EOF_B =     itob(EOF, length=1)

    ENDACK =    255
    ENDACK_B =  itob(ENDACK, length=1)
