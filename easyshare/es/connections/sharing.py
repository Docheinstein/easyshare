    from typing import Union, List

from easyshare.es.connections import require_connected_connection, handle_connection_response
from easyshare.es.errors import ClientErrors
from easyshare.logging import get_logger
from easyshare.protocol.services import Response, ISharingService
from easyshare.protocol.responses import is_success_response, create_success_response, ServerErrors, is_error_response, \
    create_error_response
from easyshare.protocol.types import ServerInfoFull, SharingInfo
from easyshare.utils.json import j
from easyshare.utils.pyro.client import TracedPyroProxy
from easyshare.utils.pyro import pyro_uri

log = get_logger(__name__)



# =============================================
# ============ SHARING CONNECTION =============
# =============================================


class SharingConnection:
    """
    Connection to a remote 'SharingService'.
    Basically its a wrapper around the exposed method of 'ISharingService',
    but adds tracing and handles some stuff locally (e.g. rcwd).
    """
    def __init__(self, sharing_uid: str,
                 sharing_info: SharingInfo,
                 server_info: ServerInfoFull):
        log.i("Initializing new SharingConnection")
        log.d("Bound to server info:\n%s", j(server_info))

        self.sharing_info = sharing_info
        self.server_info = server_info

        self._connected = True  # Start as connected,
                                # we already have opened the remote serving
        self._rcwd = ""

        # Create the proxy for the remote sharing
        self.service: Union[ISharingService, TracedPyroProxy] = TracedPyroProxy(
            pyro_uri(sharing_uid, server_info.get("ip"), server_info.get("port")),
            alias="{}{}{}".format(
                sharing_info.get("name") if sharing_info else "",
                "@" if sharing_info and server_info else "",
                server_info.get("name") if server_info else ""
            )
        )

    def is_connected(self) -> bool:
        return self._connected is True and self.service


    def destroy_connection(self):
        log.d("Marking sharing connection as disconnected")
        self._connected = False

        if self.service:
            log.d("Releasing pyro resources of the sharing connection")
            self.service._pyroRelease()
            self.service = None
        else:
            log.w("Sharing connection already invalid, nothing to release")


    def rcwd(self) -> str:
        """
        Current remote working directory.
        It should be consisted with the one provided by rpwd().
        """
        return self._rcwd


    @require_connected_connection
    def close(self):
        self.service.close_()         # async
        self.destroy_connection()

    @require_connected_connection
    def rpwd(self) -> Response:
        return create_success_response(self._rcwd)  # cached

    @handle_connection_response
    @require_connected_connection
    def rcd(self, path) -> Response:
        resp = self.service.rcd(path)

        if is_success_response(resp):
            self._rcwd = resp["data"]

        return resp

    @handle_connection_response
    @require_connected_connection
    def rls(self, sort_by: List[str], reverse: bool = False,
            hidden: bool = False,  path: str = None) -> Response:
        return self.service.rls(path=path, sort_by=sort_by,
                                reverse=reverse, hidden=hidden)

    @handle_connection_response
    @require_connected_connection
    def rtree(self, sort_by: List[str], reverse=False, hidden: bool = False,
              max_depth: int = int, path: str = None) -> Response:
        return self.service.rtree(path=path, sort_by=sort_by, reverse=reverse,
                                  hidden=hidden, max_depth=max_depth)

    @handle_connection_response
    @require_connected_connection
    def rmkdir(self, directory) -> Response:
        return self.service.rmkdir(directory)

    @handle_connection_response
    @require_connected_connection
    def rrm(self, paths: List[str]) -> Response:
        return self.service.rrm(paths)

    @handle_connection_response
    @require_connected_connection
    def rmv(self, sources: List[str], destination: str) -> Response:
        return self.service.rmv(sources, destination)

    @handle_connection_response
    @require_connected_connection
    def rcp(self, sources: List[str], destination: str) -> Response:
        return self.service.rcp(sources, destination)

    @handle_connection_response
    @require_connected_connection
    def get(self, files: List[str], check: bool) -> Response:
        return self.service.get(files, check)

    @handle_connection_response
    @require_connected_connection
    def put(self, check: bool) -> Response:
        return self.service.put(check)

