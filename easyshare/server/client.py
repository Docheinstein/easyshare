import threading
from typing import Optional, Set

from easyshare.logging import get_logger
from easyshare.shared.endpoint import Endpoint
from easyshare.utils.str import randstring

log = get_logger(__name__)


class ClientContext:

    def __init__(self, endpoint: Endpoint):
        self.endpoint: Optional[Endpoint] = endpoint
        self.services: Set[str] = set()
        self.tag = randstring(8)
        self.lock = threading.Lock()


    def __str__(self):
        return "{} : {}".format(self.endpoint, self.tag)


    def add_service(self, service_id: str):
        log.d("Service [%s] added", service_id)
        with self.lock:
            self.services.add(service_id)


    def remove_service(self, service_id: str):
        log.d("Service [%s] removed", service_id)
        with self.lock:
            self.services.remove(service_id)
