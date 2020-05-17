
# ================================================
# ================ RESPONSE CODES ================
# ================================================
from easyshare.utils.types import is_str, is_int, is_dict


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