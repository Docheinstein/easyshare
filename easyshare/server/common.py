from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.response import create_error_response

log = get_logger(__name__)

def try_or_command_failed_response(api):
    def try_or_command_failed_response_wrapper(*vargs, **kwargs):
        try:
            return api(*vargs, **kwargs)
        except Exception:
            log.exception("Exception occurred while executing command")
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

    try_or_command_failed_response_wrapper.__name__ = api.__name__

    return try_or_command_failed_response_wrapper