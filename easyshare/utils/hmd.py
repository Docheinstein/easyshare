import re

from easyshare import logging
from easyshare.consts import ansi
from easyshare.logging import get_logger_silent, get_logger
from easyshare.styling import styled
from easyshare.utils.env import terminal_size

# log = get_logger_silent(__name__)
log = get_logger(__name__)

I_START_REGEX = re.compile(r"^<(i\d+)>")
I_END_REGEX = re.compile(r"<(/i\d+)>$")
# I_END_REGEX = re.compile(r"</([iI]\d+)>")

def help_markdown_pager(hmd: str, cols = None, debug_step_by_step = False) -> str: # HelpMarkDown
    if not cols:
        cols, rows = terminal_size()

    last_a_col = 0
    last_i = 0

    parsed_hdm = ""

    def add_text(l: str, *, indent: int = 0, endl=True):
        nonlocal parsed_hdm
        l = " " * indent + (l or "") + ("\n" if endl else "")
        parsed_hdm += l
        log.d("+ %s", styled(l, fg=ansi.FG_CYAN, attrs=ansi.ATTR_BOLD))


    for line_in in hmd.splitlines(keepends=False):
        reset_i = False

        log.d("'%s'", styled(line_in, attrs=ansi.ATTR_BOLD))
        if debug_step_by_step:
            input()

        # Indent <i*></i*>
        # indents = re.findall(I_REGEX, line_in)
        #
        # if indents:
        #     indent_tag = indents[len(indents) - 1]
        #     last_i = int(last_indent_tag[1:])
        #     log.d("Found new indentation: %d", last_i)
        #
        #     if last_indent_tag[0] == "I":
        #         continue  # don't keep the line into account
        #
        # # Add the indentation
        # line_in = re.sub(I_BEGIN_REGEX, "", line_in) # strip <i*>
        # line_in = re.sub(I_END_REGEX, "", line_in) # strip </i*>
        #

        indents = re.findall(I_START_REGEX, line_in)
        if indents:
            indent_tag = indents[len(indents) - 1]
            last_i = int(indent_tag[1:])
            log.d("Found new indentation: %d", last_i)

        line_in = re.sub(I_START_REGEX, "", line_in) # strip <i*>

        log.d("Adding indentation of %d", last_i)
        # line_in = " " * last_i + line_in

        # strip </i*>
        indents = re.findall(I_END_REGEX, line_in)
        if indents:
            reset_i = True
            log.d("Resetting indentation: %d", last_i)

        line_in = re.sub(I_END_REGEX, "", line_in) # strip </i*>

        # Alignment <a> OR <A>
        # <a> will be stripped out lonely
        # <A> will be stripped out with the entire line

        # Remind the position of an eventual <a>/<A> tag on this line

        a_idx = line_in.find("<a>")
        if a_idx != -1:
            log.d("-> Found <a> at col: %d", a_idx)
            last_a_col = a_idx
            line_in = line_in.replace("<a>", "") # strip <a>

        a_idx = line_in.find("<A>")
        if a_idx != -1:
            log.d("-> Found <A> at col: %d", a_idx)
            last_a_col = a_idx
            continue # don't keep the line into account

        if last_a_col > cols:
            # <a> tag is outside the current columns
            log.w("Align tag <a> position exceed current cols: %d > %d", last_a_col, cols)
            alignment = 0
        else:
            alignment = last_a_col

        # Bold <b></b>

        line_in = line_in.replace("<b>", ansi.ATTR_BOLD)
        line_in = line_in.replace("</b>", ansi.RESET)

        # Underline <u></u>

        line_in = line_in.replace("<u>", ansi.ATTR_UNDERLINE)
        line_in = line_in.replace("</u>", ansi.RESET)

        if len(line_in) <= cols:
            add_text(line_in, indent=last_i)
        else:
            log.d("-> breaking line since length %d > %d cols", len(line_in), cols)

            leading = line_in[:alignment]
            space_leading = " " * alignment
            remaining_line_in = line_in[alignment:]
            current_i = last_i
            remaining_space = cols - alignment - current_i

            while len(remaining_line_in) > remaining_space:
                log.w("--> still longer after break:  '%s'", remaining_line_in)
                head = remaining_line_in[:remaining_space - 1]
                remaining_line_in = remaining_line_in[remaining_space - 1:].lstrip()

                if not head.endswith(" ") and remaining_line_in:
                    head += "-"

                log.d("--> cols: %d", cols)
                log.d("--> alignment: %d", alignment)
                log.d("--> leading (%d) = '%s'", len(leading), leading)
                log.d("--> head (%d) = '%s'", len(head), head)
                log.d("--> tail (%d) = '%s'", len(remaining_line_in), remaining_line_in)
                log.d("--> last_i = %d", last_i)
                log.d("--> len(leading) = %d", len(leading))

                add_text(leading + head, indent=current_i)
                leading = space_leading
                current_i = max(0, last_i - len(leading))
                remaining_space = cols - alignment - current_i

            add_text(leading + remaining_line_in, indent=current_i)

        if reset_i:
            last_i = 0

    return parsed_hdm

if __name__ == "__main__":
    log.set_verbosity(logging.VERBOSITY_MAX)

    print(help_markdown_pager("""\
    <A>
<i4>An indented text of the super text very very long that will break the line</i8>
    """,
    cols=40
    ))

    print(help_markdown_pager("""\
    <A>
<i0>An indented text of the super text very very long that will break the line</i8>
    """,
    cols=40
    ))