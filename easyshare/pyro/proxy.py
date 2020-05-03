# from typing import Any, TypeVar, Callable
#
# from Pyro5 import api as pyro
#
# from easyshare.tracing import is_tracing_enabled, trace_out, trace_in
#
# from easyshare.protocol.response import Response
# from easyshare.shared.endpoint import Endpoint
# from easyshare.tracing import trace_in, trace_out
# from easyshare.utils.json import json_to_pretty_str
# from easyshare.utils.trace import args_to_str
#
# class TracedProxy(pyro.Proxy):
#
#     LOCAL_ATTR_PREFIX = "_easyshare"
#
#     def __init__(self, uri, **kwargs):
#         super().__init__(uri)
#
#         self._easyshare_remote_alias = kwargs.get("alias")
#
#     def _pyroInvoke(self, methodname, vargs, kwargs, flags=0, objectId=None) -> Any:
#         remote = self._pyroConnection.sock.getsockname()
#
#         if is_tracing_enabled():
#             trace_out("{} ({})".format(methodname, args_to_str(vargs, kwargs)),
#                       ip=remote[0],
#                       port=remote[1],
#                       alias=self._easyshare_remote_alias)
#
#         resp = super()._pyroInvoke(methodname, vargs, kwargs, flags, objectId)
#
#         if is_tracing_enabled() and resp:
#             trace_in("{}\n{}".format(methodname, json_to_pretty_str(resp)),
#                      ip=remote[0],
#                      port=remote[1],
#                      alias=self._easyshare_remote_alias)
#
#         return resp
#
#     def __setattr__(self, key, value):
#         if key.startswith(TracedProxy.LOCAL_ATTR_PREFIX):
#             return super(Pyro4.Proxy, self).__setattr__(key, value)   # local attributes
#         return super().__setattr__(key, value)                        # dispatch to pyro
#
#
#
# def current_request_endpoint() -> Endpoint:
#     return pyro.current_context.client_sock_addr
#
#
# API = TypeVar('API', bound=Callable[..., Any])
#
#
# def expose(api: API) -> API:
#     def expose_wrapper(pyro_obj, *vargs, **kwargs) -> Optional[Response]:
#         requester = current_request_endpoint()
#
#         api_name = pyro_obj.__class__.__name__ + "." + api.__name__
#         trace_in("{} ({})".format(api_name, args_to_str(vargs, kwargs)),
#                  ip=requester[0],
#                  port=requester[1])
#
#         resp = api(pyro_obj, *vargs, **kwargs)
#
#         if resp:
#             trace_out("{}\n{}".format(api_name, json_to_pretty_str(resp)),
#                       ip=requester[0],
#                       port=requester[1])
#         # else: should be a one-way call without response
#         return resp
#
#     expose_wrapper.__name__ = api.__name__
#     expose_wrapper._pyroExposed = True
#
#     return expose_wrapper