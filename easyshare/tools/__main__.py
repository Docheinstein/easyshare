import pkgutil
import sys

from getpass import getpass

from easyshare.args import ArgsParseError
from easyshare.auth import AuthScrypt
from easyshare.common import APP_INFO, easyshare_setup
from easyshare.help.estools import EsTools
from easyshare.logging import get_logger
from easyshare.res.helps import get_command_usage
from easyshare.utils.app import abort, terminate


def generate_password(pw: str):
    auth = AuthScrypt.new(pw)
    if not auth:
        abort("Cannot compute password")

    print(auth)

def generate_esd_conf():
    esd_conf_b = pkgutil.get_data("easyshare.res", "esd.conf")
    esd_conf_s = str(esd_conf_b, encoding="UTF-8")
    print(esd_conf_s)


def ask_and_generate_password():
    plain_pass = getpass("Password: ")
    if not plain_pass:
        abort("Please insert a valid password")
    generate_password(plain_pass)

def main():
    easyshare_setup()

    # Parse arguments
    args = None

    try:
        args = EsTools().parse(sys.argv[1:])
    except ArgsParseError as err:
        abort("Parse of arguments failed: {}".format(str(err)))


    # Help?
    if EsTools.HELP in args:
        terminate(get_command_usage(EsTools.name()))

    # Version?
    if EsTools.VERSION in args:
        terminate(APP_INFO)


    # Explicit mode?

    if EsTools.GENERATE_ESD_CONF in args:
        generate_esd_conf()
        return

    if EsTools.GENERATE_PASSWORD in args:
        pw = args.get_kwarg_param(EsTools.GENERATE_PASSWORD)
        generate_password(pw)
        return

    # If no mode is specified, ask the user what to do
    TOOLS = {
        "1": (ask_and_generate_password, "PASSWORD GENERATOR"),
        "2": (generate_esd_conf, "ESD CONFIG GENERATOR")
    }
    try:
        while True:
            choice = input(
                "What do you want to do?\n"
                "1. Generate an hash of a password (hash)\n"
                "2. Generate the default server configuration file\n"
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