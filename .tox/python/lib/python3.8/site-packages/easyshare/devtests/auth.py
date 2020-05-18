from base64 import b64encode, b64decode
from getpass import getpass

from easyshare.utils.crypt import scrypt, scrypt_new, bytes_to_b64, b64_to_bytes, str_to_b64
from easyshare.utils.types import str_to_bytes


def main():
    plain_pass = getpass("Real password: ")
    salt_b, hash_b = scrypt_new(plain_pass, salt_length=16)
    salt_s, hash_s = bytes_to_b64(salt_b), bytes_to_b64(hash_b)
    # salt_s = "banana"

    print("salt_s: ", salt_s)
    print("hash_s: ", hash_s)

    salt_known = b64_to_bytes(salt_s)

    ask_pass = getpass("Guess password: ")
    hash_computed = scrypt(ask_pass, salt=salt_known)
    hash_computed_s = bytes_to_b64(hash_computed)

    print("hash_compute_s: ", hash_computed_s)

    if hash_computed == hash_b:
        print("Auth OK!")
    else:
        print("Auth ERROR")


if __name__ == "__main__":
    salt_b = b"pippo furfante"
    salt = bytes_to_b64(salt_b)

    print("salt_b", salt_b)
    print("salt", salt)

    salt_b2 = b64_to_bytes(salt)
    salt2 = bytes_to_b64(salt_b)

    print("salt_b2", salt_b2)
    print("salt2", salt2)

    # s = "pippo"
    # s2 = b64decode(b64encode(str_to_bytes(s)))
    # sb = str_to_bytes(s)
    # s2 = bytes_to_b64(b64_to_bytes(sb))
    # print(s)
    # print(s2)
    main()