from typing import Union, List

from easyshare.client.errors import ClientErrors
from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.response import Response, create_error_response, is_success_response, is_data_response, \
    is_error_response, create_success_response
from easyshare.protocol.exposed import ISharingService
from easyshare.protocol.serverinfo import ServerInfoFull
from easyshare.protocol.sharinginfo import SharingInfo
from easyshare.shared.common import pyro_uri
from easyshare.utils.json import json_to_pretty_str
from easyshare.utils.pyro import TracedPyroProxy

log = get_logger(__name__)


def require_sharing_connection(api):
    def require_sharing_connection_api_wrapper(conn: 'SharingConnection', *vargs, **kwargs) -> Response:
        log.d("Checking sharing connection validity before invoking %s", api.__name__)
        if not conn.is_connected():
            log.w("@require_sharing_connection : invalid connection")
            return create_error_response(ClientErrors.NOT_CONNECTED)
        log.d("Sharing connection is valid, invoking %s", api.__name__)
        return api(conn, *vargs, **kwargs)

    require_sharing_connection_api_wrapper.__name__ = api.__name__

    return require_sharing_connection_api_wrapper


def handle_sharing_response(api):
    def handle_sharing_response_api_wrapper(conn: 'SharingConnection', *vargs, **kwargs) -> Response:
        log.d("Invoking %s and handling response", api.__name__)
        resp = api(conn, *vargs, **kwargs)
        log.d("Handling %s response", api.__name__)

        if is_error_response(resp, ServerErrors.NOT_CONNECTED):
            conn._destroy_connection()

        return resp

    handle_sharing_response_api_wrapper.__name__ = __name__

    return handle_sharing_response_api_wrapper


class SharingConnection:

    def __init__(self, sharing_uid: str,
                 sharing_info: SharingInfo,
                 server_info: ServerInfoFull):
        log.i("Initializing new SharingConnection")
        log.d("Bound to server \n%s", json_to_pretty_str(server_info))

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

    def rcwd(self) -> str:
        return self._rcwd

    # =====

    # NO @handle_response (async)
    @require_sharing_connection
    def close(self):
        self.service.close()         # async
        self._destroy_connection()


    @require_sharing_connection
    def rpwd(self) -> Response:
        return create_success_response(self._rcwd)  # cached

    @handle_sharing_response
    @require_sharing_connection
    def rcd(self, path) -> Response:
        resp = self.service.rcd(path)

        if is_success_response(resp):
            self._rcwd = resp["data"]

        return resp

    @handle_sharing_response
    @require_sharing_connection
    def rls(self, sort_by: List[str], reverse: bool = False,
            hidden: bool = False,  path: str = None) -> Response:
        return self.service.rls(path=path, sort_by=sort_by,
                                reverse=reverse, hidden=hidden)

    @handle_sharing_response
    @require_sharing_connection
    def rtree(self, sort_by: List[str], reverse=False, hidden: bool = False,
              max_depth: int = int, path: str = None) -> Response:
        return self.service.rtree(path=path, sort_by=sort_by, reverse=reverse,
                                  hidden=hidden, max_depth=max_depth)

    @handle_sharing_response
    @require_sharing_connection
    def rmkdir(self, directory) -> Response:
        return self.service.rmkdir(directory)

    @handle_sharing_response
    @require_sharing_connection
    def rrm(self, paths: List[str]) -> Response:
        return self.service.rrm(paths)

    @handle_sharing_response
    @require_sharing_connection
    def rmv(self, sources: List[str], destination: str) -> Response:
        return self.service.rmv(sources, destination)

    @handle_sharing_response
    @require_sharing_connection
    def rcp(self, sources: List[str], destination: str) -> Response:
        return self.service.rcp(sources, destination)

    @handle_sharing_response
    @require_sharing_connection
    def get(self, files: List[str]) -> Response:
        return self.service.get(files)

    @handle_sharing_response
    @require_sharing_connection
    def put(self, check: bool) -> Response:
        return self.service.put(check)

    def _destroy_connection(self):
        log.d("Marking sharing connection as disconnected")
        self._connected = False

        if self.service:
            log.d("Releasing pyro resources of the sharing connection")
            self.service._pyroRelease()
            self.service = None
        else:
            log.w("Sharing connection already invalid, nothing to release")

