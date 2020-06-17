import os
from pathlib import Path
from typing import Optional, Union

if os.name == "nt":
    # Can't use is_windows() form utils.os due to circular import
    import win32api, win32con


def is_hidden(p: Union[str, Path]):
    if isinstance(p, Path):
        name = p.name
    elif isinstance(p, str):
        name = p
    else:
        raise TypeError("Path should be str or Path")

    if os.name == "nt":
        try:
            attribute = win32api.GetFileAttributes(name)
            return attribute & (win32con.FILE_ATTRIBUTE_HIDDEN | win32con.FILE_ATTRIBUTE_SYSTEM)
        except:
            # FIXME
            return False
    else:
        return name.startswith(".")

# Path extension
# pathlib.Path.is_hidden = _is_hidden
#
# class Path(pathlib.Path):
#     def is_hidden(self) -> bool:
#         pass
# --------------

def LocalPath(p: Optional[str] = None, default="") -> Path:
    return Path(p or default).expanduser()

