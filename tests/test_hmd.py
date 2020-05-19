from easyshare.styling import bold
from easyshare.utils.helpmarkdown import ansistr


def test_ansistr():
    assert ansistr(bold("some text")).endswith("t")

    s = ansistr(bold("a str") + "text")
    assert s.startswith("a")
    assert s.endswith("ext")

    # sl_smart = s.sliced(slice(0, 7))
    # self.assertEqual(str(sl_smart), "a strte")

# TODO a lot of tests...