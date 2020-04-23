from getpass import getpass

from easyshare.passwd.auth import AuthScrypt
from easyshare.utils.app import abort


if __name__ == "__main__":
    plain_pass = getpass("Password: ")
    if not plain_pass:
        abort("Please insert a valid password")

    auth = AuthScrypt.new(plain_pass)
    if not auth:
        abort("Cannot compute password")

    print(auth)
