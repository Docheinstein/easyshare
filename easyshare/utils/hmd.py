import re
from typing import Optional, Tuple

from easyshare import logging
from easyshare.consts import ansi
from easyshare.logging import get_logger
from easyshare.utils.env import terminal_size

# log = get_logger_silent(__name__)
from easyshare.utils.str import multireplace
from easyshare.utils.types import to_int

log = get_logger(__name__)

A_START_REGEX = re.compile("<([aA])>")
A_END_REGEX = re.compile("</([aA])>")

I_START_REGEX = re.compile(r"<([iI])(\+?)(\d+)>")
I_END_REGEX = re.compile(r"</([iI]\d*)>")

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

    def __repr__(self):
        return repr(self._string)

    def __str__(self):
        return self._string

    def __len__(self):
        return self.len()

    def __add__(self, other):
        return ansistr(str(self._string) + str(other))

    def __eq__(self, other):
        if isinstance(other, ansistr):
            return self._string == other._string
        if isinstance(other, str):
            return self == ansistr(other)
        raise ValueError("__eq__ don't know what to do for item of unknown type")

    def __getitem__(self, item):
        if isinstance(item, slice):
            return self.sliced(item)
        if isinstance(item, int):
            return self.sliced(slice(item, item + 1))
        raise ValueError("__getitem__ don't know what to do for item of unknown type")

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

        return ansistr(self.raw().lstrip())

    def first_ansi_match(self) -> Optional[Tuple[int, str]]:
        if self._ansis:
            return self._ansis[len(self._ansis) - 1]
        return None

    def first_ansi(self) -> str:
        return self.first_ansi_match()[1] if self.first_ansi_match() else ""


    def last_ansi_match(self) -> Optional[Tuple[int, str]]:
        if self._ansis:
            return self._ansis[0]
        return None

    def last_ansi(self) -> str:
        return self.last_ansi_match()[1] if self.last_ansi_match() else ""


    def sliced(self, slicing) -> 'ansistr':
        # print("slicing {} by {}".format(repr(self), slicing))
        # print("ansistr._ansis is: {}".format(self._ansis))

        slicing_start = slicing.start or 0
        slicing_stop = slicing.stop or len(self._escaped_string)
        new_s = self._escaped_string[slicing_start:slicing_stop]

        # print("> _escaped_string sliced '{}'".format(new_s))

        for el in self._ansis:
            ansi_pos, ansi_sequence = el
            if slicing_start <= ansi_pos <= slicing_stop:
                ansi_pos_correct = ansi_pos - slicing_start
                # print(f"> ansi pos {ansi_pos} ({ansi_pos_correct}) within {slicing_start}:{slicing_stop}")
                new_s = new_s[:ansi_pos_correct] + ansi_sequence + new_s[ansi_pos_correct:]

        astr = ansistr(new_s)
        # print("> sliced astr =", repr(astr))

        return astr

    def raw(self) -> str:
        return self._string

    def len(self):
        length = len(self._string)
        matches = re.findall(ANSI_REGEX, self._string)
        for m in matches:
            length -= len(m)
        return length


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

class HelpMarkdownParseError(Exception):
    pass


class HelpMarkdown:
    def __init__(self, markdown: str):
        self._markdown = markdown


    def to_term_str(self, cols = None, styled = True) -> str:
        try:
            return self._to_term_str(cols, styled)
        except Exception as err:
            raise HelpMarkdownParseError(str(err))


    def _to_term_str(self, cols = None, styled = True) -> str:
        if not cols:
            cols, rows = terminal_size()
            cols -= 1  # stay on the safe side,
            # allow scrollbars of terminal emulators too

        log.d("HelpMarkdown - cols = %d", cols)

        self._i_stack = []
        self._a_stack = []
        self._awaiting_ansi = ""
        self._output = ""

        for line_in in self._markdown.splitlines(keepends=False):
            pop_i = 0
            pop_a = 0
            keep_line = True

            log.d("READ '%s'", line_in)

            # --------------------------------------
            # INDENT
            # <i*> will be stripped out lonely
            # <I*> will be stripped out with the entire line

            # <i*>
            indents = re.findall(I_START_REGEX, line_in)
            if indents:

                if len(indents) > 1:
                    log.w("Found more than an indent per line")

                for indent in indents:
                    i, plus, val = indent
                    indent_value = to_int(val, raise_exceptions=True)

                    if plus:
                        log.d("Detect relative indent increasing")
                        indent_value += self._current_indent()

                    self._set_indent(indent_value)

                    if i == "I": # <I*>
                        keep_line = False # don't keep the line into account

            # </i*>
            indents = re.findall(I_END_REGEX, line_in)
            if indents:
                pop_i = len(indents)

                for indent in indents:
                    # At the end of the iter pop the current indentation from the stack

                    indent_match = indent

                    if indent_match[0] == "I":
                        keep_line = False # don't keep the line into account

            # --------------------------------------
            # ALIGNMENT
            # <a> will be stripped out lonely
            # <A> will be stripped out with the entire line

            # TODO: multiple <a> per line will break
            al_start_idx = line_in.find("<a>")
            au_start_idx = line_in.find("<A>")
            a_start_idx = max(al_start_idx, au_start_idx)

            keep_line = keep_line and (au_start_idx == -1)


            if a_start_idx != -1:
                if a_start_idx + self._current_indent() < cols:
                    self._set_align(a_start_idx)
                else:
                    # <a> tag is outside the current columns
                    log.w("Align tag <a> position (+ indent) exceed current cols: %d > %d",
                          a_start_idx + self._current_indent(), cols)
                    self._set_align(0)

            # </a>
            aligns = re.findall(A_END_REGEX, line_in)
            if aligns:
                pop_a = len(aligns)

                for align in aligns:
                    # At the end of the iter pop the current indentation from the stack
                    if align[0] == "A":
                        keep_line = False  # don't keep the line into account

            # --------------------------------------
            # LINE BREAKING and real insertion

            if keep_line:
                # Strip tags
                line_in = multireplace(line_in,
                   str_replacements=[
                       ("<a>", ""),
                       ("</a>", ""),
                       ("<b>", ansi.ATTR_BOLD if styled else ""),
                       ("</b>", ansi.RESET if styled else ""),
                       ("<u>", ansi.ATTR_UNDERLINE if styled else ""),
                       ("</u>", ansi.RESET if styled else ""),
                   ],
                   re_replacements=[
                       (I_START_REGEX, ""),
                       (I_END_REGEX, ""),
                   ]
                )

                # Make an ansi aware string
                line_in = ansistr(line_in)

                available_space = cols - self._current_indent()

                if len(line_in) <= available_space:
                    self._add_line(line_in)
                else:
                    log.d("-> breaking line since length %d >= %d cols",
                          len(line_in), available_space)

                    # Treat the first line specially since won' be aligned
                    # but just indented
                    # If the line doesn't fit after the first add_line,
                    # the consecutive parts of the line will be aligned
                    line_no_fit_part = line_in
                    do_align = False

                    while True:
                        # Keep the alignment into account for the available space
                        available_space = cols - self._current_indent() - (do_align * self._current_align())

                        if len(line_no_fit_part) <= available_space:
                            break

                        log.d("--> available space = %d (need align = %s)", available_space, do_align)
                        log.d("--> still longer after break:  '%s'", line_no_fit_part)
                        line_fit_part = line_no_fit_part[:available_space] # make room for "-"
                        line_no_fit_part = line_no_fit_part[available_space:]

                        if len(line_no_fit_part) >= 2:
                            line_no_fit_c1 = line_no_fit_part[0]
                            line_no_fit_c2 = line_no_fit_part[1]
                            if line_no_fit_c1[0] == " " and \
                                    line_no_fit_c2[1] != " ":
                                line_no_fit_part = line_no_fit_part.lstrip()

                        # Add a trailing "-" if there's still something to render
                        # and if the line doesn't end with a space
                        if not line_fit_part.endswith(" ") and len(line_no_fit_part) > 0:
                            log.d("--> adding trailing '-' to fit part %s", repr(line_fit_part))
                            line_fit_part += "-"

                        self._add_line(line_fit_part, align=do_align)

                        # Always do alignment, apart from the first iter
                        do_align = True


                    self._add_line(line_no_fit_part, align=do_align)
            else:
                log.d("Ignoring line due to upper case tag")

            # Cleanup due to end tags
            for _ in range(0, pop_a):
                self._unset_align()

            for _ in range(0, pop_i):
                self._unset_indent()

        if self._a_stack:
            log.w("Detected unclosed <a> tags at the end of the parsing, had value = %d", self._current_align())
        if self._i_stack:
            log.w("Detected unclosed <i> tags at the end of the parsing, had value = %d", self._current_indent())

        return self._output


    # Alignment

    def _set_align(self, align: int):
        log.d("SET align: %d", align)
        self._a_stack.append(align)

    def _unset_align(self):
        log.d("UNSET align")
        if self._a_stack:
            self._a_stack.pop()
        else:
            log.w("<a> stack already empty")
        log.d("CURRENT align: %d", self._current_align())

    def _current_align(self) -> int:
        if self._a_stack:
            return self._a_stack[len(self._a_stack) - 1]
        return 0

    # Indent

    def _set_indent(self, indent: int):
        log.d("SET indent: %d", indent)
        self._i_stack.append(indent)

    def _unset_indent(self):
        log.d("UNSET indent")
        if self._i_stack:
            self._i_stack.pop()
        else:
            log.w("<i> stack already empty")
        log.d("CURRENT indent: %d", self._current_indent())

    def _current_indent(self) -> int:
        if self._i_stack:
            return self._i_stack[len(self._i_stack) - 1]
        return 0


    def _add_line(self, astr: ansistr, *, align: bool = False):
        log.d("add_line()")
        log.d("-> raw = '%s'", astr.raw())
        log.d("-> raw repr = %s", repr(astr.raw()))
        log.d("-> current indent = %d", self._current_indent())
        log.d("-> current align = %d", self._current_align())

        # Build line as <indent>[<align>][awaiting_ansi_tag]<str>
        # The awaiting ansi tag is an eventual tag that has been broken
        # in the previous add_line and thus add to be re-enabled.
        s = str(astr)
        escaped = astr._escaped_string.strip().replace("\n", "")

        line = ""

        if escaped:
            line = " " * self._current_indent() + \
                   " " * (self._current_align() if align else 0) + \
                   self._awaiting_ansi + s

            # Check whether the line ends with a valid ansi tag that is not RESET.
            # In that case we have to remember what tag it is in order to restore
            # it on the next call o _add_line
            self._awaiting_ansi = astr.last_ansi()

            if self._awaiting_ansi and self._awaiting_ansi != ansi.RESET:
                log.w("There is an open ansi tag %s before breaking line; adding RESET", repr(self._awaiting_ansi))
                line += ansi.RESET
        else:
            log.d("Empty line detected")
        # else: do not put anything else but just \n
        # (otherwise ansi might apply to whitespaces)
        # which leads to stuff like underlined spaces

        line += "\n"

        log.d("[+]%s", repr(line))
        log.d("=> '%s'", line)
        self._output += line
#
#
# def help_markdown_to_str(hmd: str, cols = None, debug_step_by_step = False) -> str: # HelpMarkDown
#
#     # # Keep of stack of <i>
#     # i_stack = []
#     #
#     # # Keep a stack of <a>
#     # a_stack = []
#     #
#     # # last_a_col = 0
#     # # last_i = 0
#
#     # parsed_hdm = ""
#
#     def add_ansistr(al: ansistr, *, indent: int = 0, endl=True) -> ansistr:
#         nonlocal parsed_hdm
#         last_open_ansi = al.last_ansi()
#         open_tag = last_open_ansi[1] if last_open_ansi else ""
#         end_tag = ""
#         if open_tag and open_tag != ansi.RESET:
#             log.w("There is an open ansi tag")
#             end_tag = ansi.RESET
#         l = str(al)
#         l = " " * indent + (l or "") + ("\n" if endl else "") + end_tag
#         parsed_hdm += l
#         log.d("+ %s", styled(l, fg=ansi.FG_CYAN, attrs=ansi.ATTR_BOLD))
#
#         return ansistr(open_tag)
#
#     # leading_ansi_tag = ansistr("")
#
#     for line_in in hmd.splitlines(keepends=False):
#         reset_i = False
#
#         log.d("'%s'", styled(line_in, attrs=ansi.ATTR_BOLD))
#         if debug_step_by_step:
#             input()
#
#         indents = re.findall(I_START_REGEX, line_in)
#         if indents:
#             indent_tag = indents[len(indents) - 1]
#             last_i = int(indent_tag[1:])
#             log.d("Found new indentation: %d", last_i)
#             if indent_tag[0] == "I":
#                 continue # don't keep the line into account
#
#         line_in = re.sub(I_START_REGEX, "", line_in) # strip <i*>
#
#         log.d("Will add indentation of %d", last_i)
#
#         # strip </i*>
#         indents = re.findall(I_END_REGEX, line_in)
#         if indents:
#             indent_tag = indents[len(indents) - 1]
#
#             if indent_tag[0] == "I":
#                 last_i = 0
#                 continue # don't keep the line into account
#
#             reset_i = True # don't set last_i now, will be set at the end of the iter
#             log.d("Resetting indentation")
#
#
#         line_in = re.sub(I_END_REGEX, "", line_in) # strip </i*>
#
#         # Alignment <a> OR <A>
#         # <a> will be stripped out lonely
#         # <A> will be stripped out with the entire line
#
#         # Remind the position of an eventual <a>/<A> tag on this line
#
#         a_idx = line_in.find("<a>")
#         if a_idx != -1:
#             log.d("-> Found <a> at col: %d", a_idx)
#             last_a_col = a_idx
#             line_in = line_in.replace("<a>", "") # strip <a>
#
#         a_idx = line_in.find("<A>")
#         if a_idx != -1:
#             log.d("-> Found <A> at col: %d", a_idx)
#             last_a_col = a_idx
#             continue # don't keep the line into account
#
#         if last_a_col > cols:
#             # <a> tag is outside the current columns
#             log.w("Align tag <a> position exceed current cols: %d > %d", last_a_col, cols)
#             alignment = 0
#         else:
#             alignment = last_a_col
#
#         line_in = multireplace(line_in, {
#             "<b>": ansi.ATTR_BOLD,
#             "</b>": ansi.RESET,
#             "<u>": ansi.ATTR_UNDERLINE,
#             "</u>": ansi.RESET,
#         })
#
#         # Make an ansi aware string
#         line_in = ansistr(line_in)
#         # line_in = leading_ansi_tag + line_in
#
#         if len(line_in) + last_i <= cols:
#             # leading_ansi_tag = add_ansistr(line_in, indent=last_i)
#             add_ansistr(line_in, indent=last_i)
#         else:
#             log.d("-> breaking line since length %d > %d cols", len(line_in), cols)
#
#             leading = line_in[:alignment]
#             space_leading = ansistr(" " * alignment)
#             remaining_line_in = line_in[alignment:]
#             current_i = last_i
#             remaining_space = cols - alignment - current_i
#
#             while len(remaining_line_in) > remaining_space:
#                 log.w("--> still longer after break:  '%s'", remaining_line_in)
#                 head = remaining_line_in[:remaining_space - 1]
#
#                 # remaining_line_in = leading_ansi_tag + remaining_line_in[remaining_space - 1:].lstrip()
#                 # remaining_line_in = leading_ansi_tag + remaining_line_in[remaining_space - 1:]
#                 remaining_line_in = remaining_line_in[remaining_space - 1:]
#                 if not head.endswith(" ") and len(remaining_line_in) > 0:
#                     head += "-"
#
#                 log.d("--> cols: %d", cols)
#                 log.d("--> alignment: %d", alignment)
#                 log.d("--> leading (%d) = '%s'", len(leading), leading)
#                 log.d("--> head (%d) = '%s'", len(head), head)
#                 log.d("--> tail (%d) = '%s'", len(remaining_line_in), remaining_line_in)
#                 log.d("--> last_i = %d", last_i)
#                 log.d("--> len(leading) = %d", len(leading))
#
#                 leading_ansi_tag = add_ansistr(leading + head, indent=current_i)
#
#                 remaining_line_in = leading_ansi_tag + remaining_line_in.lstrip()
#
#                 leading = space_leading
#                 current_i = max(0, last_i - len(leading))
#                 remaining_space = cols - alignment - current_i
#
#             add_ansistr(leading + remaining_line_in, indent=current_i)
#
#         if reset_i:
#             last_i = 0
#
#     return parsed_hdm

if __name__ == "__main__":

    print(
        "======================\n",
          HelpMarkdown("""
<I4>
Indented of four spaces
<I8>
Indented of eight spaces
</I8>
Indented of four spaces
</I4>
""").to_term_str(),
        "\n======================")

    print(
        "======================\n",
        HelpMarkdown("""
<I4>
   <A>
-  Indented of four spaces that will break the line
</I4>
""").to_term_str(cols=40),
        "\n======================")