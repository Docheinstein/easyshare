import os
import string
import sys
import threading
import time

import utils
from args import Args
from utils import filter_string

def test_ls():
    for fi in utils.ls("/tmp", sort_by="type"):
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
    print(filter_string("dog/dmwe&", string.ascii_letters))


if __name__ == "__main__":
    test_ls()
    # test_args()
    # test_filter()
