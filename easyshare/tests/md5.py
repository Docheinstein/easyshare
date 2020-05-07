import hashlib
import sys
import time
import zlib

if __name__ == "__main__":
    filename = sys.argv[1]

    start = time.monotonic_ns()
    with open(filename, "rb") as f:
        file_md5 = hashlib.md5()
        while chunk := f.read(4096):
            file_md5.update(chunk)
    end = time.monotonic_ns()


    # print(file_hash.digest())
    print("MD5 Time: {}".format((end - start) * 1e-6))
    print("MD5 Digest: {}".format(file_md5.hexdigest()))


    start = time.monotonic_ns()
    with open(filename, "rb") as f:
        file_crc32 = 0
        while chunk := f.read(4096):
            file_crc32 = zlib.crc32(chunk, file_crc32)
    end = time.monotonic_ns()


    # print(file_hash.digest())
    print("CRC32 Time: {}".format((end - start) * 1e-6))
    print("CRC32 Digest: {}".format(file_crc32))