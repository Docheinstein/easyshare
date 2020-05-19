import os
import threading
from typing import Callable, Optional, Union


from easyshare.esd.common import ClientContext, Sharing
from easyshare.esd.daemons.server import get_pyro_daemon
from easyshare.logging import get_logger
from easyshare.protocol.responses import ServerErrors, create_error_response
from easyshare.utils.os import is_relpath, relpath
from easyshare.utils.pyro.server import pyro_client_endpoint
from easyshare.utils.str import unprefix
from easyshare.utils.types import is_int, is_str

log = get_logger(__name__)

# =============================================
# ============ BASE CLIENT SERVICE ============
# =============================================

class BaseClientService:
    def __init__(self, client: ClientContext,
                 end_callback: Callable[['BaseClientService'], None]):
        self.service_uri = None
        # self.service_uid = "esd_" + uuid()
        self.service_uid = None
        self.published = False

        self._client = client
        self._end_callback = end_callback

        self._lock = threading.Lock()


    def publish(self) -> str:
        with self._lock:
            self.service_uri, self.service_uid = \
                get_pyro_daemon().publish(self, uid=self.service_uid)
            self.published = True
            self._client.add_service(self.service_uid)
            return self.service_uid

    def unpublish(self):
        with self._lock:
            if self.is_published():
                get_pyro_daemon().unpublish(self.service_uid)
                self.published = False
                self._client.remove_service(self.service_uid)


    def is_published(self) -> bool:
        return self.published

    def _notify_service_end(self):
        if self._end_callback:
            self._end_callback(self)

    def _is_request_allowed(self):
        # Check whether the es that tries to access this publication
        # has the same IP of the original es the first time it access
        # and has the same IP and PORT for the rest of the time
        # log.d("Checking publication owner (original_owner: %s | current_owner: %s)", self._client, self._real_client_endpoint)
        #
        # current_client_endpoint = pyro_client_endpoint()
        #
        # if not self._real_client_endpoint:
        #     # First request: the port could be different from the original
        #     # one but the es IP must remain the same
        #     allowed = self._client.endpoint[0] == current_client_endpoint[0]
        #     log.d("First request, allowed: %s", allowed)
        #     if allowed:
        #         self._real_client_endpoint = current_client_endpoint
        #     return allowed
        #
        # # Not the first request: both IP and port must match
        # log.d("Further request, allowed: %s", self._real_client_endpoint == current_client_endpoint)
        # allowed = self._real_client_endpoint == current_client_endpoint
        # if not allowed:
        #     log.w("Not allowed since %s != %s", self._real_client_endpoint, current_client_endpoint)
        # return allowed
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
    def __init__(self,
                 sharing: Sharing,
                 sharing_rcwd: str,
                 client: ClientContext,
                 end_callback: Callable[['BaseClientService'], None]):
        super().__init__(client, end_callback)
        self._sharing = sharing
        self._rcwd = sharing_rcwd


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



# decorator
def check_service_owner(api):
    def check_service_owner_wrapper(client_service: BaseClientService, *vargs, **kwargs):
        if not client_service._is_request_allowed():
            return create_error_response(ServerErrors.NOT_ALLOWED)
        return api(client_service, *vargs, **kwargs)

    check_service_owner_wrapper.__name__ = api.__name__
    return check_service_owner_wrapper
