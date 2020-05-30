
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

    RCD_PATH = "path"

    RLS_PATH = "path"
    RLS_SORT_BY = "sort_by"
    RLS_REVERSE = "reverse"
    RLS_HIDDEN = "hidden"

    RTREE_PATH = "path"
    RTREE_SORT_BY = "sort_by"
    RTREE_REVERSE = "reverse"
    RTREE_HIDDEN = "hidden"
    RTREE_DEPTH = "depth"

    RMKDIR_PATH = "path"

    RRM_PATHS = "paths"

    RMV_SOURCES = "src"
    RMV_DESTINATION = "dest"

    RCP_SOURCES = "src"
    RCP_DESTINATION = "dest"

    GET_PATHS = "paths"
    GET_CHECK = "check"

    PUT_CHECK = "check"


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