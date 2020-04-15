from typing import Any

from Pyro4 import Proxy

from easyshare.protocol.serverinfo import ServerInfo
from easyshare.shared.trace import is_tracing_enabled, trace_out, trace_in
from easyshare.utils.json import json_to_str
from easyshare.utils.str import strstr


class ServerProxy(Proxy):

    LOCAL_ATTR_PREFIX = "_server"

    def __init__(self, server_info: ServerInfo):
        super().__init__(server_info.get("uri"))
        self._server_uri = server_info.get("uri")
        self._server_ip = server_info.get("ip")
        self._server_port = server_info.get("port")
        self._server_name = server_info.get("name")

    def _pyroInvoke(self, methodname, vargs, kwargs, flags=0, objectId=None) -> Any:

        # print("_pyroInvoke: " + methodname)
        # print("args: ", str(inspect.getargs(inspect.currentframe())))
        # print("getargvalues: ", str(inspect.getargvalues(inspect.currentframe())))

        if is_tracing_enabled():
            remote_function_args_str = "{}{}".format(
                ", ".join([strstr(x) for x in vargs]) if vargs else "",
                ", ".join([str(k) + "=" + strstr(v) for k, v in kwargs.items()]) if kwargs else ""
            )
            trace_out("{} ({})".format(methodname, remote_function_args_str),
                      ip=self._server_ip,
                      port=self._server_port,
                      alias=self._server_name)

        resp = super()._pyroInvoke(methodname, vargs, kwargs, flags, objectId)

        if is_tracing_enabled() and resp:
            trace_in("{}\n{}".format(methodname, json_to_str(resp, pretty=True)),
                     ip=self._server_ip,
                     port=self._server_port,
                     alias=self._server_name)

        return resp

    def __setattr__(self, key, value):
        if key.startswith(ServerProxy.LOCAL_ATTR_PREFIX):
            return super(Proxy, self).__setattr__(key, value)   # local attributes
        return super().__setattr__(key, value)                  # dispatch to pyro
