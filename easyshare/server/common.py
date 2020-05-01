from typing import TypeVar, Callable, Any, Optional

import Pyro4

from easyshare.protocol.response import Response
from easyshare.shared.endpoint import Endpoint
from easyshare.tracing import trace_in, trace_out
from easyshare.utils.json import json_to_pretty_str
from easyshare.utils.trace import args_to_str

API = TypeVar('API', bound=Callable[..., Any])


def current_request_endpoint() -> Endpoint:
    return Pyro4.current_context.client_sock_addr


def trace_pyro_api(api: API) -> API:

    def trace_pyro_api_wrapper(pyro_obj, *vargs, **kwargs) -> Optional[Response]:
        requester = current_request_endpoint()

        api_name = pyro_obj.__class__.__name__ + "." + api.__name__
        trace_in("{} ({})".format(api_name, args_to_str(vargs, kwargs)),
                 ip=requester[0],
                 port=requester[1])

        resp = api(pyro_obj, *vargs, **kwargs)

        if resp:
            trace_out("{}\n{}".format(api_name, json_to_pretty_str(resp)),
                      ip=requester[0],
                      port=requester[1])
        # else: should be a one-way call without response
        return resp

    return trace_pyro_api_wrapper
