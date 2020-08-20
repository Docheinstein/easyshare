import datetime
from typing import Type, Tuple, List
import sys

import os

# Add the the project directory to sys.path before load any easyshare module
# since this is outside the easyshare folder and the modules won't be
# seen otherwise

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PARENT_DIR, _ = os.path.split(SCRIPT_DIR)

sys.path.append(SCRIPT_PARENT_DIR)

# Now we can import easyshare stuff

from easyshare.commands import CommandHelp, es
from easyshare.commands.commands import COMMANDS_INFO
from easyshare.commands.es import Es
from easyshare.commands.esd import Esd
from easyshare.commands.estools import EsTools
from easyshare.utils.str import isorted


def section(name: str, content: str, indent: int = 4):
    if not content:
        return ""

    i = (" " * indent)
    return f"**{name}**\n{i + i.join(content.splitlines(keepends=True))}\n\n"


def make_hmd(cmd: Type[CommandHelp]):
    s = f"""
. =============================================
. Automatically generated - {datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")}
. =============================================
"""

    def opt_str(opt):
        return ", ".join(f"**{alias}**" for alias in opt.aliases) + \
               " " + \
               (" ".join(f"*{param}*" for param in opt.params) if opt.params else "") + \
               "\n" + \
               "    " + opt.description[0].upper() + opt.description[1:]

    options_content = "\n\n".join(opt_str(opt) for opt in
                                  isorted(cmd.options(), key=lambda opt: opt.aliases_str()))

    s += section("COMMAND", f"{cmd.name()} - {cmd.short_description()}")
    s += section("SYNOPSIS", cmd.synopsis())
    s += section("DESCRIPTION", cmd.long_description())
    s += section("OPTIONS", options_content)
    s += section("EXAMPLES", cmd.examples())
    s += section("SEE ALSO", cmd.see_also())

    return s[:len(s) - 1]

if __name__ == "__main__":
    HELPS_PATH = "../easyshare/res/helps"
    # noinspection PyTypeChecker

    cmds: List[Tuple[str, Type[CommandHelp]]] = \
        [(k, v) for k, v in COMMANDS_INFO.items()] + [
            (Es.name(), Es),
            (Esd.name(), Esd),
            (EsTools.name(), EsTools),
        ]

    os.makedirs(HELPS_PATH, exist_ok=True)

    for (cmd_name, cmd_help) in cmds:
        with open(f"{HELPS_PATH}/{cmd_name}.hmd", "w") as f:
            f.write(make_hmd(cmd_help))

    with open(f"{HELPS_PATH}/usage.hmd", "w") as f:
        f.write(es.USAGE)