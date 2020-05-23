from typing import Union

from easyshare.protocol.responses import TransferOutcomes, ServerErrors
from easyshare.utils import eprint
from easyshare.utils.types import is_int, is_str


class ClientErrors:
    # TODO: probably we have to delete these
    """ Client side errors """
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


class ErrorsStrings:
    """
    Error messages; tipically for each error code there is an error string,
    but the same string could be associated with more errors
    (e.g. client and server side of a similar error)
    """
    SUCCESS = "Success"
    ERROR = "Error"
    INVALID_COMMAND_SYNTAX = "Invalid command syntax"
    INVALID_PARAMETER_VALUE = "Invalid parameter value"
    NOT_IMPLEMENTED = "Not implemented"
    NOT_CONNECTED = "Not connected"
    COMMAND_EXECUTION_FAILED = "Command execution failed"
    SHARING_NOT_FOUND = "Sharing not found"
    SERVER_NOT_FOUND = "Server not found"
    INVALID_PATH = "Invalid path"
    INVALID_DIRECTORY = "Invalid directory"
    INVALID_TRANSACTION = "Invalid transaction"
    NOT_ALLOWED = "Not allowed"
    AUTHENTICATION_FAILED = "Authentication failed"
    INTERNAL_SERVER_ERROR = "Internal esd error"
    NOT_WRITABLE = "Forbidden: sharing is readonly"
    FILE_NOT_FOUND = "File not found"
    NOT_EXISTS = "Not exists"

    COMMAND_NOT_RECOGNIZED = "Command not recognized"
    UNEXPECTED_SERVER_RESPONSE = "Unexpected esd response"
    IMPLEMENTATION_ERROR = "Implementation error"
    CONNECTION_ERROR = "Connection error"
    CONNECTION_CANT_BE_ESTABLISHED = "Connection can't be established"

    TRANSFER_CHECK_FAILED = "Check failed"
    NOT_ALLOWED_FOR_F_SHARING = "Not allowed: action can be performed only on sharings of type directory"
    PERMISSION_DENIED = "Permission denied"
    NOT_A_DIRECTORY = "Not a directory"
    DIRECTORY_ALREADY_EXISTS = "Directory already exists"
    WINDOWS_NOT_SUPPORTED = "Not supported for Windows"
    SUPPORTED_ONLY_FOR_UNIX = "Supported only for Unix"


# Maps the errors (any kind of error) to its string
_ERRORS_STRINGS_MAP = {
    ServerErrors.ERROR: ErrorsStrings.ERROR,
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

    TransferOutcomes.SUCCESS: ErrorsStrings.SUCCESS,
    TransferOutcomes.ERROR: ErrorsStrings.ERROR,
    TransferOutcomes.CHECK_FAILED: ErrorsStrings.TRANSFER_CHECK_FAILED
}


def errno_str(errno: int) -> str:
    """ Returns the string associated with the error with number 'error_code' """
    return _ERRORS_STRINGS_MAP.get(errno, ErrorsStrings.ERROR)


def print_errno(errno: int):
    """ Prints the string associated with the error with number 'errno' """
    eprint(errno_str(errno))


def print_error(err: Union[int, str]):
    """
    Prints 'err' if it is a string or the string associated with
    the error 'err' if it is an known errno.
    """
    if is_int(err):
        print_errno(err)
    elif is_str(err):
        eprint(err)
