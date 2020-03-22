from typing import Optional, Any, TypedDict


class EasyshareServerResponse(TypedDict):
    success: str
    error: Optional[int]
    data: Optional[Any]


SERVER_RESPONSE_SUCCESS = {"success": True}
SERVER_RESPONSE_ERROR = {"success": False}

def build_server_response_success(data=None):
    if data:
        return {
            "success": True,
            "data": data
        }

    return SERVER_RESPONSE_SUCCESS


def build_server_response_error(error_code=None):
    if error_code:
        return {
            "success": False,
            "error": error_code
        }

    return SERVER_RESPONSE_ERROR


def is_server_response_success(j: dict):
    return isinstance(j, dict) and j.get("success") is True

def is_server_response_error(j: dict):
    return not is_server_response_success(j)
