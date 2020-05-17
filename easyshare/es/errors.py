from typing import Union

from easyshare.protocol.protocol import ServerErrors, TransferOutcomes
from easyshare.utils.app import eprint
from easyshare.utils.types import is_int, is_str


class ClientErrors:
    COMMAND_NOT_RECOGNIZED =        101
    INVALID_COMMAND_SYNTAX =        102
    INVALID_PARAMETER_VALUE =       103
    COMMAND_EXECUTION_FAILED =      104
    UNEXPECTED_SERVER_RESPONSE =    105
    NOT_CONNECTED =                 106
    INVALID_PATH =                  107
    SHARING_NOT_FOUND =             108
    SERVER_NOT_FOUND =              109
    IMPLEMENTATION_ERROR =          110
    CONNECTION_ERROR =              111


class ErrorsStrings:
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
    INVALID_TRANSACTION = "Invalid transaction"
    NOT_ALLOWED = "Not allowed"
    AUTHENTICATION_FAILED = "Authentication failed"
    INTERNAL_SERVER_ERROR = "Internal esd error"
    NOT_WRITABLE = "Forbidden: sharing is readonly"

    COMMAND_NOT_RECOGNIZED = "Command not recognized"
    UNEXPECTED_SERVER_RESPONSE = "Unexpected esd response"
    IMPLEMENTATION_ERROR = "Implementation error"
    CONNECTION_ERROR = "Connection error"

    TRANSFER_CHECK_FAILED = "Check failed"
    NOT_ALLOWED_FOR_F_SHARING = "Not allowed: action can be performed only on sharings of type directory"




ERRORS_STRINGS_MAP = {
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

    ClientErrors.COMMAND_NOT_RECOGNIZED: ErrorsStrings.COMMAND_NOT_RECOGNIZED,
    ClientErrors.INVALID_COMMAND_SYNTAX: ErrorsStrings.INVALID_COMMAND_SYNTAX,
    ClientErrors.INVALID_PARAMETER_VALUE: ErrorsStrings.INVALID_PARAMETER_VALUE,
    ClientErrors.COMMAND_EXECUTION_FAILED: ErrorsStrings.COMMAND_EXECUTION_FAILED,
    ClientErrors.UNEXPECTED_SERVER_RESPONSE: ErrorsStrings.UNEXPECTED_SERVER_RESPONSE,
    ClientErrors.NOT_CONNECTED: ErrorsStrings.NOT_CONNECTED,
    ClientErrors.INVALID_PATH: ErrorsStrings.INVALID_PATH,
    ClientErrors.SHARING_NOT_FOUND: ErrorsStrings.SHARING_NOT_FOUND,
    ClientErrors.SERVER_NOT_FOUND: ErrorsStrings.SERVER_NOT_FOUND,
    ClientErrors.IMPLEMENTATION_ERROR: ErrorsStrings.IMPLEMENTATION_ERROR,
    ClientErrors.CONNECTION_ERROR: ErrorsStrings.CONNECTION_ERROR,

    TransferOutcomes.SUCCESS: ErrorsStrings.SUCCESS,
    TransferOutcomes.ERROR: ErrorsStrings.ERROR,
    TransferOutcomes.CHECK_FAILED: ErrorsStrings.TRANSFER_CHECK_FAILED
}


def errcode_string(error_code: int) -> str:
    return ERRORS_STRINGS_MAP.get(error_code, ErrorsStrings.ERROR)


def print_errcode(error_code: int):
    eprint(errcode_string(error_code))


def print_error(err: Union[int, str]):
    if is_int(err):
        print_errcode(err)
    elif is_str(err):
        eprint(err)
