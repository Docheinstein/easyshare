from typing import Optional

from easyshare.logging import get_logger
from easyshare.common import is_server_name
from easyshare.utils.net import is_valid_ip, is_valid_port
from easyshare.utils.types import to_int

log = get_logger(__name__)


class ServerLocation:
    # |----esd location---------|
    # <server_name> OR <ip>[:<port>]

    # e.g.  hostname
    #       192.168.1.105
    #       192.168.1.105:47294

    def __init__(self,
                 name: str = None,
                 ip: str = None,
                 port: int = None):
        self.name = name
        self.ip = ip
        self.port = port

    def __str__(self):
        if not self.name and not self.ip:
            return ""

        s = ""
        if self.name:
            s = self.name
        elif self.ip:
            s = self.ip

        if self.port:
            s += ":" + str(self.port)

        return s

    @staticmethod
    def parse(location: str) -> Optional['ServerLocation']:

        if not location:
            log.d("ServerLocation.parse() -> None")
            return None

        server_name_or_ip, _, server_port = location.partition(":")

        server_ip = None
        server_name = None

        if server_name_or_ip:
            if is_valid_ip(server_name_or_ip):
                server_ip = server_name_or_ip
            elif is_server_name(server_name_or_ip):
                server_name = server_name_or_ip

        server_port = to_int(server_port)

        if not is_valid_port(server_port):
            server_port = None

        if not server_name and not server_ip:
            log.w("Invalid esd location for '%s'", location)
            return None

        server_location = ServerLocation(
            name=server_name,
            ip=server_ip,
            port=server_port
        )

        log.d("ServerLocation.parse() -> %s", str(server_location))

        return server_location


class SharingLocation:
    # |----name-----|-----esd location--------|
    # <sharing_name>[@<server_name>|<ip>[:<port>]]
    # |-------------sharing location-------------|
    #
    # e.g.  shared
    #       shared@john-desktop
    #       shared@john-desktop:54794
    #       shared@192.168.1.105
    #       shared@192.168.1.105:47294

    def __init__(self,
                 sharing_name: str,
                 server_location: ServerLocation = None):
        self.name: str = sharing_name
        self.server: ServerLocation = server_location

    def __str__(self):
        s = self.name
        return "{}{}".format(s, ("@" + str(self.server)) if self.server else "")

    @property
    def server_name(self) -> Optional[str]:
        return self.server.name if self.server else None

    @property
    def server_ip(self) -> Optional[str]:
        return self.server.ip if self.server else None

    @property
    def server_port(self) -> Optional[int]:
        return self.server.port if self.server else None

    @staticmethod
    def parse(location: str) -> Optional['SharingLocation']:
        if not location:
            log.d("SharingLocation.parse() -> None")
            return None

        sharing_name, _, server_locationifier = location.partition("@")
        server_location = ServerLocation.parse(server_locationifier)

        if not sharing_name:
            log.w("Invalid sharing location for '%s'", location)
            return None

        sharing_location = SharingLocation(
            sharing_name=sharing_name,
            server_location=server_location
        )

        log.d("SharingLocation.parse() -> %s", str(sharing_location))

        return sharing_location


if __name__ == "__main__":
    print("1.", ServerLocation.parse("hostname"))
    print("2.", ServerLocation.parse("192.168.1.105:"))
    print("3.", ServerLocation.parse("192.168.1.105:8888"))
    print()
    print("1.", SharingLocation.parse("shared"))
    print("2.", SharingLocation.parse("shared@hostname"))
    print("3.", SharingLocation.parse("shared@192.168.1.105"))
    print("4.", SharingLocation.parse("shared@192.168.1.105:8888"))

