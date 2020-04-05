from typing import Optional

from easyshare.shared.endpoint import Endpoint


class ClientContext:
    def __init__(self):
        self.endpoint: Optional[Endpoint] = None
        self.sharing_name: Optional[str] = None
        self.rpwd = ""

    def __str__(self):
        return self.endpoint[0] + ":" + str(self.endpoint[1])