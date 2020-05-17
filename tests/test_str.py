import re
import string
import unittest

from easyshare.utils.str import keepchars, discardchars, satisfychars, multireplace, rightof, leftof


class TestStr(unittest.TestCase):

    def test_chars(self):
        self.assertEqual(keepchars("mystringg", "mg"), "mgg")
        self.assertEqual(discardchars("mystringg", "mg"), "ystrin")
        self.assertTrue(satisfychars("mystringgxx", string.ascii_letters))
        self.assertFalse(satisfychars("mystringg-xx", string.ascii_letters))

    def test_replace(self):
        self.assertEqual(multireplace(
            "mystringg",
            str_replacements=[
                ("n", "NN"),
                ("gg", "")
            ]
        ), "mystriNN")

        self.assertEqual(multireplace(
            "<b>oh my god</b>",
            re_replacements=[
                (re.compile("</?b>"), "")
            ]
        ), "oh my god")

    def test_partition(self):
        self.assertEqual(rightof("astring:separator", ":", from_end=False),
                         "separator")
        self.assertEqual(rightof("astring:separator:another", ":", from_end=True),
                         "another")
        self.assertEqual(rightof("astring:separator:another", ":", from_end=False),
                         "separator:another")
        self.assertEqual(rightof("astring:separator:another", "=", from_end=False),
                         "astring:separator:another")


        self.assertEqual(leftof("astring:separator", ":", from_end=False),
                         "astring")
        self.assertEqual(leftof("astring:separator:another", ":", from_end=True),
                         "astring:separator")
        self.assertEqual(leftof("astring:separator:another", ":", from_end=False),
                         "astring")
        self.assertEqual(leftof("astring:separator:another", "=", from_end=False),
                         "astring:separator:another")



if __name__ == '__main__':
    unittest.main()
