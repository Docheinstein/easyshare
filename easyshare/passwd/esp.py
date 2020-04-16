from getpass import getpass

from easyshare.passwd.auth import create_auth_string, AuthType
from easyshare.utils.app import abort
from easyshare.utils.crypt import scrypt_new, bytes_to_b64


if __name__ == "__main__":
    plain_pass = getpass("Password: ")
    if not plain_pass:
        abort("Please insert a valid password")

    salt_b, hash_b = scrypt_new(plain_pass, salt_length=16)
    salt_s, hash_s = bytes_to_b64(salt_b), bytes_to_b64(hash_b)
    print(create_auth_string(AuthType.SCRYPT, salt_s, hash_s))
