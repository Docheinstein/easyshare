import os
import sys
import threading
import time

from args import Args

if __name__ == "__main__":
    args = Args(sys.argv[1:])
    print(args)
    print(args.get_params(["s", "share"]))
    print(args.get_param(["p", "port"]))
    print(args.has_arg(["v", "verbose"]))
