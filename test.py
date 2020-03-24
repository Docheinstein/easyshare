import os
import sys

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    print("Listing " + path)

    for root, directories, files in os.walk(path):
        for directory in directories:
            print(os.path.join(root, directory))
        for file in files:
            print(os.path.join(root, file))
