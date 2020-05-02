from typing import Optional

from easyshare.logging import get_logger
from easyshare.shared.common import is_server_name
from easyshare.utils.net import is_valid_ip, is_valid_port
from easyshare.utils.types import to_int

log = get_logger(__name__)


class ServerSpecifier:
    # |----server specifier-----|
    # <server_name>|<ip>[:<port>]

    def __init__(self,
                 name: str = None,
                 ip: str = None,
                 port: int = None):
        self.name = name
        self.ip = ip
        self.port = port

    def __str__(self):
        s = ""
        if self.name or self.ip:
            if self.name:
                s += "@" + self.name
            elif self.ip:
                s += "@" + self.ip
            if self.port:
                s += ":" + str(self.port)

        return s

    @staticmethod
    def parse(spec: str) -> Optional['ServerSpecifier']:


        if not spec:
            log.d("ServerSpecifier.parse() -> None")
            return None

        server_name_or_ip, _, server_port = spec.partition(":")

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

        server_spec = ServerSpecifier(
            name=server_name,
            ip=server_ip,
            port=server_port
        )

        log.d("ServerSpecifier.parse() -> %s", str(server_spec))

        return server_spec


class SharingSpecifier:
    # |----name-----|-----server specifier-------|
    # <sharing_name>[@<server_name>|<ip>[:<port>]]
    # |-------------sharing specifier------------|
    #
    # e.g.  shared
    #       shared@john-desktop
    #       shared@john-desktop:54794
    #       shared@192.168.1.105
    #       shared@192.168.1.105:47294

    def __init__(self,
                 sharing_name: str,
                 server_spec: ServerSpecifier = ServerSpecifier()):
        self.name: str = sharing_name
        self.server: ServerSpecifier = server_spec

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
    def parse(spec: str) -> Optional['SharingSpecifier']:
        if not spec:
            log.d("SharingSpecifier.parse() -> None")
            return None

        sharing_name, _, server_specifier = spec.partition("@")
        server_spec = ServerSpecifier.parse(server_specifier)

        sharing_spec = SharingSpecifier(
            sharing_name=sharing_name,
            server_spec=server_spec
        )

        log.d("SharingSpecifier.parse() -> %s", str(sharing_spec))

        return sharing_spec
