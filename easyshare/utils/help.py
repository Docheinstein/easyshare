from easyshare.consts import ansi
from easyshare.logging import get_logger_silent
from easyshare.styling import styled
from easyshare.utils.env import terminal_size

log = get_logger_silent(__name__)

def help_markdown_pager(hmd: str, cols = None, debug_step_by_step = False) -> str: # HelpMarkDown
    if not cols:
        cols, rows = terminal_size()
    last_a_col = 0

    parsed_hdm = ""

    def add_text(l: str, endl=True):
        nonlocal parsed_hdm
        l = (l or "") + ("\n" if endl else "")
        parsed_hdm += l
        log.d("+ %s", styled(l, fg=ansi.FG_CYAN, attrs=ansi.ATTR_BOLD))


    for line_in in hmd.splitlines(keepends=False):
        log.d("'%s'", styled(line_in, attrs=ansi.ATTR_BOLD))
        if debug_step_by_step:
            input()

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

        if len(line_in) <= cols:
            add_text(line_in)
        else:
            log.d("-> breaking line since length %d > %d cols", len(line_in), cols)

            leading = line_in[:alignment]
            space_leading = " " * alignment
            remaining_line_in = line_in[alignment:]

            while len(remaining_line_in) > cols - alignment:
                log.w("--> still longer after break:  '%s'", remaining_line_in)
                head = remaining_line_in[:cols - alignment - 1]
                remaining_line_in = remaining_line_in[cols - alignment - 1:].lstrip()

                if not head.endswith(" ") and remaining_line_in:
                    head += "-"

                log.d("--> cols: %d", cols)
                log.d("--> alignment: %d", alignment)
                log.d("--> leading (%d) = '%s'", len(leading), leading)
                log.d("--> head (%d) = '%s'", len(head), head)
                log.d("--> tail (%d) = '%s'", len(remaining_line_in), remaining_line_in)

                add_text(leading + head)
                leading = space_leading

            add_text(leading + remaining_line_in)

    return parsed_hdm
