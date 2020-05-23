import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional, Union, Dict, List

from easyshare.esd.common import ClientContext, Sharing
from easyshare.esd.daemons.pyro import get_pyro_daemon
from easyshare.logging import get_logger
from easyshare.protocol.responses import ServerErrors, create_error_response
from easyshare.utils.os import is_relpath, relpath
from easyshare.utils.pyro.server import pyro_client_endpoint
from easyshare.utils.str import unprefix, q
from easyshare.utils.types import is_str

log = get_logger(__name__)


SPath = Path
FPath = Path

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
                 sharing_rcwd: FPath,
                 client: ClientContext,
                 end_callback: Callable[['BaseClientService'], None]):
        super().__init__(client, end_callback)
        self._sharing = sharing
        self._rcwd_fpath: FPath = sharing_rcwd


    @property
    def _rcwd_spath(self) -> SPath:
        return self._spath_rel_to_root_of_fpath(self._rcwd_fpath)

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
            path = os.path.join(self._rcwd_fpath, path)

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


    def _err_resp(self,
                  err: Union[str, int, Dict, List[Dict]] = None,
                  *subjects # if a suject is a Path, must be a FPath (relative to the file system)
          ):
        """ Sanitize subjects so that they are Path relative to the sharing root """

        log.d("_err_resp of subjects %s", subjects)

        return create_error_response(err, *self._qspathify(*subjects))


    def _qspathify(self, *fpaths_or_strs) -> List[str]:
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


    # ---- NEW ----

    # spath: path as seen by the client (Sharing PATH)
    # i.e. / is considered from the sharing root

    # fpath: path as see by the server (Full PATH)
    # i.e. / is considered from the file system root

    def _spath_rel_to_rcwd_of_fpath(self, p: Union[str, FPath]) -> SPath:

    # def _path_rel_to_rcwd(self, ) -> Path:
    #     """
    #     Returns the part of p without the rcwd prefix (which should belong this sharing)
    #     Might throw if p doesn't belong to this sharing.
    #     """
        log.d("spath_of_fpath_rel_to_rcwd for p: %s", p)
        fp = self._as_path(p)
        log.d("-> fp: %s", fp)

        return fp.relative_to(self._rcwd_fpath)

    def _spath_rel_to_root_of_fpath(self, p: Union[str, FPath]) -> SPath:
        # """
        # Returns the part of p without the sharing's root prefix.
        # Might throw if p doesn't belong to this sharing.
        # """
        log.d("spath_of_fpath_rel_to_root for p: %s", p)
        fp = self._as_path(p)
        log.d("-> fp: %s", fp)

        return fp.relative_to(self._sharing.path)


    def _is_fpath_allowed(self, p: Union[str, FPath]) -> bool:
        # """
        # Checks whether p belongs to (is a subdirectory/file of) this sharing.
        # """
        try:
            spath_from_root = self._spath_rel_to_root_of_fpath(p)
            log.d("Path is allowed for this sharing. spath is: %s", spath_from_root)
            return True
        except:
            log.d("Path is not allowed for this sharing: %s", p)
            return False


    def _fpath_joining_rcwd_and_spath(self, p: Union[str, SPath]) -> FPath:
        # """
        # Joins p to the current rcwd and returns an absolute Path (from the file system root).
        # If p is relative, than rcwd / p is the result.
        # If p is absolute, than p (relative to the root) is the result
        # """
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
        # return p.resolve() if resolve else p



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


if __name__ == "__main__":
    sh = Sharing.create("test", "/tmp")
    serv = BaseClientSharingService(sh, sh.path, None, None)
    serv