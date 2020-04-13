import os
from typing import Optional

from easyshare.protocol.filetype import FileType, FTYPE_DIR, FTYPE_FILE
from easyshare.protocol.sharinginfo import SharingInfo
from easyshare.shared.conf import SHARING_NAME_ALPHABET
from easyshare.utils.obj import items
from easyshare.utils.str import keep


class Sharing:
    def __init__(self, name: str, ftype: FileType, path: str, read_only: bool):
        self.name = name
        self.ftype = ftype
        self.path = path
        self.read_only = read_only

    def __str__(self):
        return str(items(self))

    @staticmethod
    def create(name: str, path: str, read_only: bool) -> Optional['Sharing']:
        # Ensure path existence
        if not path:
            return None

        if os.path.isdir(path):
            ftype = FTYPE_DIR
        elif os.path.isfile(path):
            ftype = FTYPE_FILE
        else:
            return None

        if not name:
            # Generate the sharing name from the path
            _, name = os.path.split(path)

        # Sanitize the name anyway (only alphanum and _ is allowed)
        # name = keep(name, SHARING_NAME_ALPHABET)

        read_only = True if read_only else False

        return Sharing(
            name=name,
            ftype=ftype,
            path=path,
            read_only=read_only
        )



    def info(self) -> SharingInfo:
        return {
            "name": self.name,
            "ftype": self.ftype,
            "read_only": self.read_only
        }
