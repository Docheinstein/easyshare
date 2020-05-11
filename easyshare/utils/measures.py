from easyshare.consts.units import K, M, G

UNITS = (1, K, M, G)

def duration_str_human(seconds: int) -> str:
    return duration_str(seconds, fixed=False, formats=("{}h ", "{}m ", "{}s"))

def duration_str(seconds: int, *,
                 fixed: bool = True,
                 formats=("{:02}:", "{:02}:", "{:02}")):
    hours, remainder = divmod(seconds, 3600)
    mins, secs = divmod(remainder, 60)

    if fixed or hours > 0:
        return "".join(formats).format(hours, mins, secs)
    elif mins > 0:
        return "".join(formats[1:]).format(mins, secs)
    else:
        return "".join(formats[2:]).format(secs)


def speed_str(size: float) -> str:
    return size_str(size, prefixes=("B/s", "KB/s", "MB/s", "GB/s"))


def size_str(size: float,
             prefixes=("B", "KB", "MB", "GB"),
             precisions=(0, 0, 1, 1)) -> str:
    i = len(UNITS) - 1
    while i >= 0:
        u = UNITS[i]
        if size > u:
            return ("{:0." + str(precisions[i]) + "f}{}").format(size / u, prefixes[i])
        i -= 1
    return "0{}".format(prefixes[0])


if __name__ == "__main__":
    print(duration_str(1313))
    print(duration_str(1313, fixed=False))
    print(duration_str(1313, fixed=False, formats=("{} hours ", "{} minutes ", "{} seconds")))

