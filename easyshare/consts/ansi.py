# ANSI escapes codes (colors, styles)
from easyshare.utils.env import is_windows

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


PROMPT_BLINK_OFF =  "\033[25m"

UP_LINE =           "\033[A"
DOWN_LINE =         "\033[B"
RIGHT_LINE =        "\033[C"
LEFT_LINE =         "\033[D"

DELETE_R_LINE =     "\033[K"  # delete until end of line
DELETE_LINE =       "\033[2K"  # delete current line

# The bad effect without DELETE_EOL_VT100 is that if the text on the new
# line is not long enough to cover the previous line, a part of it remains printed
# to the screen. But without internal Windows API we cannot do better.
# DELETE_EOL = "\r" if is_windows() else (DELETE_EOL_VT100 + "\r")
RESET_LINE = "\r" if is_windows() else (DELETE_LINE + "\r")

# From readline docs
# declared in `readline.h'
# This may be used to embed terminal-specific escape sequences in prompts.
RL_PROMPT_START_IGNORE = "\001"
RL_PROMPT_END_IGNORE = "\002"
