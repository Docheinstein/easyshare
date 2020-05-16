from math import ceil
from typing import List

from easyshare.consts import ansi
from easyshare.logging import get_logger
from easyshare.protocol import FileInfo
from easyshare.protocol import FTYPE_DIR, FTYPE_FILE
from easyshare.protocol import ServerInfoFull
from easyshare.protocol import SharingInfo
from easyshare.common import DIR_COLOR, FILE_COLOR
from easyshare.styling import styled, fg
from easyshare.tree import TreeNodeDict, TreeRenderPostOrder
from easyshare.ssl import get_cached_or_fetch_ssl_certificate_for_endpoint
from easyshare.utils.env import terminal_size, is_unicode_supported
from easyshare.utils.measures import size_str
from easyshare.utils.os import is_hidden
from easyshare.utils.ssl import SSLCertificate


log = get_logger(__name__)

class StyledString:
    def __init__(self, string: str, styled_string: str = None):
        self.string = string
        self.styled_string = styled_string or string

    def __str__(self):
        return self.string


def print_tabulated(strings: List[StyledString], max_columns: int = None):
    if not strings:
        return

    log.d("len(strings) %d", len(strings))

    term_cols, _ = terminal_size()
    log.d("term_cols %d", term_cols)

    longest_string_length = len(str(max(strings, key=lambda ss: len(str(ss)))))
    log.d("longest_match_length %d", longest_string_length)

    min_col_width = longest_string_length + 2
    log.d("min_col_width %d", min_col_width)

    max_allowed_cols = max_columns if max_columns else 50
    log.d("max_allowed_cols %d", max_allowed_cols)

    max_fillable_cols = term_cols // min_col_width
    log.d("max_fillable_cols %d", max_fillable_cols)

    display_cols = max(1, min(max_allowed_cols, max_fillable_cols))
    log.d("display_cols %d", display_cols)

    display_rows = ceil(len(strings) / display_cols)
    log.d("display_rows %d", display_rows)

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
        print(print_row)


def print_files_info_list(infos: List[FileInfo],
                          show_file_type: bool = False,
                          show_size: bool = False,
                          show_hidden: bool = False,
                          compact: bool = True):
    if not infos:
        return

    sstrings: List[StyledString] = []

    for info in infos:
        log.d("f_info: %s", info)

        fname = info.get("name")

        if not show_hidden and is_hidden(fname):
            log.d("Not showing hidden files: %s", fname)
            continue

        size = info.get("size")

        if info.get("ftype") == FTYPE_DIR:
            ftype_short = "D"
            fname_styled = fg(fname, DIR_COLOR)
        else:
            ftype_short = "F"
            fname_styled = fg(fname, FILE_COLOR)

        file_str = ""

        if show_file_type:
            s = ftype_short + "  "
            # if not compact:
            #     s = s.ljust(3)
            file_str += s

        if show_size:
            s = size_str(size, prefixes=(" ", "M", "K", "G")).rjust(4) + "  "
            file_str += s

        file_str_styled = file_str

        file_str += fname
        file_str_styled += fname_styled

        sstrings.append(StyledString(file_str, file_str_styled))

    if not compact:
        for ss in sstrings:
            print(ss.styled_string)
    else:
        print_tabulated(sstrings)


def print_files_info_tree(root: TreeNodeDict,
                          max_depth: int = None,
                          show_size: bool = False,
                          show_hidden: bool = False):
    for prefix, node, depth in TreeRenderPostOrder(root, depth=max_depth):
        name = node.get("name")

        if not show_hidden and is_hidden(name):
            log.d("Not showing hidden file: %s", name)
            continue

        ftype = node.get("ftype")
        size = node.get("size")

        print("{}{}{}".format(
            prefix,
            "[{}]  ".format(size_str(size, prefixes=(" ", "M", "K", "G")).rjust(4)) if show_size else "",
            fg(name, color=DIR_COLOR if ftype == FTYPE_DIR else FILE_COLOR),
        ))


def ssl_certificate_to_pretty_str(ssl_cert: SSLCertificate) -> str:
    if not ssl_cert:
        return ""

    subject = ssl_cert.get("subject")
    issuer = ssl_cert.get("issuer")

    return \
        "Common name:        {}\n".format(subject.get("common_name")) + \
        "Organization:       {}\n".format(subject.get("organization")) + \
        "Organization Unit:  {}\n".format(subject.get("organization_unit")) + \
        "Email:              {}\n".format(subject.get("email")) + \
        "Locality:           {}\n".format(subject.get("locality")) + \
        "State:              {}\n".format(subject.get("state")) + \
        "Country:            {}\n\n".format(subject.get("country")) + \
        "Valid From:         {}\n".format(ssl_cert.get("valid_from")) + \
        "Valid To:           {}\n\n".format(ssl_cert.get("valid_to")) + \
        "Issuer:             {}\n".format(", ".join([issuer.get("common_name"), issuer.get("organization")])) + \
        "Signing:            {}".format("self signed" if ssl_cert.get("self_signed") else "signed")


def server_info_to_pretty_str(info: ServerInfoFull, sharing_details: bool = False, separators: bool = False) -> str:
        SEP = "================================"

        SEP_FIRST = (SEP + "\n\n") if separators else ""
        SEP_MID = ("\n" + SEP + "\n\n") if separators else "\n"
        SEP_LAST = ("\n" + SEP) if separators else ""

        # Server info
        s = SEP_FIRST + \
            styled("SERVER INFO", attrs=ansi.ATTR_BOLD) + "\n\n" + \
            "Name:           {}\n".format(info.get("name")) + \
            "Address:        {}\n".format(info.get("ip")) + \
            "Port:           {}\n".format(info.get("port")) + \
            "Discoverable:   {}\n".format(info.get("discoverable", False)) + \
            ("Discover Port: {}\n".format(info.get("discover_port")) if info.get("discoverable", False) else "") + \
            "Auth:           {}\n".format(info.get("auth")) + \
            "SSL:            {}\n".format(info.get("ssl")) + \
            SEP_MID

        # SSL?
        if info.get("ssl"):
            ssl_cert = get_cached_or_fetch_ssl_certificate_for_endpoint(
                (info.get("ip"), info.get("port"))
            )

            s += \
                styled("SSL CERTIFICATE", attrs=ansi.ATTR_BOLD) + "\n\n" + \
                ssl_certificate_to_pretty_str(ssl_cert) + "\n" + \
                SEP_MID

        # Sharings
        s += \
            styled("SHARINGS", attrs=ansi.ATTR_BOLD) + "\n\n" + \
            sharings_to_pretty_str(info.get("sharings"),
                                   details=sharing_details,
                                   indent=2) + "\n" + \
            SEP_LAST

        return s

def server_info_to_short_str(server_info: ServerInfoFull):
    return "{} ({}:{})".format(
        server_info.get("name"),
        server_info.get("ip"),
        server_info.get("port"))

def sharings_to_pretty_str(sharings: List[SharingInfo],
                           details: bool = False,
                           indent: int = 0) -> str:
    s = ""
    bullet = "\u2022" if is_unicode_supported() else "-"

    d_sharings = [sh for sh in sharings if sh.get("ftype") == FTYPE_DIR]
    f_sharings = [sh for sh in sharings if sh.get("ftype") == FTYPE_FILE]

    def sharing_string(sharing: SharingInfo):
        ss = " " * indent + bullet + " " + sharing.get("name")

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

