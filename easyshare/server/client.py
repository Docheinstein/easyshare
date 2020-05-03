from typing import Optional, List, Set

from easyshare.logging import get_logger
from easyshare.server.publication import Publication
from easyshare.shared.endpoint import Endpoint
from easyshare.utils.str import randstring

log = get_logger(__name__)


class ClientContext:

    def __init__(self, endpoint: Endpoint):
        self.endpoint: Optional[Endpoint] = endpoint
        self.publications: Set[Publication] = set()
        self.tag = randstring(8)

    def __str__(self):
        return "{} : {}".format(self.endpoint, self.tag)

    def add_publication(self, pub: Publication):
        log.d("Publication [%s] added", pub.publication_uid)
        self.publications.add(pub)


    def remove_publication(self, pub: Publication):
        try:
            self.publications.remove(pub)
            log.d("Publication [%s] removed", pub.publication_uid)
        except:
            log.w("Publication unpublish failed; not among client's publications")