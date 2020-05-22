import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional, Union


from easyshare.esd.common import ClientContext, Sharing
from easyshare.esd.daemons.pyro import get_pyro_daemon
from easyshare.logging import get_logger
from easyshare.protocol.responses import ServerErrors, create_error_response
from easyshare.utils.os import is_relpath, relpath
from easyshare.utils.pyro.server import pyro_client_endpoint
from easyshare.utils.str import unprefix
from easyshare.utils.types import is_int, is_str

log = get_logger(__name__)


# =============================================
# ============ BASE SERVICE ============
# =============================================


class BaseService(ABC):
    """
    Base service: an object that can be published to a Pyro Daemon.
    """
    @abstractmethod
    def publish(self) -> str:
        """ Publishes the service to the Pyro Daemon """
        pass

    @abstractmethod
    def unpublish(self):
        """ Unpublishes the service from the Pyro Daemon """
        pass

    @abstractmethod
    def is_published(self) -> bool:
        """ Whether the service is published """
        pass


# =============================================
# ============ BASE CLIENT SERVICE ============
# =============================================


class BaseClientService(BaseService):
    """
    Represents a 'BaseService' bound to a specific client.
    Is automatically added to the set of services of the client
    when is published, in order to be unpublished when the client disconnects.
    """

    def __init__(self, client: ClientContext,
                 end_callback: Callable[['BaseClientService'], None]):
        self.service_uri = None
        self.service_uid = None
        self.published = False

        self._client = client
        self._end_callback = end_callback

        self._lock = threading.Lock()

    def publish(self) -> str:
        """ Publishes the service to the Pyro Daemon """
        with self._lock:
            self.service_uri, self.service_uid = \
                get_pyro_daemon().publish(self, uid=self.service_uid)
            self.published = True
            self._client.add_service(self.service_uid)
            return self.service_uid

    def unpublish(self):
        """ Unpublishes the service from the Pyro Daemon """
        with self._lock:
            if self.is_published():
                get_pyro_daemon().unpublish(self.service_uid)
                self.published = False
                self._client.remove_service(self.service_uid)

    def is_published(self) -> bool:
        """ Whether the service is published """
        return self.published

    def _notify_service_end(self):
        if self._end_callback:
            self._end_callback(self)

    def _is_request_allowed(self):
        # A request is allowed if at least the address is the same
        # We can't check the port since the remote port will be different
        # (different socket)
        current_client_endpoint = pyro_client_endpoint()
        allowed = self._client.endpoint[0] == current_client_endpoint[0]

        if allowed:
            log.d("Service owner check OK")
        else:
            log.w("Not allowed, address mismatch between %s and %s", current_client_endpoint, self._client.endpoint)
        return allowed


# =============================================
# ========= BASE CLIENT SHARING SERVICE =======
# =============================================


class BaseClientSharingService(BaseClientService):
    """
    Represents a 'BaseService' bound to a specific client and sharing.
    Is automatically added to the set of services of the client
    when is published, in order to be unpublished when the client disconnects.
    Offers facilities for handle the rcwd, path conversion relative to the sharing,
    path domain checking and more.
    """

    def __init__(self,
                 sharing: Sharing,
                 sharing_rcwd: Path,
                 client: ClientContext,
                 end_callback: Callable[['BaseClientService'], None]):
        super().__init__(client, end_callback)
        self._sharing = sharing
        self._rcwd = sharing_rcwd


    def _rcwd_client_view(self):
        return self._rcwd.relative_to(self._sharing.path)

    def _current_real_path(self):
        return self._real_path_from_rcwd("")

    def _real_path_from_rcwd(self, path: str) -> Optional[str]:
        """
        Returns the path of the location composed of the 'path' of the
        sharing the es is currently on and the 'path' itself.
        The method allows:
            * 'path' starting with a leading / (absolute w.r.t the sharing path)
            * 'path' not starting with a leading / (relative w.r.t the rpwd)

        e.g.
            (ABSOLUTE)
            es sharing path =  /home/stefano/Applications
            es rpwd =                                     InsideAFolder
            path                =  /AnApp
                                => /home/stefano/Applications/AnApp

            (RELATIVE)
            es sharing path =  /home/stefano/Applications
            es rpwd =                                     InsideAFolder
            path                =  AnApp
                                => /home/stefano/Applications/InsideAFolder/AnApp

        """

        if is_relpath(path):
            # It refers to a subdirectory starting from the es's current directory
            path = os.path.join(self._rcwd, path)

        # Take the trail part (without leading /)
        trail = relpath(path)

        return os.path.normpath(os.path.join(self._sharing.path, trail))


    def _trailing_path_from_rcwd(self, path: str) -> Optional[str]:
        """
        Returns the trailing part of the 'path' by stripping the path of the
        sharing from the string's beginning.
        The path is relative w.r.t the rpwd of the sharing path the es
        is currently on.
        e.g.
            es sharing path = /home/stefano/Applications
            es rpwd         =                            AnApp
            (es path        = /home/stefano/Applications/AnApp          )
            path                = /home/stefano/Applications/AnApp/afile.mp4
                                =>                                 afile.mp4
        """
        return self._trailing_path(self._current_real_path(), path)


    def _is_real_path_allowed(self, path: str) -> bool:
        """
        Returns whether the given path is legal for the given es, based
        on the its sharing and rpwd.

        e.g. ALLOWED
            es sharing path = /home/stefano/Applications
            es rpwd         =                            AnApp
            path                = /home/stefano/Applications/AnApp/AFile.mp4

        e.g. NOT ALLOWED
            es sharing path = /home/stefano/Applications
            es rpwd         =                            AnApp
            path                = /home/stefano/Applications/AnotherApp/AFile.mp4

            es sharing path = /home/stefano/Applications
            es rpwd         =                           AnApp
            path                = /tmp/afile.mp4

        :param path: the path to check
        :param es: the es
        :return: whether the path is allowed for the es
        """
        normalized_path = os.path.normpath(path)

        try:
            common_path = os.path.commonpath([normalized_path, self._sharing.path])
            log.d("Common path between '%s' and '%s' = '%s'",
                  normalized_path, self._sharing.path, common_path)

            return self._sharing.path == common_path
        except:
            return False

    def _trailing_path(self, prefix: str, full: str) -> Optional[str]:
        """
        Returns the trailing part of the path 'full' by stripping the path 'prefix'.
        The path is relative w.r.t the root of the sharing path.
        e.g.
            prefix                = /home/stefano/Applications
            full                  = /home/stefano/Applications/AnApp/afile.mp4
                                  =>                           AnApp/afile.mp4
        """

        if not full or not prefix:
            return None

        if not full.startswith(prefix):
            return None

        return relpath(unprefix(full, prefix))

    def _trailing_path_from_root(self, path: str) -> Optional[str]:
        """
        Returns the trailing part of the 'path' by stripping the path of the
        sharing from the string's beginning.
        The path is relative w.r.t the root of the sharing path.
        e.g.
            sharing path        = /home/stefano/Applications
            path                = /home/stefano/Applications/AnApp/afile.mp4
                                =>                           AnApp/afile.mp4
        """
        return self._trailing_path(self._sharing.path, path)


    def _create_sharing_error_response(self, err: Union[int, str]):
        if is_int(err):
            return create_error_response(err)

        if is_str(err):
            safe_err = err.replace(self._sharing.path, "")
            return create_error_response(safe_err)

        return create_error_response()

    # ---- NEW

    def _is_path_allowed(self, p: Path) -> bool:
        try:
            p.relative_to(self._sharing.path)
            log.d("Path is allowed: %s", p.relative_to(self._sharing.path))
            return True
        except:
            log.d("Path is not allowed for this sharing %s", p)
            return False


# decorator
def check_sharing_service_owner(api):
    """
    Decorator that checks whether the remote peer is allowed
    based on its IP/port before invoking the wrapped API,
    """
    def check_sharing_service_owner_wrapper(client_service: BaseClientService, *vargs, **kwargs):
        if not client_service._is_request_allowed():
            return create_error_response(ServerErrors.NOT_ALLOWED)
        return api(client_service, *vargs, **kwargs)

    check_sharing_service_owner_wrapper.__name__ = api.__name__

    return check_sharing_service_owner_wrapper
