import string
import tempfile
import threading
from pathlib import Path
from typing import Optional

from easyshare.commands.commands import Commands
from easyshare.es.client import Client
from easyshare.esd.__main__ import start as start_esd
from easyshare.esd.__main__ import stop as stop_esd
from easyshare.logging import get_logger
from easyshare.utils.os import rm
from easyshare.utils.rand import randstring

log = get_logger(__name__)

def tmpfile(parent, create=True) -> Path:
    f = Path(parent) / randstring()
    if create:
        log.x("XXX", f"Creating FILE '{f}'")
        f.touch()
    return f

def tmpdir(parent, create=True) -> Path:
    d = Path(parent) / randstring()
    if create:
        log.x("XXX", f"Creating DIR '{d}'")
        d.mkdir(parents=True)
    return d

class EsdTest:
    def __init__(self, server_name: str = None):
        self.server_name = server_name or randstring(length=4, alphabet=string.ascii_letters)
        self.server_root: Optional[Path] = None
        self._daemon = None

    def __enter__(self):
        log.x("XXX", "__enter__ START")
        self.server_root = tmpdir(tempfile.gettempdir())
        self._daemon = threading.Thread(target=lambda:
            start_esd(["-n", self.server_name, str(self.server_root)]), daemon=False)
        self._daemon.start()
        log.x("XXX", "__enter__ DONE")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        log.x("XXX", "__exit__ START")
        stop_esd()
        rm(self.server_root)
        log.x("XXX", "__exit__ DONE")
        return self

class EsConnectionTest:
    def __init__(self, sharing_name, cd=None):
        self.sharing_name = sharing_name
        self.cd = cd
        self.client = None

    def enter(self):
        return self.__enter__()

    def exit(self):
        self.__exit__(None, None, None)

    def __enter__(self):
        self.client = Client()

        if self.cd:
            self.client.execute_command(Commands.LOCAL_CHANGE_DIRECTORY, self.cd)

        self.client.execute_command(Commands.OPEN, self.sharing_name)
        return self.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.execute_command(Commands.CLOSE)
        return self.client
