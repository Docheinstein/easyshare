
# ===============================================
# ================== REQUEST ====================
# ===============================================
from easyshare.utils.types import is_dict, is_str
from typing import Any, Dict

class Requests:
    CONNECT = "connect"
    DISCONNECT = "disconnect"

    LIST = "list"
    INFO = "info"
    PING = "ping"

    OPEN = "open"
    CLOSE = "close"

    REXEC = "rexec"
    RSHELL = "rshell"


    RPWD = "rpwd"
    RCD = "rcd"
    RLS = "rls"
    RTREE = "rtree"
    RMKDIR = "rmkdir"
    RRM = "rrm"
    RMV = "rmv"
    RCP = "rcp"

    GET = "get"
    PUT = "put"


class RequestsParams:
    CONNECT_PASSWORD = "password"

    OPEN_SHARING = "sharing"

    REXEC_CMD = "cmd"

    RSHELL_CMD = "cmd"

    RCD_PATH = "path"

    RLS_PATH = "path"
    RLS_SORT_BY = "sort_by"
    RLS_REVERSE = "reverse"
    RLS_HIDDEN = "hidden"
    RLS_DETAILS = "details"

    RTREE_PATH = "path"
    RTREE_SORT_BY = "sort_by"
    RTREE_REVERSE = "reverse"
    RTREE_HIDDEN = "hidden"
    RTREE_DEPTH = "depth"
    RTREE_DETAILS = "details"

    RMKDIR_PATH = "path"

    RRM_PATHS = "paths"

    RMV_SOURCES = "src"
    RMV_DESTINATION = "dest"

    RCP_SOURCES = "src"
    RCP_DESTINATION = "dest"

    GET_PATHS = "paths"
    GET_CHECK = "check"
    GET_NO_HIDDEN = "no_hidden"
    GET_CHUNK_SIZE = "chunk_size"
    GET_MMAP = "mmap"

    GET_NEXT_ACTION = "action"
    GET_NEXT_ACTION_SEEK = "seek"
    GET_NEXT_ACTION_TRANSFER = "transfer"
    GET_NEXT_ACTION_SKIP = "skip"
    GET_NEXT_ACTIONS = [GET_NEXT_ACTION_SEEK, GET_NEXT_ACTION_TRANSFER, GET_NEXT_ACTION_SKIP]

    PUT_CHECK = "check"
    PUT_NO_HIDDEN = "no_hidden"
    PUT_CHUNK_SIZE = "chunk_size"

    PUT_NEXT_FILE = "file"
    PUT_NEXT_OVERWRITE = "overwrite"
    PUT_NEXT_OVERWRITE_PROMPT = "prompt"
    PUT_NEXT_OVERWRITE_YES = "yes"
    PUT_NEXT_OVERWRITE_NO = "no"
    PUT_NEXT_OVERWRITE_NEWER = "newer"
    PUT_NEXT_OVERWRITES = [PUT_NEXT_OVERWRITE_PROMPT, PUT_NEXT_OVERWRITE_YES,
                           PUT_NEXT_OVERWRITE_NO, PUT_NEXT_OVERWRITE_NEWER]

RequestParams = Dict[str, Any]

try:
    # From python 3.8
    from typing import Literal, TypedDict, Union, List, Optional

    class Request(TypedDict, total=False):
        api: str
        params: Dict[str, Any]
except:
    Request = Dict[str, Union[str, RequestParams]]



def create_request(api: str, params: RequestParams = None) -> Request:
    """
    Creates a request:
     {
        'api': <api>
        [, params: {
            'param1': <val>,
            ...
        }]
    }
    """
    req = { "api": api }
    if params:
        req["params"] = params

    return req



def is_request(req: Request) -> bool:
    """ Returns whether 'req' is a valid request """
    return \
        req and \
        is_dict(req) and \
        is_str(req.get("api", None))