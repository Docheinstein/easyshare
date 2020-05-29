
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

    LS = "ls"


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