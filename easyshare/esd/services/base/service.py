import threading
from typing import Callable

from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.response import create_error_response
from easyshare.esd.client import ClientContext
from easyshare.esd.daemon import get_pyro_daemon
from easyshare.utils.pyro import pyro_client_endpoint
from easyshare.utils.str import uuid

log = get_logger(__name__)


class ClientService:
    def __init__(self, client: ClientContext,
                 end_callback: Callable[['ClientService'], None]):
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


# decorator
def check_service_owner(api):
    def check_service_owner_wrapper(client_service: ClientService, *vargs, **kwargs):
        if not client_service._is_request_allowed():
            return create_error_response(ServerErrors.NOT_ALLOWED)
        return api(client_service, *vargs, **kwargs)
    check_service_owner_wrapper.__name__ = api.__name__
    return check_service_owner_wrapper