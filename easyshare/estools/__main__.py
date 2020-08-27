import pkgutil
import sys

from getpass import getpass

from easyshare.args import ArgsParseError
from easyshare.auth import AuthScrypt
from easyshare.commands.estools import EsToolsUsage, EsTools
from easyshare.common import APP_INFO, easyshare_setup
from easyshare.res.helps import command_usage
from easyshare.utils import abort, terminate


def generate_password(pw: str):
    """
    Print a scrypt hash of the given password.
    """
    auth = AuthScrypt.new(pw)
    if not auth:
        abort("cannot compute password")

    print(auth)

def generate_esd_conf():
    """
    Print the default esd configuration file.
    """
    esd_conf_b = pkgutil.get_data("easyshare.res", "esd.conf")
    esd_conf_s = str(esd_conf_b, encoding="UTF-8")
    print(esd_conf_s)


def generate_esrc():
    """
    Print the default esd configuration file.
    """
    esrc_b = pkgutil.get_data("easyshare.res", ".esrc")
    esrc_s = str(esrc_b, encoding="UTF-8")
    print(esrc_s)


def ask_and_generate_ssl_certificate():
    """
    Actually not implemented within es-tools.
    Let openssl do the job for us.
    """
    print("Please install and use openssl for create a self-signed certificate")
    print("A typical command for create a self-signed request could be:\n")
    print("openssl req -x509 -keyout privkey.pem -days 365 -nodes -out cert.pem")


def ask_and_generate_password():
    """
    getpass() and generate a scrypt hash of the password read.
    """
    plain_pass = getpass("Password: ")
    if not plain_pass:
        abort("please insert a valid password")
    generate_password(plain_pass)

def main():
    easyshare_setup()

    # Parse arguments
    args = None

    try:
        args = EsTools().parse(sys.argv[1:])
    except ArgsParseError as err:
        abort(f"parse of arguments failed: {str(err)}")


    # Help?
    if EsTools.HELP in args:
        command_usage(EsToolsUsage.helpname())
        terminate()

    # Version?
    if EsTools.VERSION in args:
        terminate(APP_INFO)


    # Explicit mode?

    if EsTools.GENERATE_ESD_CONF in args:
        generate_esd_conf()
        return

    if EsTools.GENERATE_ESRC in args:
        generate_esrc()
        return

    if EsTools.GENERATE_PASSWORD in args:
        pw = args.get_option_param(EsTools.GENERATE_PASSWORD)
        generate_password(pw)
        return

    # If no mode is specified, ask the user what to do
    TOOLS = {
        "1": (ask_and_generate_password, "PASSWORD GENERATOR"),
        "2": (generate_esd_conf, "esd.conf GENERATOR"),
        "3": (generate_esrc, ".esrc GENERATOR"),
        "4": (ask_and_generate_ssl_certificate, "SSL CERTIFICATE GENERATOR")
    }
    try:
        while True:
            choice = input(
                "What do you want to do?\n"
                "1. Generate an hash of a password (hash)\n"
                "2. Generate the default server configuration file (esd.conf)\n"
                "3. Generate the default server configuration file (.esrc)\n"
                "4. Generate a self signed SSL certificate\n"
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