from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union, Dict, List

from easyshare.consts import ansi
from easyshare.esd.common import Client, Sharing
from easyshare.esd.daemons.pyro import get_pyro_daemon, PyroObject
from easyshare.logging import get_logger
from easyshare.protocol.responses import ServerErrors, create_error_response
from easyshare.utils.inspection import stacktrace
from easyshare.utils.pyro.server import pyro_client_endpoint
from easyshare.utils.str import q
from easyshare.utils.types import is_str

log = get_logger(__name__)

# SPath and FPath are Path with a different semantic:
SPath = Path # sharing path, is relative and bounded to the sharing domain
FPath = Path # file system path, absolute, starts from the server's file system root

# =============================================
# ============ BASE SERVICE ============
# =============================================


class BaseService(PyroObject):
    """
    Base service: an object that can be published to a Pyro Daemon.
    """

    def __init__(self):
        self.service_uri = None
        self.service_uid = None
        self.published = False

    @abstractmethod
    def name(self) -> str:
        """ Name of the service (debug purpose) """
        pass

    def publish(self) -> str:
        """ Publishes the service to the Pyro Daemon """
        if not self.is_published():
            self.published = True
            self.service_uri, self.service_uid = \
                get_pyro_daemon().publish(self, uid=self.service_uid)
        log.d("Service [%s - %s] added", self.name(), self.service_uid)
        return self.service_uid

    def unpublish(self):
        """ Unpublishes the service from the Pyro Daemon """
        if self.is_published():
            self.published = False
            get_pyro_daemon().unpublish(self)
        log.d("Service [%s - %s] removed", self.name(), self.service_uid)

    def is_published(self) -> bool:
        """ Whether the service is published """
        return self.published


    def close(self):
        log.d("Service '%s' unpublished | uid = %s",
              self.name(), self.service_uid)

# =============================================
# ============ BASE CLIENT SERVICE ============
# =============================================


class BaseClientService(BaseService, ABC):
    """
    Represents a 'BaseService' bound to a specific client.
    Is automatically added to the set of services of the client
    when is published, in order to be unpublished when the client disconnects.
    """

    def __init__(self, client: Client):
        super().__init__()
        self.client = client
        self.endpoint = None

    def is_tracked(self) -> bool:
        return True

    def _accept_request_if_allowed(self, check_only_address: bool = False) -> bool:
        """
        Returns whether the request is allowed for the remote peer.

        If check_only_address is True, the IP + PORT is checked with the rule that:
        for the first request we can't check the port since the remote
        port will be different from the original one of client, therefore
        we will check the IP the first time, but further times we will
        check the new port too

        If check_only_address is False only the IP is checked.
        """

        current_client_endpoint = pyro_client_endpoint()

        if self.endpoint:
            # This is not the first request

            # Check address
            allowed = current_client_endpoint[0] == self.endpoint[0]

            if not check_only_address:
                # Check port too
                allowed = allowed and current_client_endpoint[1] == self.endpoint[1]
        else:
            # This is the first request, allow any port (since the port of a
            # proxy connected to a service will for sure be different from
            # the one the client has for the primary connection)

            # IP match
            allowed = self.client.endpoint[0] == current_client_endpoint[0]

        if allowed:
            log.d("Service owner check OK (check type = %s)",
                  "address" if check_only_address else "endpoint")

            # If this is the first connection, set the definitive remote endpoint
            # for this service (that should not change for further calls, apart
            # if the service allow more than proxy connection (e.g rexec, rshell),
            # but in that case check_only_address should be set to True for
            # a less strictly check
            if not self.endpoint:
                self.endpoint = current_client_endpoint
                log.i("Definitive client endpoint for this service (%s) is: %s",
                      self.name(), self.endpoint)
        else:
            log.w("Not allowed, mismatch between %s and %s",
                  current_client_endpoint, self.client.endpoint)
            log.w(stacktrace(color=ansi.FG_YELLOW))

        return allowed


# =============================================
# ========= BASE CLIENT SHARING SERVICE =======
# =============================================


class BaseClientSharingService(BaseClientService, ABC):
    """
    Represents a 'BaseService' bound to a specific client and sharing.
    Is automatically added to the set of services of the client
    when is published, in order to be unpublished when the client disconnects.
    Offers facilities for handle the rcwd, path conversion relative to the sharing,
    path domain checking and more.
    """

    # spath: path as seen by the client (Sharing PATH)
    # i.e. / is considered from the sharing root

    # fpath: path as seen by the server (Full PATH)
    # i.e. / is considered from the file system root

    def __init__(self,
                 sharing: Sharing,
                 sharing_rcwd: FPath,
                 client: Client):
        super().__init__(client)
        self._sharing = sharing
        self._rcwd_fpath: FPath = sharing_rcwd


    @property
    def _rcwd_spath(self) -> SPath:
        return self._spath_rel_to_root_of_fpath(self._rcwd_fpath)

    def _create_error_response(self,
                               err: Union[str, int, Dict, List[Dict]] = None,
                               *subjects  # if a suject is a Path, must be a FPath (relative to the file system)
                               ):
        """
        Create an error response sanitizing  subjects so that they are
        Path  relative to the sharing root (spath).
        """

        log.d("_err_resp of subjects %s", subjects)

        return create_error_response(err, *self._qspathify(*subjects))


    def _qspathify(self, *fpaths_or_strs) -> List[str]:
        """
        Adds quootes (") the string representation of every parameter, making
        those Path relative to the sharing root (spath) if are instance of Path.
        """
        # quote the spaths of fpaths
        if not fpaths_or_strs:
            return []

        log.d("_qspathify of %s", fpaths_or_strs)

        qspathified = [
            # leave str as str
            q(self._spath_rel_to_root_of_fpath(o)) if isinstance(o, Path) else str(o)
            for o in fpaths_or_strs
        ]

        log.d("qspathified -> %s", qspathified)

        return qspathified


    def _spath_rel_to_rcwd_of_fpath(self, p: Union[str, FPath]) -> SPath:
        """
        Returns the path 'p' relative to the current rcwd.
        The result should be within the sharing domain (if rcwd is valid).
        Raise an exception if 'p' doesn't belong to this sharing, so use
        this only after _is_fpath_allowed.
        """
        log.d("spath_of_fpath_rel_to_rcwd for p: %s", p)
        fp = self._as_path(p)
        log.d("-> fp: %s", fp)

        return fp.relative_to(self._rcwd_fpath)

    def _spath_rel_to_root_of_fpath(self, p: Union[str, FPath]) -> SPath:
        """
        Returns the path 'p' relative to the sharing root.
        The result should be within the sharing domain (if rcwd is valid).
        Raise an exception if 'p' doesn't belong to this sharing, so use
        this only after _is_fpath_allowed.
        """
        log.d("spath_of_fpath_rel_to_root for p: %s", p)
        fp = self._as_path(p)
        log.d("-> fp: %s", fp)

        return fp.relative_to(self._sharing.path)


    def _is_fpath_allowed(self, p: Union[str, FPath]) -> bool:
        """
        Checks whether p belongs to (is a subdirectory/file of) this sharing.
        """
        try:
            spath_from_root = self._spath_rel_to_root_of_fpath(p)
            log.d("Path is allowed for this sharing. spath is: %s", spath_from_root)
            return True
        except:
            log.d("Path is not allowed for this sharing: %s", p)
            return False


    def _fpath_joining_rcwd_and_spath(self, p: Union[str, SPath]) -> FPath:
        """
        Joins p to the current rcwd and returns an fpath
        (absolute Path from the file system root).
        If p is relative, than rcwd / p is the result.
        If p is absolute, than sharing root / p  is the result
        """
        p = self._as_path(p)

        if p.is_absolute():
            # Absolute is considered relative to the sharing root
            # Join all the path apart from the leading "/"
            fp = self._sharing.path.joinpath(*p.parts[1:])
        else:
            # Relative is considered relative to the current working directory
            # Join all the path
            fp = self._rcwd_fpath / p

        return fp.resolve()

    @classmethod
    def _as_path(cls, p: Union[str, Path]):
        if is_str(p):
            p = Path(p)

        if not isinstance(p, Path):
            raise TypeError(f"expected str or Path, found {type(p)}")

        return p

# decorator
def check_sharing_service_owner_endpoint(api):
    """
    Decorator that checks whether the remote peer is allowed
    based on its IP/port before invoking the wrapped API.
    Actually for the first request only the IP is checked (since the port
    might be different), for further calls everything is checked.
    """
    def check_sharing_service_owner_endpoint_wrapper(
            client_service: BaseClientService, *vargs, **kwargs):
        if not client_service._accept_request_if_allowed():
            return create_error_response(ServerErrors.NOT_ALLOWED)
        return api(client_service, *vargs, **kwargs)

    check_sharing_service_owner_endpoint_wrapper.__name__ = api.__name__

    return check_sharing_service_owner_endpoint_wrapper

# decorator
def check_sharing_service_owner_address(api):
    """
    Decorator that checks whether the remote peer is allowed
    based on its IP before invoking the wrapped API.
    This is a less strictly version of check_sharing_service_owner_endpoint
    since does not check ports.
    Is useful for services that requires the client to use multiple pyro proxy
    (and thus differnt sockets, e.g. rexec and rshell).
    """
    def check_sharing_service_owner_address_wrapper(
            client_service: BaseClientService, *vargs, **kwargs):
        if not client_service._accept_request_if_allowed(check_only_address=True):
            return create_error_response(ServerErrors.NOT_ALLOWED)
        return api(client_service, *vargs, **kwargs)

    check_sharing_service_owner_address_wrapper.__name__ = api.__name__

    return check_sharing_service_owner_address_wrapper