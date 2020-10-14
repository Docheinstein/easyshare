
# ================================================
# ================ RESPONSE CODES ================
# ================================================

from typing import Any, Dict, Union, List, Optional
from easyshare.utils.types import is_str, is_int, is_dict, is_list, is_valid_list


class ServerErrors:
    """ Server side errors """
    GENERAL_ERROR =             200

    UNKNOWN_API =               201
    INVALID_REQUEST =           202
    INVALID_COMMAND_SYNTAX =    203
    NOT_IMPLEMENTED =           204
    COMMAND_EXECUTION_FAILED =  205

    NOT_CONNECTED =             206
    NOT_ALLOWED =               207
    AUTHENTICATION_FAILED =     208
    SUPPORTED_ONLY_FOR_UNIX =   209

    SHARING_NOT_FOUND =         210
    INVALID_PATH =              211
    NOT_WRITABLE =              212
    NOT_ALLOWED_FOR_F_SHARING = 213
    NOT_A_DIRECTORY =           214
    PERMISSION_DENIED =         215
    DIRECTORY_ALREADY_EXISTS =  216
    NOT_EXISTS =                217

    MV_NOT_EXISTS =             218
    MV_PERMISSION_DENIED =      219
    MV_OTHER_ERROR =            220

    CP_NOT_EXISTS =             221
    CP_PERMISSION_DENIED =      222
    CP_OTHER_ERROR =            223

    RM_NOT_EXISTS =             224
    RM_PERMISSION_DENIED =      225
    RM_OTHER_ERROR =            226

    GET_TRANSFER_SKIPPED =      227

    PUT_CHECK_FAILED =          228
    PUT_INVALID_DEST_SEMANTIC = 229

    REXEC_DISABLED =            230
    REXEC_EXECUTION_FAILED =    231


class ResponsesParams:
    GET_NEXT_FILE = "file"
    GET_OUTCOME = "outcome"
    GET_ERRORS = "errors"

    PUT_OUTCOME = "outcome"
    PUT_ERRORS = "errors"
    PUT_SYNC_OKS = "sync_oks"
    PUT_SYNC_ERRORS = "sync_errors"

    PUT_NEXT_FILE_INFO = "file"
    PUT_NEXT_ALREADY_EXISTS = "exists"
    PUT_NEXT_STATUS = "status"
    PUT_NEXT_STATUS_ACCEPTED = "accepted" # e.g. does not exists
    PUT_NEXT_STATUS_REFUSED = "refused" # e.g. already exists and overwrite == "newer"
    PUT_NEXT_STATUS_UNCERTAIN = "uncertain" # e.g. already exists and overwrite == "prompt"



# ================================================
# ================== RESPONSE ====================
# ================================================


try:
    # From python 3.8
    from typing import TypedDict

    class ResponseError(TypedDict, total=False):
        errno: int
        subjects: List[str]

    class Response(TypedDict, total=False):
        success: str
        errors: List[ResponseError]
        data: Any
except:
    ResponseError = Dict[str, Union[int, List[Dict]]]
    Response = Dict[str, Union[str, List[ResponseError], Any]]


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

    # Try to create from err (works if it's int or str)
    if subjects:
        resp_err = create_error_of_response(err, *subjects)
    else:
        resp_err = create_error_of_response(err)

    if resp_err:
        errors.append(resp_err)

    # We can handle a ResponseError or a list of ResponseError as well
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

def create_error_of_response(err: Union[int, str], *subjects) -> Optional[ResponseError]:
    if is_int(err):
        # Consider err as an error number
        if not subjects:
            return {"errno": err}
        return {"errno": err, "subjects": [str(s) for s in subjects] }

    if is_str(err):
        # Consider err as a reason of a SPECIFIED_ERROR
        return {"errno": ServerErrors.GENERAL_ERROR, "subjects": err}

    return None


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
