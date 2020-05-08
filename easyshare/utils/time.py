
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


if __name__ == "__main__":
    print(duration_str(1313))
    print(duration_str(1313, fixed=False))
    print(duration_str(1313, fixed=False, formats=("{} hours ", "{} minutes ", "{} seconds")))
