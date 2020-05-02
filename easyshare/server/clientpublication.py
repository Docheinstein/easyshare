from typing import Callable

from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.response import create_error_response
from easyshare.server.client import ClientContext
from easyshare.server.publication import Publication
from easyshare.utils.pyro import pyro_client_endpoint

log = get_logger(__name__)


class ClientPublication(Publication):
    def __init__(self, client: ClientContext, unpublish_hook: Callable):
        super().__init__(unpublish_hook)
        self._client = client
        # self._real_client_endpoint = None

    def publish(self) -> str:
        super().publish()
        self._client.add_publication(self)
        return self.publication_uri

    def unpublish(self):
        super().unpublish()
        self._client.remove_publication(self)

    def _is_request_allowed(self):
        # Check whether the client that tries to access this publication
        # has the same IP of the original client the first time it access
        # and has the same IP and PORT for the rest of the time
        # log.d("Checking publication owner (original_owner: %s | current_owner: %s)", self._client, self._real_client_endpoint)
        #
        # current_client_endpoint = pyro_client_endpoint()
        #
        # if not self._real_client_endpoint:
        #     # First request: the port could be different from the original
        #     # one but the client IP must remain the same
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
            log.d("Publication owner check OK")
        else:
            log.w("Not allowed, address mismatch between %s and %s", current_client_endpoint, self._client.endpoint)
        return allowed


# decorator
def check_publication_owner(api):
    def check_publication_owner_wrapper(client_pub: ClientPublication, *vargs, **kwargs):
        if not client_pub._is_request_allowed():
            return create_error_response(ServerErrors.NOT_ALLOWED)
        return api(client_pub, *vargs, **kwargs)
    check_publication_owner_wrapper.__name__ = api.__name__
    return check_publication_owner_wrapper