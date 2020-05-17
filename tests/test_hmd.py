import unittest

from easyshare.styling import bold
from easyshare.utils.helpmarkdown import ansistr


class TestHmd(unittest.TestCase):

    def test_ansistr(self):
        self.assertTrue(ansistr(bold("some text")).endswith("t"))

        s = ansistr(bold("a str") + "text")
        self.assertTrue(s.startswith("a"))
        self.assertTrue(s.endswith("ext"))

        # sl_smart = s.sliced(slice(0, 7))
        # self.assertEqual(str(sl_smart), "a strte")

    # TODO a lot of tests...

if __name__ == '__main__':
    unittest.main()