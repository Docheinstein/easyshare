from collections import Callable

from easyshare.logging import get_logger
from easyshare.server.daemon import get_pyro_daemon
from easyshare.utils.str import uuid


log = get_logger(__name__)

#
# class Publication:
#     def __init__(self, unpublish_hook: Callable):
#         self.publication_uri = None
#         self.publication_uid = "esd_" + uuid()
#         self.published = False
#
#         self._unpublish_hook = unpublish_hook
#
#
#     def publish(self) -> str:
#         self.publication_uri, self.publication_uid = \
#             get_pyro_daemon().publish(self, uid=self.publication_uid)
#         self.published = True
#         return self.publication_uri
#
#
#     def unpublish(self):
#         if self.is_published():
#             get_pyro_daemon().unpublish(self.publication_uid)
#             self.published = False
#
#             if self._unpublish_hook:
#                 self._unpublish_hook(self)
#
#     def is_published(self) -> bool:
#         return self.published
