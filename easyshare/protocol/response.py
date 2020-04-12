from typing import TypedDict, Optional, Any, Union, Dict

from easyshare.utils.types import is_int

Response = Dict[str, Union[str, bool, Any]]
#   success: bool
#   error: int
#   data: Any


def create_success_response(data=None) -> Response:
    if data is not None:
        return {"success": True, "data": data}

    return {"success": True}


def create_error_response(error_code=None) -> Response:
    if error_code:
        return {"success": False, "error": error_code}

    return {"success": False}


def is_success_response(resp: Response) -> bool:
    return resp and resp.get("success", False) is True


def is_data_response(resp: Response) -> bool:
    return resp and is_success_response(resp) and resp.get("data") is not None


def is_error_response(resp: Response, error_code=None) -> bool:
    return resp and resp.get("success") is False and is_int(resp.get("error"))\
           and (not error_code or resp.get("error") == error_code)


# class Response(Serializable):
#     def __init__(self,
#                  success: bool,
#                  error: Optional[int] = None,
#                  data: Optional[Any] = None):
#         super().__init__()
#         self.success = success
#         self.error = error
#         self.data = data
#
#     @staticmethod
#     def create_success(data=None) -> 'Response':
#         if data is not None:
#             return Response(success=True, data=data)
#
#         return Response(success=True)
#
#     @staticmethod
#     def create_error(error_code=None) -> 'Response':
#         if error_code:
#             return Response(success=False, error=error_code)
#
#         return Response(success=False)
#
#     @staticmethod
#     def is_success(resp: 'Response') -> bool:
#         return resp and resp.success is True
#
#     @staticmethod
#     def is_success_data(resp: 'Response') -> bool:
#         return resp and Response.is_success(resp) and resp.data is not None
#
#     @staticmethod
#     def is_error(resp: 'Response', error_code=None) -> bool:
#         return resp and resp.success is False and is_int(resp.error) \
#                and (not error_code or resp.error == error_code)
#
#     @staticmethod
#     def from_json(d: dict) -> Optional['Response']:
#         return Serializable().parse_json(d)
