import string
import sys

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


if __name__ == "__main__":
    test_ls()
    # test_args()
    # test_filter()
