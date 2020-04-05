import os
from typing import Optional

from easyshare.shared.conf import SHARING_NAME_ALPHABET
from easyshare.utils.str import keep


class Sharing:
    def __init__(self):
        self.name = None
        self.path = None
        self.read_only = False

    def __str__(self):
        return "[{}] | {} | {}".format(
            self.name,
            self.path,
            "r" if self.read_only else "rw")

    @staticmethod
    def create(name, path, read_only) -> Optional['Sharing']:
        sharing = Sharing()

        # Check path existence
        if not path or not os.path.isdir(path):
            return None

        if not name:
            # Generate the sharing name from the path
            _, name = os.path.split(path)

        # Sanitize the name anyway (only alphanum and _ is allowed)
        name = keep(name, SHARING_NAME_ALPHABET)

        read_only = True if read_only else False

        sharing.name = name
        sharing.path = path
        sharing.read_only = read_only

        return sharing
