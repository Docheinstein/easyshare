from easyshare.tree import TreeNodeDict

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
    from typing import Literal, List, Union, Dict

    FileType = Literal["file", "dir"]
except:
    FileType = str  # "file" | "dir"

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
