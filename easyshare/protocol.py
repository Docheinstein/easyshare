from abc import abstractmethod, ABC

from easyshare.tree import TreeNodeDict
from easyshare.utils.types import is_dict, is_int, is_str


# ---------------- CLIENT/SERVER communication shared stuff --------------------

# ================================================
# ================ RESPONSE CODES ================
# ================================================


class ServerErrors:
    ERROR =                     200
    INVALID_COMMAND_SYNTAX =    201
    NOT_IMPLEMENTED =           202
    NOT_CONNECTED =             203
    COMMAND_EXECUTION_FAILED =  204
    SHARING_NOT_FOUND =         205
    INVALID_PATH =              206
    INVALID_TRANSACTION =       207
    NOT_ALLOWED =               208
    AUTHENTICATION_FAILED =     209
    INTERNAL_SERVER_ERROR =     210
    NOT_WRITABLE =              211
    NOT_ALLOWED_FOR_F_SHARING = 212


class TransferOutcomes:
    SUCCESS = 0
    ERROR = 301
    CONNECTION_ESTABLISHMENT_ERROR = 302
    TRANSFER_CLOSED = 303
    CHECK_FAILED = 304


# ================================================
# ================== RESPONSE ====================
# ================================================


try:
    # From python 3.8
    from typing import Literal, TypedDict, Any, Dict, Union, List


    class Response(TypedDict, total=False):
        success: str
        error: int
        data: Any
except:
    Response = Dict[str, Union[str, bool, Any]]


def create_success_response(data=None) -> Response:
    if data is not None:
        return {"success": True, "data": data}

    return {"success": True}

def create_error_response(err: [int, str] = None) -> Response:
    if err:
        return {"success": False, "error": err}

    return {"success": False}

def is_success_response(resp: Response) -> bool:
    return \
        resp and \
        is_dict(resp) and \
        resp.get("success", False) is True

def is_data_response(resp: Response, data_field: str = None) -> bool:
    return \
        resp and \
        is_dict(resp) and \
        is_success_response(resp) and \
        resp.get("data") is not None and \
        (not data_field or data_field in resp.get("data"))

def is_error_response(resp: Response, error_code=None) -> bool:
    return \
        resp and \
        is_dict(resp) and \
        resp.get("success") is False and \
        (is_int(resp.get("error")) or is_str(resp.get("error"))) and \
        (error_code is None or resp.get("error") == error_code)


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

try:
    # From python 3.8
    from typing import TypedDict

    class FileInfo(TypedDict, total=False):
        name: str
        ftype: FileType
        size: int
        mtime: int

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
        # Don't expose IP and port

        name: str
        # ip: str
        # port: int
        # discoverable: bool
        # discover_port: int
        ssl: bool
        auth: bool
        sharings: List[SharingInfo]

    class ServerInfoFull(ServerInfo):
        ip: str
        port: int

        discoverable: bool
        discover_port: int
except:
    ServerInfo = Dict[str, Union[str, int, List[SharingInfo]]]


# ================================================
# ============== OVERWRITE POLICY  ===============
# ================================================


class OverwritePolicy:
    PROMPT = 0
    YES = 1
    NO = 2
    NEWER = 3



# ================================================
# ============= EXPOSED PYRO OBJECTS =============
# ================================================


class ITransferService(ABC):
    @abstractmethod
    def outcome(self) -> Response:
        pass

    @abstractmethod
    def _run(self):
        pass


class IGetService(ITransferService):
    @abstractmethod
    def next(self, transfer: bool = False, skip: bool = False) -> Response:
        pass


class IPutService(ITransferService):
    @abstractmethod
    def next(self, finfo: Union[FileInfo, None],
             overwrite_policy: OverwritePolicy = OverwritePolicy.PROMPT) -> Response:
        pass


class IRexecService(ABC):
    class Event:
        TERMINATE = 0
        EOF = 1

    @abstractmethod
    def recv(self) -> Response:
        pass

    @abstractmethod
    def send_data(self, data: str) -> Response:
        pass

    @abstractmethod
    def send_event(self, ev: int) -> Response:
        pass


class ISharingService(ABC):
    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def rpwd(self) -> Response:
        pass

    @abstractmethod
    def rcd(self, path: str) -> Response:
        pass

    @abstractmethod
    def rls(self, *,
            path: str = None, sort_by: List[str] = None,
            reverse: bool = False, hidden: bool = False, ) -> Response:
        pass

    @abstractmethod
    def rtree(self, *,
              path: str = None, sort_by: List[str] = None,
              reverse: bool = False, hidden: bool = False,
              max_depth: int = None,) -> Response:
        pass

    @abstractmethod
    def rmkdir(self, directory: str) -> Response:
        pass

    @abstractmethod
    def rrm(self, paths: List[str]) -> Response:
        pass

    @abstractmethod
    def rmv(self, sources: List[str], destination: str) -> Response:
        pass

    @abstractmethod
    def rcp(self, sources: List[str], destination: str) -> Response:
        pass

    @abstractmethod
    def get(self, files: List[str], check: bool) -> Response:
        pass

    @abstractmethod
    def put(self, check: bool = False) -> Response:
        pass


class IServer(ABC):
    @abstractmethod
    def connect(self, password: str) -> Response:
        """ New es"""
        pass

    @abstractmethod
    def disconnect(self) -> Response:
        pass

    @abstractmethod
    def list(self) -> Response:
        pass

    @abstractmethod
    def info(self) -> Response:
        pass

    @abstractmethod
    def open(self, sharing_name: str) -> Response:
        """ Opens a sharing """
        pass

    @abstractmethod
    def ping(self) -> Response:
        pass

    @abstractmethod
    def rexec(self, cmd: str) -> Response:
        pass