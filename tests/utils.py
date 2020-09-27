import string
import threading
from pathlib import Path
from typing import Optional

from easyshare.esd.__main__ import start as start_esd
from easyshare.esd.__main__ import stop as stop_esd
from easyshare.utils.rand import randstring

def tmpfile(parent, create=True) -> Path:
    f = Path(parent) / randstring()
    if create:
        f.touch()
    return f

def tmpdir(parent, create=True) -> Path:
    d = Path(parent) / randstring()
    if create:
        d.mkdir(parents=True)
    return d

class EsdTest:
    def __init__(self, server_name: str = None):
        self.server_name = server_name or randstring(length=4, alphabet=string.ascii_letters)
        self.server_root: Optional[Path] = None
        self._daemon = None

    def __enter__(self):
        self.server_root = tmpdir("/tmp")
        self._daemon = threading.Thread(target=lambda:
            start_esd(["-n", self.server_name, str(self.server_root)]), daemon=False)
        self._daemon.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        stop_esd()
        return self