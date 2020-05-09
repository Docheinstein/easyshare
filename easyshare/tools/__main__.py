from getpass import getpass

import pkg_resources

from easyshare.passwd.auth import AuthScrypt
from easyshare.utils.app import abort


def generate_password():
    plain_pass = getpass("Password: ")
    if not plain_pass:
        abort("Please insert a valid password")

    auth = AuthScrypt.new(plain_pass)
    if not auth:
        abort("Cannot compute password")

    print(auth)

def generate_esd_conf():
    esd_conf = pkg_resources.resource_string("easyshare", "res/esd.conf")
    print(str(esd_conf, encoding="UTF-8"))


def main():
    TOOLS = {
        "1": (generate_password, "PASSWORD GENERATOR"),
        "2": (generate_esd_conf, "ESD CONFIG GENERATOR")
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
                RULER_HALF = ((40 - len(funcname)) // 2) * "="

                print("\n{} {} {}\n".format(RULER_HALF, funcname, RULER_HALF))
                func()
                break
            else:
                print("\nPlease provide a valid action number")
            print()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()