ansi_fg = str
ansi_bg = str
ansi_attr = str

RESET =             "\033[0m"

ATTR_BOLD =         "\033[1m"
ATTR_DARK =         "\033[2m"
ATTR_UNDERLINE =    "\033[4m"
ATTR_BLINK =        "\033[5m"
ATTR_REVERSE =      "\033[7m"
ATTR_CONCEALED =    "\033[8m"

FG_BLACK =          "\033[30m"
FG_RED =            "\033[31m"
FG_GREEN =          "\033[32m"
FG_YELLOW =         "\033[33m"
FG_BLUE =           "\033[34m"
FG_MAGENTA =        "\033[35m"
FG_CYAN =           "\033[36m"
FG_WHITE =          "\033[37m"

BG_BLACK =          "\033[40m"
BG_RED =            "\033[41m"
BG_GREEN =          "\033[42m"
BG_YELLOW =         "\033[43m"
BG_BLUE =           "\033[44m"
BG_MAGENTA =        "\033[45m"
BG_CYAN =           "\033[46m"
BG_WHITE =          "\033[47m"

if __name__ == "__main__":
    from easyshare.utils.hmd import help_markdown_pager

    s = "a string really long"
    sred = FG_RED + s + RESET
    sbold = ATTR_BOLD + s + RESET
    print("len_s", len(s))
    print("len_sred", len(sred))
    print("len_sbold", len(sbold))

    print(help_markdown_pager("""
         <A>
         |     |
a string really long
""", cols=16
    ))

    print(help_markdown_pager("""
         <A>
         |     |
\033[1ma string really long\033[0m
""", cols=16
    ))
