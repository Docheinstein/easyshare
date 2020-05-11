from easyshare.colors import Style, styled, Color
from easyshare.logging import get_logger_silent
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
        log.d("+ %s", styled(l, fg=Color.CYAN, attrs=Style.BOLD))


    for line_in in hmd.splitlines(keepends=False):
        log.d("'%s'", styled(line_in, attrs=Style.BOLD))
        if debug_step_by_step:
            input()

        # Alignment <a>/<A>
        # <a> will be stripped out lonely
        # <A> will be stripped out with the entire line

        # Remind the position of an eventual <a>/<A> tag on this line

        a_idx = line_in.find("<a>")
        if a_idx != -1:
            log.d("-> Found <a> at col: %d", a_idx)
            last_a_col = a_idx
            line_in = line_in[:a_idx] + line_in[a_idx + 3:] # strip <a>

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


HELP = """\
See the manual page (man es) for a complete description of the commands.
Type "help <command>" for the documentation of <command>.

Available commands are:     
                        <a>
General commands
    help                show this help
    exit, quit, q       exit from the shell
    trace, t            enable/disable packet tracing
    verbose, v          change verbosity level

Connection establishment commands
    scan, s             scan the network for easyshare servers
    connect             connect to a remote server
    disconnect          disconnect from a remote server
    open, o             open a remote sharing (eventually discovering it)
    close, c            close the remote sharing

Transfer commands
    get, g              get files and directories from the remote sharing
    put, p              put files and directories in the remote sharing

Local commands
    pwd                 show the name of current local working directory
    ls                  list local directory content
    l                   alias for ls -la
    tree                list local directory contents in a tree-like format
    cd                  change local working directory
    mkdir               create a local directory
    cp                  copy files and directories locally
    mv                  move files and directories locally
    rm                  remove files and directories locally
    exec, :             execute an arbitrary command locally

Remote commands
    rpwd                show the name of current remote working directory
    rls                 list remote directory content
    rl                  alias for rls -la
    rtree               list remote directory contents in a tree-like format
    rcd                 change remote working directory
    rmkdir              create a remote directory
    rcp                 copy files and directories remotely
    rmv                 move files and directories remotely
    rrm                 remove files and directories remotely
    rexec, ::           execute an arbitrary command remotely (disabled by default) since it will compromise server security

Server information commands
    info, i             show information about the remote server
    list                list the sharings of the remote server
    ping                test the connection with the remote server"""

LS = """\
    <A> # alignment
COMMAND
    ls - list local directory content
    
    List content of the local FILE or the current local directory if no FILE is specified.
    
SYNOPSIS
    ls [OPTION]... [FILE]

OPTIONS:
    -a, --all               show hidden files too
    -g, --group             group by file type
    -l,                     show more details
    -r, --reverse           reverse sort order
    -S, --size              show file size
    -s, --sort-size         sort by size"""


RLS = """\
    <A> # alignment
COMMAND
    rls - list remote directory content
    
    List content of the remote FILE or the current remote directory if no FILE is specified.
    
SYNOPSIS
    rls [OPTION]... [FILE]

OPTIONS:
    -a, --all               show hidden files too
    -g, --group             group by file type
    -l,                     show more details
    -r, --reverse           reverse sort order
    -S, --size              show file size
    -s, --sort-size         sort by size"""



if __name__ == "__main__":
    # i = 0
    # base = 40
    # while True:
    #     print(help_markdown_pager(HELP, cols=base + i * 10, debug_step_by_step=False))
    #     # print(help_markdown_pager(HELP, cols=base + i * 10, debug_step_by_step=False))
    #     i += 1
    #     input("Continue with cols = {}?".format(base + i * 10))

    print(help_markdown_pager(HELP))