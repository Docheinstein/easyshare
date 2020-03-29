from typing import Optional, Any, TypedDict

class ServerResponse(TypedDict):
    success: str
    error: Optional[int]
    data: Optional[Any]



def build_server_response_success(data=None):
    if data is not None:
        return {
            "success": True,
            "data": data
        }

    return {"success": True}


def build_server_response_error(error_code=None):
    if error_code:
        return {
            "success": False,
            "error": error_code
        }

    return {"success": False}


def is_server_response_success(j: dict):
    return isinstance(j, dict) and j.get("success") is True


def is_server_response_error(j: dict):
    return not is_server_response_success(j)


