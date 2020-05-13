from typing import Any

from Pyro5 import api as pyro

from easyshare.tracing import trace_out, is_tracing_enabled, trace_in
from easyshare.utils.inspection import func_args_to_str
from easyshare.utils.json import j


class TracedPyroProxy(pyro.Proxy):

    LOCAL_ATTR_PREFIX = "_easyshare"

    def __init__(self, uri, **kwargs):
        super().__init__(uri)

        self._easyshare_remote_alias = kwargs.get("alias")

    def _pyroInvoke(self, methodname, Pargs, kwargs, flags=0, objectId=None) -> Any:

        remote = self._pyroConnection.sock.getpeername()

        if is_tracing_enabled():
            trace_out("{} ({})".format(methodname, func_args_to_str(vargs, kwargs)),
                      ip=remote[0],
                      port=remote[1],
                      alias=self._easyshare_remote_alias)

        resp = super()._pyroInvoke(methodname, vargs, kwargs, flags, objectId)

        if is_tracing_enabled() and resp:
            trace_in("{}\n{}".format(methodname, j(resp)),
                     ip=remote[0],
                     port=remote[1],
                     alias=self._easyshare_remote_alias)

        return resp

    def __setattr__(self, key, value):
        if key.startswith(TracedPyroProxy.LOCAL_ATTR_PREFIX):
            return super(pyro.Proxy, self).__setattr__(key, value)   # local attributes
        return super().__setattr__(key, value)                        # dispatch to pyro
