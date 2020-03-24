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


class ErrorCode:
    ERROR = -1
    NOT_CONNECTED = -2
    INVALID_COMMAND_SYNTAX = -3
    SHARING_NOT_FOUND = -4
    INVALID_PATH = -5
    COMMAND_NOT_RECOGNIZED = -6
    COMMAND_EXECUTION_FAILED = -7
    NOT_IMPLEMENTED = -8
    INVALID_TRANSACTION = -9
    UNEXPECTED_SERVER_RESPONSE = -10