from typing import Any

from Pyro5 import api as pyro

from easyshare.utils.inspection import func_args_to_str
from easyshare.utils.json import j


class TracedPyroProxy(pyro.Proxy):
    """
    Extends the Pyro.Proxy by tracing the packets sent and received,
    dumping those if trace is enabled.
    """

    # Special prefix for easyshare fields that should not be
    # serialized by pyro
    _EASYSHARE_ATTR_PREFIX = "_easyshare"

    def __init__(self, uri, **kwargs):
        # If kwargs contains "alias", it will be used will dumping the packets
        # to screen as display name of the remote host
        super().__init__(uri)

        self._easyshare_remote_alias = kwargs.get("alias")

    def _pyroInvoke(self, methodname, vargs, kwargs, flags=0, objectId=None) -> Any:

        remote = self._pyroConnection.sock.getpeername()

        # TRACE OUT
        # if is_tracing_enabled():
        #     trace_out("{} ({})".format(methodname, func_args_to_str(vargs, kwargs)),
        #               ip=remote[0],
        #               port=remote[1],
        #               alias=self._easyshare_remote_alias)

        resp = super()._pyroInvoke(methodname, vargs, kwargs, flags, objectId)

        # TRACE IN
        if is_tracing_enabled() and resp:
            trace_in("{}\n{}".format(methodname, j(resp)),
                     ip=remote[0],
                     port=remote[1],
                     alias=self._easyshare_remote_alias)

        return resp

    def __setattr__(self, key, value):
        # Do not let pyro handle our local attributes (e.g. _easyshare_remote_alias)
        if key.startswith(TracedPyroProxy._EASYSHARE_ATTR_PREFIX):
            return super(pyro.Proxy, self).__setattr__(key, value)   # standard __setattr__
        return super().__setattr__(key, value)                       # pyro __setattr__
