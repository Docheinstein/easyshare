# It would be wonderful to use Literal type as of PEP 586
# https://www.python.org/dev/peps/pep-0586/
# But it is

FTYPE_FILE = "file"
FTYPE_DIR = "dir"

try:
    # From python 3.8
    from typing import Literal

    FileType = Literal["file", "dir"]
except:
    FileType = str  # "file" | "dir"

