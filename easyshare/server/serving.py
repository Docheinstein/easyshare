from typing import List, Callable

from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.pyro import IServing
from easyshare.protocol.response import Response, create_error_response, create_success_response
from easyshare.server.client import ClientContext
from easyshare.server.clientpublication import ClientPublication, check_publication_owner
from easyshare.server.sharing import Sharing
from easyshare.utils.os import ls
from easyshare.utils.pyro import pyro_expose, pyro_client_endpoint

log = get_logger(__name__)


class Serving(IServing, ClientPublication):

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
                 client: ClientContext,
                 unpublish_hook: Callable = None):
        super().__init__(client, unpublish_hook)
        self._sharing = sharing

    @pyro_expose
    @check_publication_owner
    def rls(self, *,
            path: str = None, sort_by: List[str] = None,
            reverse: bool = False, hidden: bool = False, ) -> Response:
        # CHECK CLIENT

        # client = self._current_request_client()
        # if not client:
        #     log.w("Client not connected: %s", self._current_request_endpoint())
        #     return create_error_response(ServerErrors.NOT_CONNECTED)
        client_endpoint = pyro_client_endpoint()

        path = path or "."
        sort_by = sort_by or ["name"]

        log.i("<< RLS %s %s%s [%s]",
              path, sort_by, " | reverse " if reverse else "", str(client_endpoint))

        try:
            # ls_path = self._path_for_client(client, path)
            ls_path = "/tmp"
            log.i("Going to ls on %s", ls_path)
            #
            # # Check path legality (it should be valid, if he rcd into it...)
            # if not self._is_path_allowed_for_client(client, ls_path):
            #     return create_error_response(ServerErrors.INVALID_PATH)
            #
            ls_result = ls(ls_path, sort_by=sort_by, reverse=reverse)
            if ls_result is None:
                return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

            log.i("RLS response %s", str(ls_result))

            return create_success_response(ls_result)
        except Exception as ex:
            log.e("RLS error: %s", str(ex))
            return create_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)



    @pyro_expose
    @check_publication_owner
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

        self.unpublish()