from easyshare.auth import AuthFactory, AuthScrypt
from easyshare.utils.crypt import scrypt_new, scrypt, bytes_to_b64
from easyshare.utils.rand import randstring


def test_scrypt():
    m = randstring()

    salt_bin, hash_bin = scrypt_new(m, salt_length=48)
    hash_b2 = scrypt(m, salt_bin)

    assert hash_bin == hash_b2

    salt_s = bytes_to_b64(salt_bin)
    hash_b3 = scrypt(m, salt_s)

    assert hash_bin == hash_b3


def test_plain_auth():
    plaintext = randstring()

    # Plain auth check
    assert (AuthFactory.parse(plaintext).authenticate(plaintext))

def test_consecutive_scrypt_different():
    plaintext = randstring()

    auth_enc1 = AuthScrypt.new(plaintext)
    auth_enc2 = AuthScrypt.new(plaintext)

    # Two consecutive creations should be different
    assert str(auth_enc1) != str(auth_enc2)

def test_scrypt_parse():
    plaintext = randstring()

    auth_enc1 = AuthScrypt.new(plaintext)

    auth_str = str(auth_enc1)
    auth_dec = AuthFactory.parse(auth_str)

    # Are we parsing correctly?
    assert str(auth_dec) == auth_str

def test_scrypt_auth():
    plaintext = randstring()

    auth_enc1 = AuthScrypt.new(plaintext)

    auth_str = str(auth_enc1)
    auth_dec = AuthFactory.parse(auth_str)

    # Match against plaintext
    assert auth_dec.authenticate(plaintext)