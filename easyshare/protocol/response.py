from typing import TypedDict, Optional, Any, Union, Dict, TypeVar, Generic

from easyshare.utils.types import is_int, is_dict

try:
    # From python 3.8
    from typing import Literal


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


def create_error_response(error_code=None) -> Response:
    if error_code:
        return {"success": False, "error": error_code}

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
        is_int(resp.get("error")) and \
        (not error_code or resp.get("error") == error_code)