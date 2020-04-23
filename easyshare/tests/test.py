import string
import sys
from enum import Enum

from easyshare.shared.args import Args
from easyshare.utils import str
from easyshare.utils.os import ls


def test_ls():
    for fi in ls("/tmp", sort_by="type"):
        print(fi["name"], fi["size"], fi["type"])


def test_args():
    args = Args(sys.argv[1:])
    print(args)
    print(args.get_params(["-s", "--share"]))
    print(args.get_mparams(["-s", "--share"]))
    print(args.get_param(["-p", "--port"]))
    print(args.has_arg(["-v", "--verbose"]))
    print(args.get_param())
    print(args.get_params())
    print(args.get_mparams())


def test_filter():
    print(str.filter("dog/dmwe&", string.ascii_letters))


def return_none_tuple():
    return None, None, None


class Dog(Enum):
    Cat = 1
    Dog = 2

if __name__ == "__main__":
    a, b, c = return_none_tuple()
    print(a)
    print(b)
    print(c)
    print(Dog(1))
    print(Dog(2))
    print(Dog(3))
    # test_ls()
    # test_args()
    # test_filter()
