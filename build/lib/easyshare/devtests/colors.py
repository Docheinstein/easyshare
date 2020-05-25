from easyshare.styling import red, enable_colors, styled, Color, Style

if __name__ == "__main__":
    enable_colors()
    s0 = "ciao"
    s1 = red(s0)
    s2 = styled(s0, fg=Color.RED, attrs=Style.BOLD)
    s3 = styled(s0, fg=Color.RED, bg=Color.WHITE, attrs=Style.BOLD)

    print(s0)
    print(s1)
    print(s2)
    print(s3)

    print([s0])
    print([s1])
    print([s2])
    print([s3])

    print(len(s0))
    print(len(s1))
    print(len(s2))
    print(len(s3))

    print(len("\x1b"))
    print(len("1b"))