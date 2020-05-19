import re
import string

from easyshare.utils.str import keepchars, discardchars, satisfychars, multireplace, rightof, leftof


def test_chars():
    assert keepchars("mystringg", "mg") == "mgg"
    assert discardchars("mystringg", "mg") == "ystrin"
    assert satisfychars("mystringgxx", string.ascii_letters)
    assert not satisfychars("mystringg-xx", string.ascii_letters)

def test_replace():
    assert multireplace(
        "mystringg",
        str_replacements=[
            ("n", "NN"),
            ("gg", "")
        ]
    ) == "mystriNN"

    assert multireplace(
        "<b>oh my god</b>",
        re_replacements=[
            (re.compile("</?b>"), "")
        ]
    ) == "oh my god"

def test_partition():
    assert rightof("astring:separator", ":", from_end=False) == \
           "separator"
    assert rightof("astring:separator:another", ":", from_end=True) == \
           "another"
    assert rightof("astring:separator:another", ":", from_end=False) == \
           "separator:another"
    assert rightof("astring:separator:another", "=", from_end=False) == \
           "astring:separator:another"


    assert leftof("astring:separator", ":", from_end=False) == \
                     "astring"
    assert leftof("astring:separator:another", ":", from_end=True) == \
                     "astring:separator"
    assert leftof("astring:separator:another", ":", from_end=False) == \
                     "astring"
    assert leftof("astring:separator:another", "=", from_end=False) == \
                     "astring:separator:another"