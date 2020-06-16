from typing import Union, List

from easyshare.consts import ansi
from easyshare.logging import get_logger
from easyshare.protocol.responses import TransferOutcomes, ServerErrors
from easyshare.utils import eprint
from easyshare.utils.inspection import stacktrace
from easyshare.utils.types import is_int, is_str, is_list

log = get_logger(__name__)


# TODO: cleanup - remove unused errors


class ClientErrors:
    """ Client side errors """
    ERR_0 =                          97
    ERR_1 =                          98
    ERR_2 =                          99

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

    CANNOT_MOVE =                   117
    CANNOT_COPY =                   118

    MV_NOT_EXISTS =                 119
    MV_PERMISSION_DENIED =          120
    MV_OTHER_ERROR =                121

    CP_NOT_EXISTS =                 122
    CP_PERMISSION_DENIED =          123
    CP_OTHER_ERROR =                124


    RM_NOT_EXISTS =                 125
    RM_PERMISSION_DENIED =          126
    RM_OTHER_ERROR =                127

    TRANSFER_CONNECTION_CANT_BE_ESTABLISHED =     128


    SYNC_ONLY_ONE_PARAMETER =       129


class ErrorsStrings:
    """
    Error messages; tipically for each error code there is an error string,
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

    ERR_0 = "Error"
    ERR_1 = "{}"
    ERR_2 = "{}: {}"

    SUCCESS = "Success"
    ERROR = "Error"
    INVALID_COMMAND_SYNTAX = "Invalid command syntax"
    INVALID_PARAMETER_VALUE = "Invalid parameter value"
    NOT_IMPLEMENTED = "Not implemented"
    NOT_CONNECTED = "Not connected"
    COMMAND_EXECUTION_FAILED = "Command execution failed"
    SERVER_NOT_FOUND = "Server not found"
    INVALID_DIRECTORY = "Invalid directory"
    INVALID_TRANSACTION = "Invalid transaction"
    NOT_ALLOWED = "Not allowed"
    AUTHENTICATION_FAILED = "Authentication failed"
    INTERNAL_SERVER_ERROR = "Internal server error"
    NOT_WRITABLE = "Forbidden: sharing is readonly"
    FILE_NOT_FOUND = "File not found"

    COMMAND_NOT_RECOGNIZED = "Command not recognized"
    UNEXPECTED_SERVER_RESPONSE = "Unexpected server response"
    IMPLEMENTATION_ERROR = "Implementation error"
    CONNECTION_ERROR = "Connection error"
    CONNECTION_CANT_BE_ESTABLISHED = "Connection can't be established"
    TRANSFER_CONNECTION_CANT_BE_ESTABLISHED = "Transfer connection can't be established"

    NOT_ALLOWED_FOR_F_SHARING = "Not allowed: action can be performed only on sharings of type directory"
    WINDOWS_NOT_SUPPORTED = "Not supported for Windows"
    SUPPORTED_ONLY_FOR_UNIX = "Supported only for Unix"



class SubErrorsStrings:
    CANNOT_MOVE = "cannot move {} to {}"
    CANNOT_COPY = "cannot copy {} to {}"
    CANNOT_REMOVE = "cannot remove {}"

class TransferOutcomesStrings:
    SUCCESS = "OK"
    ERROR = "ERROR"
    CONNECTION_ESTABLISHMENT_ERROR = "ERROR: connection establishment failed"
    TRANSFER_CLOSED = "ERROR: transfer closed"
    CHECK_FAILED = "ERROR: CRC check failed"


# Maps the errors (any kind of error) to its string
_ERRORS_STRINGS_MAP = {
    ServerErrors.ERR_0: ErrorsStrings.ERR_0,
    ServerErrors.ERR_1: ErrorsStrings.ERR_1,
    ServerErrors.ERR_2: ErrorsStrings.ERR_2,
    ServerErrors.INVALID_COMMAND_SYNTAX: ErrorsStrings.INVALID_COMMAND_SYNTAX,
    ServerErrors.NOT_IMPLEMENTED: ErrorsStrings.NOT_IMPLEMENTED,
    ServerErrors.NOT_CONNECTED: ErrorsStrings.NOT_CONNECTED,
    ServerErrors.COMMAND_EXECUTION_FAILED: ErrorsStrings.COMMAND_EXECUTION_FAILED,
    ServerErrors.SHARING_NOT_FOUND: ErrorsStrings.SHARING_NOT_FOUND,
    ServerErrors.INVALID_PATH: ErrorsStrings.INVALID_PATH,
    ServerErrors.INVALID_TRANSACTION: ErrorsStrings.INVALID_TRANSACTION,
    ServerErrors.NOT_ALLOWED: ErrorsStrings.NOT_ALLOWED,
    ServerErrors.AUTHENTICATION_FAILED: ErrorsStrings.AUTHENTICATION_FAILED,
    ServerErrors.INTERNAL_SERVER_ERROR: ErrorsStrings.INTERNAL_SERVER_ERROR,
    ServerErrors.NOT_WRITABLE: ErrorsStrings.NOT_WRITABLE,
    ServerErrors.NOT_ALLOWED_FOR_F_SHARING: ErrorsStrings.NOT_ALLOWED_FOR_F_SHARING,
    ServerErrors.NOT_A_DIRECTORY: ErrorsStrings.NOT_A_DIRECTORY,
    ServerErrors.PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED,
    ServerErrors.DIRECTORY_ALREADY_EXISTS: ErrorsStrings.DIRECTORY_ALREADY_EXISTS,
    ServerErrors.NOT_EXISTS: ErrorsStrings.NOT_EXISTS,

    ServerErrors.MV_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_MOVE),
    ServerErrors.MV_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_MOVE),
    ServerErrors.MV_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_MOVE,

    ServerErrors.CP_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_COPY),
    ServerErrors.CP_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_COPY),
    ServerErrors.CP_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_COPY,

    ServerErrors.RM_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_REMOVE),
    ServerErrors.RM_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_REMOVE),
    ServerErrors.RM_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_REMOVE,

    ServerErrors.TRANSFER_SKIPPED: ErrorsStrings.TRANSFER_SKIPPED,

    ServerErrors.SUPPORTED_ONLY_FOR_UNIX: ErrorsStrings.SUPPORTED_ONLY_FOR_UNIX,

    ClientErrors.ERR_0: ErrorsStrings.ERR_0,
    ClientErrors.ERR_1: ErrorsStrings.ERR_1,
    ClientErrors.ERR_2: ErrorsStrings.ERR_2,
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
    ClientErrors.NOT_EXISTS: ErrorsStrings.NOT_EXISTS,

    ClientErrors.TRANSFER_CONNECTION_CANT_BE_ESTABLISHED: ErrorsStrings.TRANSFER_CONNECTION_CANT_BE_ESTABLISHED,

    ClientErrors.MV_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_MOVE),
    ClientErrors.MV_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_MOVE),
    ClientErrors.MV_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_MOVE,

    ClientErrors.CP_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_COPY),
    ClientErrors.CP_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_COPY),
    ClientErrors.CP_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_COPY,

    ClientErrors.RM_NOT_EXISTS: ErrorsStrings.NOT_EXISTS.format(SubErrorsStrings.CANNOT_REMOVE),
    ClientErrors.RM_PERMISSION_DENIED: ErrorsStrings.PERMISSION_DENIED.format(SubErrorsStrings.CANNOT_REMOVE),
    ClientErrors.RM_OTHER_ERROR: "{}: " + SubErrorsStrings.CANNOT_REMOVE,

}

_OUTCOMES_STRINGS_MAP = {
    TransferOutcomes.SUCCESS: TransferOutcomesStrings.SUCCESS,
    TransferOutcomes.ERROR: TransferOutcomesStrings.ERROR,
    TransferOutcomes.CONNECTION_ESTABLISHMENT_ERROR: TransferOutcomesStrings.CONNECTION_ESTABLISHMENT_ERROR,
    TransferOutcomes.TRANSFER_CLOSED: TransferOutcomesStrings.TRANSFER_CLOSED,
    TransferOutcomes.CHECK_FAILED: TransferOutcomesStrings.CHECK_FAILED
}

def errno_str(errno: int, *formats) -> str:
    """ Returns the string associated with the error with number 'error_code' """
    errstr = _ERRORS_STRINGS_MAP.get(errno, ErrorsStrings.ERROR)

    if formats:
        try:
            errstr = errstr.format(*formats)
        except IndexError:
            log.w("Mismatch between subjects and expected string params")
            # Use the err_str as it is

    return errstr


def outcome_str(outcomeno: int) -> str:
    return _OUTCOMES_STRINGS_MAP.get(outcomeno, ErrorsStrings.ERROR)


def print_errors(err: Union[int, str, List[Union[int, str]]]):
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


def _print_error(err: Union[int, str]):
    if is_int(err):
        if err != 0: # 0 is success
            print(errno_str(err))
    elif is_str(err):
        print(err)
    else:
        log.w("err expected of type int or str, found %s", type(err))
        log.w(stacktrace(color=ansi.FG_YELLOW))
