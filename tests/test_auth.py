import unittest

from easyshare.utils.crypt import scrypt_new, scrypt, bytes_to_b64


class TestAuth(unittest.TestCase):

    def test_scrypt(self):
        m = "hello"

        salt_bin, hash_bin = scrypt_new(m, salt_length=48)
        hash_b2 = scrypt(m, salt_bin)

        self.assertEqual(hash_bin, hash_b2)

        salt_s = bytes_to_b64(salt_bin)
        hash_b3 = scrypt(m, salt_s)

        self.assertEqual(hash_bin, hash_b3)

if __name__ == '__main__':
    unittest.main()