import pkgutil
import sys

from getpass import getpass

from easyshare import logging
from easyshare.args import Args, ArgsParseError, ActionParam
from easyshare.auth import AuthScrypt
from easyshare.common import APP_INFO
from easyshare.logging import get_logger, init_logging
from easyshare.utils.app import abort, terminate


log = get_logger("easyshare.tools", force_initialize=True)


def generate_password():
    plain_pass = getpass("Password: ")
    if not plain_pass:
        abort("Please insert a valid password")

    auth = AuthScrypt.new(plain_pass)
    if not auth:
        abort("Cannot compute password")

    print(auth)

def generate_esd_conf():
    esd_conf_b = pkgutil.get_data("easyshare.res", "esd.conf")
    esd_conf_s = str(esd_conf_b, encoding="UTF-8")
    print(esd_conf_s)


def main():
    try:
        Args.parse(
            sys.argv[1:],
            kwargs_specs= [
                (["-v", "--version"], ActionParam(lambda _: terminate(APP_INFO))),
            ]
        )
    except ArgsParseError:
        log.exception("Arguments parsing error")
        abort("Invalid command syntax")

    TOOLS = {
        "1": (generate_password, "PASSWORD GENERATOR"),
        "2": (generate_esd_conf, "ESD CONFIG GENERATOR (esd.conf)")
    }

    try:
        while True:
            choice = input(
                "What do you want to do?\n"
                "1. Generate secure password (hash)\n"
                "2. Generate default esd.conf\n"
            )
            if choice in TOOLS:
                func, funcname = TOOLS[choice]
                half_ruler = ((50 - len(funcname)) // 2) * "="

                print("\n{} {} {}\n".format(half_ruler, funcname, half_ruler))
                func()
                break
            else:
                print("\nPlease provide a valid action number")
            print()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()