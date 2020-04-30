
from easyshare.utils.os import run

if __name__ == "__main__":
    while True:
        try:
            command = input("$ ")
            run(command, lambda line: print(line, end=""))
        except KeyboardInterrupt:
            print("=============")
