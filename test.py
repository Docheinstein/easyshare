import os
import string
import sys
import threading
import time

from args import Args
from utils import filter_string


def test_args():
    args = Args(sys.argv[1:])
    print(args)
    print(args.get_params(["s", "share"]))
    print(args.get_mparams(["s", "share"]))
    print(args.get_param(["p", "port"]))
    print(args.has_arg(["v", "verbose"]))

def test_filter():
    print(filter_string("dog/dmwe&", string.ascii_letters))

if __name__ == "__main__":
    # test_args()
    test_filter()
