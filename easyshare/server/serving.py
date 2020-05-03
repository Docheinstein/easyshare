import os
from typing import List, Optional

from Pyro5.api import expose

from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.pyro import IServing
from easyshare.protocol.response import Response, create_error_response, create_success_response
from easyshare.server.client import ClientContext
from easyshare.server.clientservice import ClientService, check_service_owner
from easyshare.server.common import try_or_command_failed_response
from easyshare.server.sharing import Sharing
from easyshare.utils.json import json_to_pretty_str
from easyshare.utils.os import ls, is_relpath, relpath, tree
from easyshare.utils.pyro import pyro_client_endpoint, trace_api

log = get_logger(__name__)


class Serving(IServing, ClientService):

    def rpwd(self) -> Response:
        pass

    def rcd(self, path: str) -> Response:
        pass

    def rtree(self, *, path: str = None, sort_by: List[str] = None, reverse: bool = False, hidden: bool = False,
              max_depth: int = None) -> Response:
        pass

    def rmkdir(self, directory: str) -> Response:
        pass

    def rrm(self, paths: List[str]) -> Response:
        pass

    def rmv(self, sources: List[str], destination: str) -> Response:
        pass

    def rcp(self, sources: List[str], destination: str) -> Response:
        pass

    def get(self, files: List[str]) -> Response:
        pass

    def get_next_info(self, transaction) -> Response:
        pass

    def put(self) -> Response:
        pass

    def put_next_info(self, transaction, info: FileInfo) -> Response:
        pass

    def __init__(self, sharing: Sharing, *,
                 client: ClientContext):
        super().__init__(client)
        self._sharing = sharing
        self._rcwd = ""

    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def rls(self, *,
            path: str = None, sort_by: List[str] = None,
            reverse: bool = False, hidden: bool = False) -> Response:

        client_endpoint = pyro_client_endpoint()

        path = path or "."
        sort_by = sort_by or ["name"]
        reverse = reverse or False

        log.i("<< RLS %s %s%s [%s]",
              path, sort_by,
              " | reverse " if reverse else "",
              str(client_endpoint))

        # Compute real path and check path legality
        ls_path = self._real_path(path)

        if not self._is_real_path_allowed(ls_path):
            return create_error_response(ServerErrors.INVALID_PATH)

        log.i("Going to ls on %s", ls_path)

        ls_result = ls(ls_path, sort_by=sort_by, reverse=reverse)
        if ls_result is None:  # Check is None, since might be empty
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

        log.i("RLS response %s", str(ls_result))

        return create_success_response(ls_result)


    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def rtree(self, *, path: str = None, sort_by: List[str] = None,
              reverse: bool = False, hidden: bool = False,
              max_depth: int = None, ) -> Response:

        client_endpoint = pyro_client_endpoint()

        path = path or "."
        sort_by = sort_by or ["name"]
        reverse = reverse or False

        log.i("<< RTREE %s %s%s (%s)",
              path, sort_by,
              " | reverse " if reverse else "",
              str(client_endpoint))

        # Compute real path and check path legality
        tree_path = self._real_path(path)

        if not self._is_real_path_allowed(tree_path):
            return create_error_response(ServerErrors.INVALID_PATH)

        log.i("Going to tree on %s", tree_path)

        tree_root = tree(tree_path, sort_by=sort_by, reverse=reverse, max_depth=max_depth)
        if tree_root is None:  # Check is None, since might be empty
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

        log.i("RTREE response %s", json_to_pretty_str(tree_root))

        return create_success_response(tree_root)


    @expose
    @trace_api
    @check_service_owner
    def close(self):
        client_endpoint = pyro_client_endpoint()

        log.i("<< CLOSE [%s]", str(client_endpoint))
        log.i("Deallocating client resources...")

        # CHECK CLIENT


        # Remove any pending transaction
        # for get_trans_id in client.gets:
        #     # self._end_get_transaction(get_trans_id, client, abort=True)
        #     if get_trans_id in self.gets:
        #         log.i("Removing GET transaction = %s", get_trans_id)
        #         self.gets.pop(get_trans_id).abort()
        #
        # # Remove from clients
        # log.i("Removing %s from clients", client)
        #
        # del self.clients[client_endpoint]
        # log.i("Client connection closed gracefully")
        #
        # log.i("# clients = %d", len(self.clients))
        # log.i("# gets = %d", len(self.gets))

        # self.unpublish()


    def _real_path(self, path: str) -> Optional[str]:
        """
        Returns the path of the location composed by the 'path' of the
        sharing the client is currently on and the 'path' itself.
        The method allows:
            * 'path' starting with a leading / (absolute w.r.t the sharing path)
            * 'path' not starting with a leading / (relative w.r.t the rpwd)

        e.g.
            (ABSOLUTE)
            client sharing path =  /home/stefano/Applications
            client rpwd =                                     InsideAFolder
            path                =  /AnApp
                                => /home/stefano/Applications/AnApp

            (RELATIVE)
            client sharing path =  /home/stefano/Applications
            client rpwd =                                     InsideAFolder
            path                =  AnApp
                                => /home/stefano/Applications/InsideAFolder/AnApp

        """

        if is_relpath(path):
            # It refers to a subdirectory starting from the client's current directory
            path = os.path.join(self._rcwd, path)

        # Take the trail part (without leading /)
        trail = relpath(path)

        return os.path.normpath(os.path.join(self._sharing.path, trail))


    def _is_real_path_allowed(self, path: str) -> bool:
        """
        Returns whether the given path is legal for the given client, based
        on the its sharing and rpwd.

        e.g. ALLOWED
            client sharing path = /home/stefano/Applications
            client rpwd         =                            AnApp
            path                = /home/stefano/Applications/AnApp/AFile.mp4

        e.g. NOT ALLOWED
            client sharing path = /home/stefano/Applications
            client rpwd         =                            AnApp
            path                = /home/stefano/Applications/AnotherApp/AFile.mp4

            client sharing path = /home/stefano/Applications
            client rpwd         =                           AnApp
            path                = /tmp/afile.mp4

        :param path: the path to check
        :param client: the client
        :return: whether the path is allowed for the client
        """

        normalized_path = os.path.normpath(path)

        try:
            common_path = os.path.commonpath([normalized_path, self._sharing.path])
            log.d("Common path between '%s' and '%s' = '%s'",
                  normalized_path, self._sharing.path, common_path)

            return self._sharing.path == common_path
        except:
            return False
