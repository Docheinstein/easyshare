from typing import TypedDict, Optional, Any

from easyshare.utils.types import is_dict


class Response(TypedDict):
    success: str
    error: Optional[int]
    data: Optional[Any]


def response_success(data=None) -> Response:
    if data is not None:
        return {
            "success": True,
            "data": data
        }

    return {"success": True}


def response_error(error_code=None) -> Response:
    if error_code:
        return {
            "success": False,
            "error": error_code
        }

    return {"success": False}


def is_response_success(d: dict) -> bool:
    return is_dict(d) and d.get("success") is True


def is_response_success_data(d: dict) -> bool:
    return is_response_success(d) and "data" in d


def is_response_error(d: dict) -> bool:
    return is_dict(d) and d.get("success") is False and "error" in d


