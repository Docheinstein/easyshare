from typing import Union, List

from easyshare.consts import ansi
from easyshare.logging import get_logger
from easyshare.protocol.responses import ServerErrors
from easyshare.utils.inspection import stacktrace
from easyshare.utils.types import is_int, is_str, is_list

log = get_logger(__name__)


# TODO: cleanup - remove unused errors


class ClientErrors:
    """ Client side errors """
    SUCCESS =                         0
    GENERAL_ERROR =                 100
    COMMAND_NOT_RECOGNIZED =        101
    INVALID_COMMAND_SYNTAX =        102
    INVALID_PARAMETER_VALUE =       103
    COMMAND_EXECUTION_FAILED =      104
    UNEXPECTED_SERVER_RESPONSE =    105
    NOT_CONNECTED =                 106
    INVALID_PATH =                  107
    INVALID_DIRECTORY =             108
    SHARING_NOT_FOUND =             109
    SERVER_NOT_FOUND =              110
    IMPLEMENTATION_ERROR =          111
    CONNECTION_ERROR =              112
    PERMISSION_DENIED =             113
    NOT_A_DIRECTORY =               114
    DIRECTORY_ALREADY_EXISTS =      115
    NOT_EXISTS =                    116
    MV_NOT_EXISTS =                 117
    MV_PERMISSION_DENIED =          118
    MV_OTHER_ERROR =                119
    CP_NOT_EXISTS =                 120
    CP_PERMISSION_DENIED =          121
    CP_OTHER_ERROR =                122
    RM_NOT_EXISTS =                 123
    RM_PERMISSION_DENIED =          124
    RM_OTHER_ERROR =                125
    GET_INVALID_DEST_SEMANTIC =     126
    SUPPORTED_ONLY_FOR_UNIX =       127
    UNKNOWN_SETTING_KEY =           128
    HISTORY_FAIL_READ =             129
    HISTORY_FAIL_WRITE =            130
    HISTORY_COMMAND_OUT_OF_BOUND =  131


class ErrorsStrings:
    """
    Error messages; typically for each error code there is an error string,
    but the same string could be associated with more errors
    (e.g. client and server side of a similar error)
    """
    NOT_EXISTS = "Not exists: {}"
    PERMISSION_DENIED = "Permission denied: {}"
    DIRECTORY_ALREADY_EXISTS = "Directory already exists: {}"
    NOT_A_DIRECTORY = "Not a directory: {}"
    INVALID_PATH = "Invalid path: {}"
    SHARING_NOT_FOUND = "Sharing not found: {}"
    TRANSFER_SKIPPED = "Skipped: {}"
    SUCCESS = "Success"
    ERROR = "Error"
    INVALID_COMMAND_SYNTAX = "Invalid command syntax"
    INVALID_PARAMETER_VALUE = "Invalid parameter value"
    NOT_IMPLEMENTED = "Not implemented"
    NOT_CONNECTED = "Not connected"
    COMMAND_EXECUTION_FAILED = "Command execution failed"
    SERVER_NOT_FOUND = "Server not found"
    INVALID_DIRECTORY = "Invalid directory"
    NOT_ALLOWED = "Not allowed"
    AUTHENTICATION_FAILED = "Authentication failed"
    NOT_WRITABLE = "Forbidden: sharing is readonly"
    FILE_NOT_FOUND = "File not found"
    COMMAND_NOT_RECOGNIZED = "Command not recognized"
    UNEXPECTED_SERVER_RESPONSE = "Unexpected server response"
    IMPLEMENTATION_ERROR = "Implementation error"
    CONNECTION_ERROR = "Connection error"
    CONNECTION_CANT_BE_ESTABLISHED = "Connection can't be established"
    NOT_ALLOWED_FOR_F_SHARING = "Not allowed: action can be performed only on sharings of type directory"
    WINDOWS_NOT_SUPPORTED = "Not supported for Windows"
    INVALID_DEST_SEMANTIC = "Invalid --dest semantic"
    SUPPORTED_ONLY_FOR_UNIX = "Supported only for Unix"
    INVALID_REQUEST = "Invalid request"
    UNKNOWN_API = "Unknown command"
    REXEC_DISABLED = "Remote execution is disabled on the server"
    CHECK_FAILED = "CRC check failed"
    REXEC_EXECUTION_FAILED = "Remote execution of command failed"
    UNKNOWN_SETTING = "Unknown setting key"
    HISTORY_FAIL_READ = "Failed to read history"
    HISTORY_FAIL_WRITE = "Failed to write history"
    HISTORY_COMMAND_OUT_OF_BOUND = "History index out of bound"



class SubErrorsStrings:
    CANNOT_MOVE = "cannot move {} to {}"
    CANNOT_COPY = "cannot copy {} to {}"
    CANNOT_REMOVE = "cannot remove {}"


# Maps the errors (any kind of error) to its string
_ERRORS_STRINGS_MAP = {
    ServerErrors.INVALID_COMMAND_SYNTAX: ErrorsStrings.INVALID_COMMAND_SYNTAX,
    ServerErrors.NOT_IMPLEMENTED: ErrorsStrings.NOT_IMPLEMENTED,
    ServerErrors.NOT_CONNECTED: ErrorsStrings.NOT_CONNECTED,
    ServerErrors.COMMAND_EXECUTION_FAILED: ErrorsStrings.COMMAND_EXECUTION_FAILED,
    ServerErrors.SHARING_NOT_FOUND: ErrorsStrings.SHARING_NOT_FOUND,
    ServerErrors.INVALID_PATH: ErrorsStrings.INVALID_PATH,
    ServerErrors.NOT_ALLOWED: ErrorsStrings.NOT_ALLOWED,
    ServerErrors.AUTHENTICATION_FAILED: ErrorsStrings.AUTHENTICATION_FAILED,
    ServerErrors.NOT_WRITABLE: ErrorsStrings.NOT_WRITABLE,
    ServerErrors.NOT_ALLOWED_FOR_F_SHARING: ErrorsStrings.NOT_ALLOWED_FOR_F_SHARING,
    ServerErrors.NOT_A_DIRECTORY: ErrorsStrings.NOT_A_DIRECTORY,
    ServerErrors.PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED,
    ServerErrors.DIRECTORY_ALREADY_EXISTS: ErrorsStrings.DIRECTORY_ALREADY_EXISTS,
    ServerErrors.NOT_EXISTS: ErrorsStrings.NOT_EXISTS,
    ServerErrors.RMV_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_MOVE),
    ServerErrors.RMV_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_MOVE),
    ServerErrors.RMV_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_MOVE,
    ServerErrors.RCP_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_COPY),
    ServerErrors.RCP_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_COPY),
    ServerErrors.RCP_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_COPY,
    ServerErrors.RRM_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_REMOVE),
    ServerErrors.RRM_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_REMOVE),
    ServerErrors.RRM_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_REMOVE,
    ServerErrors.GET_TRANSFER_SKIPPED: ErrorsStrings.TRANSFER_SKIPPED,
    ServerErrors.SUPPORTED_ONLY_FOR_UNIX: ErrorsStrings.SUPPORTED_ONLY_FOR_UNIX,
    ServerErrors.INVALID_REQUEST: ErrorsStrings.INVALID_REQUEST,
    ServerErrors.UNKNOWN_API: ErrorsStrings.UNKNOWN_API,
    ServerErrors.REXEC_DISABLED: ErrorsStrings.REXEC_DISABLED,
    ServerErrors.PUT_CHECK_FAILED: ErrorsStrings.CHECK_FAILED,
    ServerErrors.PUT_INVALID_DEST_SEMANTIC: ErrorsStrings.INVALID_DEST_SEMANTIC,
    ServerErrors.REXEC_EXECUTION_FAILED: ErrorsStrings.REXEC_EXECUTION_FAILED,

    ClientErrors.COMMAND_NOT_RECOGNIZED: ErrorsStrings.COMMAND_NOT_RECOGNIZED,
    ClientErrors.INVALID_COMMAND_SYNTAX: ErrorsStrings.INVALID_COMMAND_SYNTAX,
    ClientErrors.INVALID_PARAMETER_VALUE: ErrorsStrings.INVALID_PARAMETER_VALUE,
    ClientErrors.COMMAND_EXECUTION_FAILED: ErrorsStrings.COMMAND_EXECUTION_FAILED,
    ClientErrors.UNEXPECTED_SERVER_RESPONSE: ErrorsStrings.UNEXPECTED_SERVER_RESPONSE,
    ClientErrors.NOT_CONNECTED: ErrorsStrings.NOT_CONNECTED,
    ClientErrors.INVALID_PATH: ErrorsStrings.INVALID_PATH,
    ClientErrors.INVALID_DIRECTORY: ErrorsStrings.INVALID_DIRECTORY,
    ClientErrors.SHARING_NOT_FOUND: ErrorsStrings.SHARING_NOT_FOUND,
    ClientErrors.SERVER_NOT_FOUND: ErrorsStrings.SERVER_NOT_FOUND,
    ClientErrors.IMPLEMENTATION_ERROR: ErrorsStrings.IMPLEMENTATION_ERROR,
    ClientErrors.CONNECTION_ERROR: ErrorsStrings.CONNECTION_ERROR,
    ClientErrors.PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED,
    ClientErrors.NOT_A_DIRECTORY: ErrorsStrings.NOT_A_DIRECTORY,
    ClientErrors.DIRECTORY_ALREADY_EXISTS: ErrorsStrings.DIRECTORY_ALREADY_EXISTS,
    ClientErrors.NOT_EXISTS: ErrorsStrings.NOT_EXISTS,
    ClientErrors.MV_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_MOVE),
    ClientErrors.MV_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_MOVE),
    ClientErrors.MV_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_MOVE,
    ClientErrors.CP_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_COPY),
    ClientErrors.CP_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_COPY),
    ClientErrors.CP_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_COPY,
    ClientErrors.RM_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_REMOVE),
    ClientErrors.RM_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_REMOVE),
    ClientErrors.RM_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_REMOVE,
    ClientErrors.GET_INVALID_DEST_SEMANTIC: ErrorsStrings.INVALID_DEST_SEMANTIC,
    ClientErrors.SUPPORTED_ONLY_FOR_UNIX: ErrorsStrings.SUPPORTED_ONLY_FOR_UNIX,
    ClientErrors.UNKNOWN_SETTING_KEY: ErrorsStrings.UNKNOWN_SETTING,
    ClientErrors.HISTORY_FAIL_READ: ErrorsStrings.HISTORY_FAIL_READ,
    ClientErrors.HISTORY_FAIL_WRITE: ErrorsStrings.HISTORY_FAIL_WRITE,
    ClientErrors.HISTORY_COMMAND_OUT_OF_BOUND: ErrorsStrings.HISTORY_COMMAND_OUT_OF_BOUND
}


def errno_str(errno: int, *formats) -> str:
    """ Returns the string associated with the error with number 'error_code' """
    errstr = _ERRORS_STRINGS_MAP.get(errno, ErrorsStrings.ERROR)

    if formats:
        try:
            # Special case: general error (variadic)
            if errno == ClientErrors.GENERAL_ERROR or \
                    errno == ServerErrors.GENERAL_ERROR:
                errstr = " : ".join(["{}" for _ in formats])
            if len(formats):
                errstr = errstr.format(*formats)
        except IndexError:
            log.w("Mismatch between subjects and expected string params")
            # Use the errstr as it is

    return errstr


AnyErr = Union[int, str]
AnyErrs = Union[int, str, List[AnyErr]]

def print_errors(err: AnyErrs):
    """
    Prints 'err' if it is a string or the string associated with
    the error 'err' if it is an known errno.
    """
    if err is None:
        return
    if is_list(err):
        for e in err:
            _print_error(e)
    else:
        _print_error(err)


def _print_error(err: AnyErr):
    if is_int(err):
        if err != 0: # 0 is success
            print(errno_str(err))
    elif is_str(err):
        print(err)
    else:
        log.w(f"err expected of type int or str, found {type(err)}")
        log.w(stacktrace(color=ansi.FG_YELLOW))


if __name__ == "__main__":
    print("\n".join([str(s) for s in sorted(_ERRORS_STRINGS_MAP.keys())]))