from math import ceil
from typing import List, Optional, Callable

from easyshare.common import DIR_COLOR, FILE_COLOR
from easyshare.logging import get_logger
from easyshare.protocol.types import ServerInfoFull, FTYPE_DIR, FileInfo, SharingInfo, FTYPE_FILE
from easyshare.ssl import get_cached_or_fetch_ssl_certificate_for_endpoint
from easyshare.styling import fg, bold, underline
from easyshare.tree import TreeNodeDict, TreeRenderPreOrder
from easyshare.utils.env import terminal_size, is_unicode_supported
from easyshare.utils.json import j
from easyshare.utils.measures import size_str_justify
from easyshare.utils.os import perm_str
from easyshare.utils.path import is_hidden
from easyshare.utils.ssl import SSLCertificate
from easyshare.utils.str import tf, yn

log = get_logger(__name__)

class StyledString:
    """
    Composition of a string with its display representation (e.g. with ansi codes)
    """
    def __init__(self, string: str, styled_string: str = None):
        self.string = string
        self.styled_string = styled_string or string

    def __str__(self):
        return self.string


def _print_strict(*args, **kwargs):
    print(*args, **kwargs, end="")


def print_tabulated(strings: List[StyledString], max_columns: int = None,
                    print_func: Callable = _print_strict):
    """
    Prints the 'strings' in columns (max max_columns);
    The space of the columns is the space needed for display the longest string.
    """
    if not strings:
        return

    log.d("print_tabulated - len(strings) %d", len(strings))

    term_cols, _ = terminal_size()
    log.d("print_tabulated - term_cols %d", term_cols)

    longest_string_length = len(str(max(strings, key=lambda ss: len(str(ss)))))
    log.d("print_tabulated - longest_match_length %d", longest_string_length)

    min_col_width = longest_string_length + 2
    log.d("print_tabulated - min_col_width %d", min_col_width)

    max_allowed_cols = max_columns if max_columns else 50
    log.d("print_tabulated - max_allowed_cols %d", max_allowed_cols)

    max_fillable_cols = term_cols // min_col_width
    log.d("print_tabulated - max_fillable_cols %d", max_fillable_cols)

    display_cols = max(1, min(max_allowed_cols, max_fillable_cols))
    log.d("print_tabulated - display_cols %d", display_cols)

    display_rows = ceil(len(strings) / display_cols)
    log.d("print_tabulated - display_rows %d", display_rows)

    for r in range(0, display_rows):
        print_row = ""

        for c in range(0, display_cols):
            idx = r + c * display_rows
            if idx < len(strings):
                # Add the styled string;
                # We have to justify keeping the non-printable
                # characters in count
                ss = strings[idx]

                justification = min_col_width + len(ss.styled_string) - len(ss.string)
                print_row += ss.styled_string.ljust(justification)
        print_func(print_row + "\n")


def file_info_pretty_str(info: FileInfo):
    s = f"""\
File:           {info.get("name")}    
Type:           {info.get("ftype")}
Size:           {info.get("size")}
Last modified:  {info.get("mtime")}"""
    return s

def file_info_str(info: FileInfo,
                  show_file_type: bool = False,  # -l
                  show_size: bool = False,  # -S
                  show_hidden: bool = False,  # -a
                  show_perm: bool = False, # -l
                  show_owner: bool = False, # -l
                  owner_user_justify: int = 0,  # -l
                  owner_group_justify: int = 0,  # -l
                  **kwargs) -> Optional[StyledString]:
    fname = info.get("name")

    if not show_hidden and is_hidden(fname):
        log.d("Not showing hidden files: %s", fname)
        return None

    if info.get("ftype") == FTYPE_DIR:
        ftype_short = "d"
        fname_styled = fg(fname, DIR_COLOR)
    else:
        ftype_short = "f"
        fname_styled = fg(fname, FILE_COLOR)

    file_str = ""

    if show_file_type:
        file_str += ftype_short + " "

    if show_perm:
        file_str += perm_str(info.get("perm")) + "  "

    if show_owner:
        file_str += info.get("user").ljust(owner_user_justify) + "  "
        file_str += info.get("group").ljust(owner_group_justify) + "  "

    if show_size:
        file_str += size_str_justify(info.get("size")) + "  "

    file_str_styled = file_str + fname_styled
    file_str = file_str + fname

    return StyledString(file_str, file_str_styled)



def print_files_info_list(infos: List[FileInfo],
                          show_hidden: bool = False,    # -a
                          show_file_type: bool = False, # -l
                          show_size: bool = False,      # -S
                          show_perm: bool = False,      # -l
                          show_owner: bool = False,     # -l
                          compact: bool = True,         # not -l
                          file_info_renderer: Callable[..., StyledString] = file_info_str):
    """ Prints a list of 'FileInfo' (ls -l like). """
    if not infos:
        return

    # Detect the longest user/group length for render properly
    longest_user = 0
    longest_group = 0
    if show_owner:
        for i in infos:
            if len(i.get("user")) > longest_user:
                longest_user = len(i.get("user"))
            if len(i.get("group")) > longest_group:
                longest_group = len(i.get("group"))

    sstrings: List[StyledString] = [ss for ss in (
        file_info_renderer(
            info,
            show_hidden=show_hidden,
            show_file_type=show_file_type,
            show_size=show_size,
            show_perm=show_perm,
            show_owner=show_owner,
            owner_user_justify=longest_user,
            owner_group_justify=longest_group,
            index=idx
        ) for idx, info in enumerate(infos)) if ss is not None]

    if compact:
        print_tabulated(sstrings)
    else:
        for ss in sstrings:
            print(ss.styled_string)


def print_files_info_tree(root: TreeNodeDict,
                          max_depth: int = None,
                          show_size: bool = False,
                          show_hidden: bool = False):
    """ Traverse the 'TreeNodeDict' and prints the 'FileInfo' as a tree (tree like). """

    for prefix, node, depth in TreeRenderPreOrder(root, depth=max_depth):
        log.d("TreeRenderPostOrder over %s", j(node))

        name = node.get("name")

        if not show_hidden and is_hidden(name):
            log.d("Not showing hidden file: %s", name)
            continue

        ftype = node.get("ftype")
        size = node.get("size")

        print("{}{}{}".format(
            prefix,
            "[{}]  ".format(size_str_justify(size)) if show_size else "",
            fg(name, color=DIR_COLOR if ftype == FTYPE_DIR else FILE_COLOR),
        ))

def server_pretty_str(info: ServerInfoFull,
                      show_server_info: bool = True,
                      show_ssl_certificate: bool = True,
                      show_sharings: bool = True,
                      show_sharings_details: bool = True,
                      highlight_sharings: List[SharingInfo] = None) -> str:
    """ Returns a string representation of a 'ServerInfoFull' """

    s = """\
================================"""

    # Server info?
    if show_server_info:
        s += f"""\

{bold("SERVER INFO")}

{server_info_pretty_str(info)}

================================"""

    # SSL?
    if show_ssl_certificate:
        if info.get("ssl"):
            ssl_cert = get_cached_or_fetch_ssl_certificate_for_endpoint(
                (info.get("ip"), info.get("port"))
            )

            s += f"""

{bold("SSL CERTIFICATE")}

{ssl_certificate_pretty_str(ssl_cert)}

================================"""

    # Sharings?
    if show_sharings:
        s += f"""

{bold("SHARINGS")}

{sharings_pretty_str(info.get("sharings"), 
                     details=show_sharings_details, 
                     indent=2,
                     highlight_sharings=highlight_sharings)}

================================"""

    return s



def server_info_pretty_str(info: ServerInfoFull) -> str:
    """ Returns a string representation of a 'ServerInfoFull', apart from SSL and sharings """

    discover_port_str = ""
    if info.get("discoverable", False):
        discover_port_str = "Discover Port:    {}\n".format(info.get("discover_port"))

    return f"""\
Name:             {info.get("name")}
Address:          {info.get("ip")}
Port:             {info.get("port")}
Discoverable:     {yn(info.get("discoverable", False))}
{discover_port_str}\
Authentication:   {yn(info.get("auth"))}
SSL:              {tf(info.get("ssl"), "enabled", "disabled")}
Remote execution: {tf(info.get("rexec"), "enabled", "disabled")}
Version:          {info.get("version")}"""


def server_info_short_str(server_info: ServerInfoFull):
    """ Returns a compact string representation of a 'ServerInfoFull' """

    return f"{server_info.get('name')} ({server_info.get('ip')}:{server_info.get('port')})"


def ssl_certificate_pretty_str(ssl_cert: SSLCertificate) -> str:
    """ Returns a string representation of a 'SSLCertificate' """
    if not ssl_cert:
        return ""

    subject = ssl_cert.get("subject")
    issuer = ssl_cert.get("issuer")

    return f"""\
Common name:        {subject.get("common_name")}
Organization:       {subject.get("organization")}
Organization:       {subject.get("organization")}
Organization Unit:  {subject.get("organization_unit")}
Email:              {subject.get("email")}
Locality:           {subject.get("locality")}
State:              {subject.get("state")}
Country:            {subject.get("country")}
Valid From:         {ssl_cert.get("valid_from")}
Valid To:           {ssl_cert.get("valid_to")}
Issuer:             {", ".join([issuer.get("common_name"), issuer.get("organization")])}
Signing:            {"self signed" if ssl_cert.get("self_signed") else "signed"}"""


def sharings_pretty_str(sharings: List[SharingInfo],
                        details: bool = False,
                        indent: int = 0,
                        highlight_sharings: List[SharingInfo] = None) -> str:
    """ Returns a string representation of a list of 'Sharing' """

    if sharings is None:
        return "NONE"

    s = ""
    bullet = "\u2022" if is_unicode_supported() else "-"

    d_sharings = [sh for sh in sharings if sh.get("ftype") == FTYPE_DIR]
    f_sharings = [sh for sh in sharings if sh.get("ftype") == FTYPE_FILE]

    def sharing_string(sharing: SharingInfo):
        ss = " " * indent + bullet + " "

        if sharing in highlight_sharings:
            ss += underline(sharing.get("name"))
        else:
            ss += sharing.get("name")

        if details:
            details_list = []
            if sharing.get("auth"):
                details_list.append("auth required")
            if sharing.get("read_only"):
                details_list.append("read only")
            if details_list:
                ss += "    ({})".format(", ".join(details_list))
        ss += "\n"
        return ss

    if d_sharings:
        s += " " * indent + "DIRECTORIES\n"
        for dsh in d_sharings:
            s += sharing_string(dsh)

    if f_sharings:
        s += " " * indent + "FILES\n"
        for fsh in f_sharings:
            s += sharing_string(fsh)

    return s.rstrip("\n")