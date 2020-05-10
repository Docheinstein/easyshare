from typing import Optional

from Pyro5 import api as pyro

from easyshare.endpoint import Endpoint
from easyshare.logging import get_logger
from easyshare.protocol import Response, create_error_response, ServerErrors
from easyshare.tracing import trace_in, trace_out
from easyshare.utils.inspection import func_args_to_str


log = get_logger(__name__)


def pyro_client_endpoint() -> Endpoint:
    return pyro.current_context.client_sock_addr


def trace_api(api):
    def trace_api_wrapper(pyro_obj, *vargs, **kwargs) -> Optional[Response]:
        requester = pyro_client_endpoint()

        api_name = pyro_obj.__class__.__name__ + "." + api.__name__
        trace_in("{} ({})".format(api_name, func_args_to_str(vargs, kwargs)),
                 ip=requester[0],
                 port=requester[1])

        resp = api(pyro_obj, *vargs, **kwargs)

        if resp:
            trace_out("{}\n{}".format(api_name, j(resp)),
                      ip=requester[0],
                      port=requester[1])
        # else: should be a one-way call without response
        return resp

    trace_api_wrapper.__name__ = api.__name__

    return trace_api_wrapper


def try_or_command_failed_response(api):
    def try_or_command_failed_response_wrapper(*vargs, **kwargs):
        try:
            return api(*vargs, **kwargs)
        except Exception:
            log.exception("Exception occurred while executing command")
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

    try_or_command_failed_response_wrapper.__name__ = api.__name__

    return try_or_command_failed_response_wrapper