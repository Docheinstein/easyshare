import re
from typing import Optional, Tuple

from easyshare import logging
from easyshare.consts import ansi
from easyshare.logging import get_logger
from easyshare.styling import styled
from easyshare.utils.env import terminal_size

# log = get_logger_silent(__name__)
from easyshare.utils.str import multireplace

log = get_logger(__name__)

I_START_REGEX = re.compile(r"^<([iI]\d+)>")
I_END_REGEX = re.compile(r"</([iI]\d+)>$")
ANSI_REGEX = re.compile(r"(\033\[\d+m)")
# I_END_REGEX = re.compile(r"</([iI]\d+)>")


class ansistr:
    def __init__(self, string):
        # print("ansistr of {}".format(string))
        self._string = string
        self._escaped_string = re.sub(ANSI_REGEX, "", string)

        self._ansis = []

        offset = 0
        for m in re.finditer(ANSI_REGEX, self._string):
            # print("m:", m)
            self._ansis.insert(0, (m.start() - offset, m.group()))
            offset += m.end() - m.start()

        # print(self._string)
        # print(self._escaped_string)
        # print(self._ansis)

    def __str__(self):
        return self._string

    def __len__(self):
        return self.len()

    def __add__(self, other):
        return ansistr(str(self._string) + str(other))


    def __getitem__(self, item):
        if isinstance(item, slice):
            return self.sliced(item)
        return self.sliced_raw(item)

    # def ansis(self) -> List[str]:
    #     return [a[1] for a in self._ansis]

    def startswith(self, pattern):
        return self._escaped_string.startswith(pattern)

    def endswith(self, pattern):
        return self._escaped_string.endswith(pattern)

    def lstrip(self):
        first_ansi_tag = self.first_ansi()
        if first_ansi_tag and first_ansi_tag[0] == 0:
            # print("first_ansi_tag start at 0")
            # lstrip to the string without the leading ansi tag
            return ansistr(first_ansi_tag[1] + self._string[len(first_ansi_tag[1]):].lstrip())
        # print("lstrip of {}".format(self._string))

        return ansistr(self._string.lstrip())

    def first_ansi(self) -> Optional[Tuple[int, str]]:
        if self._ansis:
            return self._ansis[len(self._ansis) - 1]
        return None

    def last_ansi(self) -> Optional[Tuple[int, str]]:
        if self._ansis:
            return self._ansis[0]
        return None

    def sliced(self, slicing) -> 'ansistr':
        # print("__getitem__", slicing)
        slicing_start = slicing.start or 0
        slicing_stop = slicing.stop or len(self._escaped_string)
        new_s = self._escaped_string[slicing_start:slicing_stop]

        # print("new_s before", new_s)

        for el in self._ansis:
            ansi_pos, ansi_sequence = el
            if slicing_start <= ansi_pos < slicing_stop:
                ansi_pos_correct = ansi_pos - slicing_start
                # print(f"ansi pos {ansi_pos} ({ansi_pos_correct}) within {slicing_start}:{slicing_stop}")
                new_s = new_s[:ansi_pos_correct] + ansi_sequence + new_s[ansi_pos_correct:]

        return ansistr(new_s)

    def sliced_raw(self, slicing) -> str:
        return self._string.__getitem__(slicing)

    def len(self):
        length = len(self._string)
        matches = re.findall(ANSI_REGEX, self._string)
        for m in matches:
            length -= len(m)
        return length

    def len_raw(self):
        return len(self._string)


if __name__ == "__main__":
    from easyshare.styling import bold

    log.set_verbosity(logging.VERBOSITY_MAX)

    assert ansistr(bold("some text")).endswith("t")

    s = ansistr(bold("a str") + "text")
    assert s.startswith("a")
    assert s.endswith("ext")
    # print(s.len())
    # print(s.len_raw())

    sl_smart = s.sliced(slice(0, 7))
    sl_raw = s.sliced_raw(slice(0, 7))
    print(f"sl_ansi |{len(sl_smart)}| {sl_smart}")
    print(f"sl_raw |{len(sl_raw)}| {sl_raw}")

    # sl_smart = s.sliced(slice(2, 7))
    # sl_raw = s.sliced_raw(slice(2, 7))
    # print(f"sl_ansi |{len(sl_smart)}| {sl_smart}")
    # print(f"sl_raw |{len(sl_raw)}| {sl_raw}")
    # #
    # sl_smart = s.sliced(slice(2, 5))
    # sl_raw = s.sliced_raw(slice(2, 5))
    # print(f"sl_ansi |{len(sl_smart)}| {sl_smart}")
    # print(f"sl_raw |{len(sl_raw)}| {sl_raw}")

def help_markdown_to_str(hmd: str, cols = None, debug_step_by_step = False) -> str: # HelpMarkDown
    if not cols:
        cols, rows = terminal_size()
        cols -= 1 # For permit scrollbars of terminal emulators


    last_a_col = 0
    last_i = 0

    parsed_hdm = ""

    def add_ansistr(al: ansistr, *, indent: int = 0, endl=True) -> ansistr:
        nonlocal parsed_hdm
        last_open_ansi = al.last_ansi()
        open_tag = last_open_ansi[1] if last_open_ansi else ""
        end_tag = ""
        if open_tag and open_tag != ansi.RESET:
            log.w("There is an open ansi tag")
            end_tag = ansi.RESET
        l = str(al)
        l = " " * indent + (l or "") + ("\n" if endl else "") + end_tag
        parsed_hdm += l
        log.d("+ %s", styled(l, fg=ansi.FG_CYAN, attrs=ansi.ATTR_BOLD))

        return ansistr(open_tag)

    # leading_ansi_tag = ansistr("")

    for line_in in hmd.splitlines(keepends=False):
        reset_i = False

        log.d("'%s'", styled(line_in, attrs=ansi.ATTR_BOLD))
        if debug_step_by_step:
            input()

        indents = re.findall(I_START_REGEX, line_in)
        if indents:
            indent_tag = indents[len(indents) - 1]
            last_i = int(indent_tag[1:])
            log.d("Found new indentation: %d", last_i)
            if indent_tag[0] == "I":
                continue # don't keep the line into account

        line_in = re.sub(I_START_REGEX, "", line_in) # strip <i*>

        log.d("Will add indentation of %d", last_i)

        # strip </i*>
        indents = re.findall(I_END_REGEX, line_in)
        if indents:
            indent_tag = indents[len(indents) - 1]

            if indent_tag[0] == "I":
                last_i = 0
                continue # don't keep the line into account

            reset_i = True # don't set last_i now, will be set at the end of the iter
            log.d("Resetting indentation")


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

        line_in = multireplace(line_in, {
            "<b>": ansi.ATTR_BOLD,
            "</b>": ansi.RESET,
            "<u>": ansi.ATTR_UNDERLINE,
            "</u>": ansi.RESET,
        })

        # Make an ansi aware string
        line_in = ansistr(line_in)
        # line_in = leading_ansi_tag + line_in

        if len(line_in) + last_i <= cols:
            # leading_ansi_tag = add_ansistr(line_in, indent=last_i)
            add_ansistr(line_in, indent=last_i)
        else:
            log.d("-> breaking line since length %d > %d cols", len(line_in), cols)

            leading = line_in[:alignment]
            space_leading = ansistr(" " * alignment)
            remaining_line_in = line_in[alignment:]
            current_i = last_i
            remaining_space = cols - alignment - current_i

            while len(remaining_line_in) > remaining_space:
                log.w("--> still longer after break:  '%s'", remaining_line_in)
                head = remaining_line_in[:remaining_space - 1]

                # remaining_line_in = leading_ansi_tag + remaining_line_in[remaining_space - 1:].lstrip()
                # remaining_line_in = leading_ansi_tag + remaining_line_in[remaining_space - 1:]
                remaining_line_in = remaining_line_in[remaining_space - 1:]
                if not head.endswith(" ") and len(remaining_line_in) > 0:
                    head += "-"

                log.d("--> cols: %d", cols)
                log.d("--> alignment: %d", alignment)
                log.d("--> leading (%d) = '%s'", len(leading), leading)
                log.d("--> head (%d) = '%s'", len(head), head)
                log.d("--> tail (%d) = '%s'", len(remaining_line_in), remaining_line_in)
                log.d("--> last_i = %d", last_i)
                log.d("--> len(leading) = %d", len(leading))

                leading_ansi_tag = add_ansistr(leading + head, indent=current_i)

                remaining_line_in = leading_ansi_tag + remaining_line_in.lstrip()

                leading = space_leading
                current_i = max(0, last_i - len(leading))
                remaining_space = cols - alignment - current_i

            add_ansistr(leading + remaining_line_in, indent=current_i)

        if reset_i:
            last_i = 0

    return parsed_hdm


#     print(len(s))
#     print(s.raw_len())
#
#     print(s[1])
#     print(s[0:2])
# #
#     print(help_markdown_pager("""\
#     <A>
# <i4>An indented text of the super text very very long that will break the line</i8>
#     """,
#     cols=40
#     ))
#
#     print(help_markdown_pager("""\
#     <A>
# <i0>An indented text of the super text very very long that will break the line</i8>
#     """,
#     cols=40
#     ))