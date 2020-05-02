from collections import Callable

from easyshare.logging import get_logger
from easyshare.server.daemon import unpublish_pyro_object, publish_pyro_object
from easyshare.utils.str import uuid


log = get_logger(__name__)


class Publication:
    def __init__(self, unpublish_hook: Callable):
        self.publication_uri = None
        self.publication_uid = "esd_" + uuid()
        self.published = False

        self._unpublish_hook = unpublish_hook


    def publish(self) -> str:
        self.publication_uri, self.publication_uid = \
            publish_pyro_object(self, uid=self.publication_uid)
        self.published = True
        return self.publication_uri


    def unpublish(self):
        unpublish_pyro_object(self.publication_uid)
        self.published = False

        if self._unpublish_hook:
            self._unpublish_hook(self)

    def is_published(self) -> bool:
        return self.published
