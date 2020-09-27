import os
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

def tmpfile(parent, *, create=True, name=("file-" + randstring(length=4)), size: int = 0) -> Path:
    f = Path(parent) / name
    if create:
        log.x("TEST", f"Creating FILE '{f}'")
        f.touch()
        f.write_bytes(os.urandom(size))
    return f

def tmpdir(parent, *, create=True, name=("dir-" + randstring(length=4))) -> Path:
    d = Path(parent) / name
    if create:
        log.x("TEST", f"Creating DIR '{d}'")
        d.mkdir(parents=True)
    return d

class EsdTest:
    def __init__(self, server_name: str = None):
        self.server_name = server_name or ("server-" + randstring(length=4, alphabet=string.ascii_letters))
        self.sharing_root: Optional[Path] = None
        self._daemon = None

    def __enter__(self):
        log.x("TEST", "__enter__ START")
        self.sharing_root = tmpdir(tempfile.gettempdir())
        self._daemon = threading.Thread(target=lambda:
            start_esd(["-n", self.server_name, str(self.sharing_root)]), daemon=False)
        self._daemon.start()
        log.x("TEST", "__enter__ DONE")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        log.x("TEST", "__exit__ START")
        stop_esd()
        rm(self.sharing_root)
        log.x("TEST", "__exit__ DONE")
        return False

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
        return False
