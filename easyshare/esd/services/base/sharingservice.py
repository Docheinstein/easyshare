import os
from typing import Callable, Optional, Union

from easyshare.logging import get_logger
from easyshare.protocol.response import create_error_response
from easyshare.esd.client import ClientContext
from easyshare.esd.services.base.service import ClientService
from easyshare.esd.sharing import Sharing
from easyshare.utils.os import relpath, is_relpath
from easyshare.utils.str import unprefix
from easyshare.utils.types import is_int, is_str

log = get_logger(__name__)


class ClientSharingService(ClientService):
    def __init__(self,
                 sharing: Sharing,
                 sharing_rcwd: str,
                 client: ClientContext,
                 end_callback: Callable[['ClientService'], None]):
        super().__init__(client, end_callback)
        self._sharing = sharing
        self._rcwd = sharing_rcwd


    def _current_real_path(self):
        return self._real_path_from_rcwd("")

    def _real_path_from_rcwd(self, path: str) -> Optional[str]:
        """
        Returns the path of the location composed by the 'path' of the
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