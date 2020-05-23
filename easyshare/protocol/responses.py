
# ================================================
# ================ RESPONSE CODES ================
# ================================================

from easyshare.utils.types import is_str, is_int, is_dict, is_list, is_valid_list


class ServerErrors:
    """ Server side errors """
    UNSPECIFIED_ERROR =         200 # 0
    SPECIFIED_ERROR =           201 # 1
    INVALID_COMMAND_SYNTAX =    202 # 0
    NOT_IMPLEMENTED =           203 # 0
    NOT_CONNECTED =             204 # 0
    COMMAND_EXECUTION_FAILED =  205 # 0
    SHARING_NOT_FOUND =         206 # 1
    INVALID_PATH =              207 # 1
    INVALID_TRANSACTION =       208
    NOT_ALLOWED =               209 # 0
    AUTHENTICATION_FAILED =     210
    INTERNAL_SERVER_ERROR =     211
    NOT_WRITABLE =              212
    NOT_ALLOWED_FOR_F_SHARING = 213
    NOT_A_DIRECTORY =           214
    PERMISSION_DENIED =         215
    DIRECTORY_ALREADY_EXISTS =  216


class TransferOutcomes:
    """ Possibles results of outcome() of a 'TransferService' """
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

    class ResponseError(TypedDict, total=False):
        errno: int
        subjects: List[str]

    class Response(TypedDict, total=False):
        success: str
        errors: List[ResponseError]
        data: Any
except:
    Response = Dict[str, Union[str, List[Dict], Any]]


def create_success_response(data=None) -> Response:
    """
    Creates a success response:
     {
        'success': true
        [, data: <DATA>]
    }
    """
    if data is not None:
        return {"success": True, "data": data}

    return {"success": True}


def create_error_response(err: Union[str, int, Dict, List[Dict]] = None, *subjects) -> Response:
    """
    Creates an error response:
     {
        'success': false

        # OPTIONALLY
        'errors': [
            {'errno': <ERRNO>, subjects: [arg1, arg2, ...],
            {'errno': <ERRNO>, subjects: [arg1, arg2, ...]
        ]
    }

    'err' could be passed as
    - errno (int)
    - string (=> SPECIFIED_ERROR)
    - dict of the form {errno: <>, subjects: <>}
    - list of dict of the form {errno: <>, subjects: <>}
    'subjects' makes sense only if err is int

    """
    if not err:
        return {"success": False}

    # Build "errors"
    errors = []
    if is_int(err):
        # Consider err as error number
        if subjects:
            errors.append({"errno": err, "subjects": subjects})
        else:
            errors.append({"errno": err})
    elif is_str(err):
        # Consider err as a reason for a SPECIFIED_ERROR
        errors.append({"errno": ServerErrors.SPECIFIED_ERROR, "subjects": err})
    elif is_dict(err):
        # Must have at least errno, subjects is optional
        if "errno" not in err:
            raise TypeError("err provided has dict must have at least errno field")
        errors.append(err)
    elif is_list(err):
        for an_err in err:
            # Must have at least errno, subjects is optional
            if "errno" not in an_err:
                raise TypeError("err provided has dict must have at least errno field")
            errors.append(an_err)
    else:
        raise TypeError("err expected as int, list, dict or list")

    if not errors:
        # Should not happen, but for example err = [] is passed can happen,
        # therefore deliver a success=False without errors field
        return {"success": False}

    return {"success": False, "errors": errors}


def is_success_response(resp: Response) -> bool:
    """ Returns whether 'resp' is a success response """
    return \
        resp and \
        is_dict(resp) and \
        resp.get("success", False) is True

def is_data_response(resp: Response, data_field: str = None) -> bool:
    """
    Returns whether 'resp' is a success response with the 'data' key.
    If 'data_field' is not None, the data dict must contain it.
    """

    return \
        resp and \
        is_dict(resp) and \
        is_success_response(resp) and \
        resp.get("data") is not None and \
        (not data_field or data_field in resp.get("data"))

def is_error_response(resp: Response, errno=None) -> bool:
    """
    Returns whether 'resp' is an error response.
    If 'errno' is not None, the value of an errno must match it
    """

    if not resp or not is_dict(resp) or resp.get("success") is not False:
        return False

    # Is an error response

    if errno is None:
        # No check on errno
        return True

    # errno specified, check if it match at least an errno
    errors = resp.get("errors")
    if not is_valid_list(errors):
        return False

    for er in errors:
        if er.get("errno") == errno:
            return True

    return False