from easyshare.colors import Style, styled
from easyshare.logging import get_logger_exuberant
from easyshare.utils.env import terminal_size

log = get_logger_exuberant()

def parse_help_markdown_string(hmd: str) -> str: # HelpMarkDown
    cols, rows = terminal_size()
    cols = 35
    last_a_col = 0

    parsed_hdm = ""

    for line_in in hmd.splitlines(keepends=True):
        log.d("%s", styled(line_in, attrs=Style.BOLD))

        # Remind the position of an eventual <a> tag on this line
        a_idx = line_in.find("<a>")
        if a_idx != -1:
            log.d("-> Found <a> at col: %d", a_idx)
            last_a_col = a_idx

        # Strip any <a> anyway
        line_in = line_in.replace("<a>", "")

        if len(line_in) <= cols:
            parsed_hdm += line_in
        else:
            log.d("-> Breaking line of length %d since > %d cols", len(line_in), cols)
            # Alignment <a>

            # Line is longer than the available columns
            # Break it, and insert an indent so that the breaked line
            # will be aligned with the last <a> tag

            # remaining_line_in = line_in

            # while len(remaining_line_in) > cols:
            breakpoint_idx = line_in.rfind(" ", 0, cols)

            if breakpoint_idx == -1:
                log.w("-> No spaces found in the string, doing nothing")
                parsed_hdm += line_in
            else:

                head = line_in[0:breakpoint_idx]
                tail = line_in[breakpoint_idx + 1:]
                parsed_hdm += head + "\n"
                parsed_hdm += " " * last_a_col

                log.d("-> cols: %d", cols)
                log.d("-> last_a_col: %d", last_a_col)
                log.d("-> breakpoint_idx: %d", breakpoint_idx)
                log.d("-> head (%d) = '%s'", len(head), head)
                log.d("-> tail (%d) = '%s'", len(tail), tail)

                remaining_line_in = tail

                while len(remaining_line_in) > cols - last_a_col:
                    log.w("Still longer after break")
                    log.d("Finding last space of '%s'", remaining_line_in[:cols - last_a_col])

                    breakpoint_idx = remaining_line_in.rfind(" ", 0, cols - last_a_col)

                    if breakpoint_idx == -1:
                        log.w("--> No more spaces found in the string, brutal breaking")
                        breakpoint_idx = cols - last_a_col

                    head = remaining_line_in[0:breakpoint_idx].lstrip()
                    tail = remaining_line_in[breakpoint_idx:].lstrip()

                    log.d("--> cols: %d", cols)
                    log.d("--> last_a_col: %d", last_a_col)
                    log.d("--> breakpoint_idx: %d", breakpoint_idx)
                    log.d("--> head (%d) = '%s'", len(head), head)
                    log.d("--> tail (%d) = '%s'", len(tail), tail)


                    parsed_hdm += head + "\n"
                    parsed_hdm += " " * last_a_col

                    remaining_line_in = tail

                parsed_hdm += remaining_line_in


            continue

    return parsed_hdm


HELP = """\
See the manual page (man es) for a complete description of the commands.
Type "help <command>" for the documentation of <command>.

Available commands are:     <a>

General commands
    help                    show this help
    exit, quit, q           exit from the shell
    trace, t                enable/disable packet tracing
    verbose, v              change verbosity level

Connection establishment commands
    scan, s                 scan the network for easyshare servers
    connect                 connect to a remote server
    disconnect              disconnect from a remote server
    open, o                 open a remote sharing (eventually discovering it)
    close, c                close the remote sharing

Transfer commands
    get, g                  get files and directories from the remote sharing
    put, p                  put files and directories in the remote sharing

Local commands
    pwd                     show the name of current local working directory
    ls                      list local directory contents
    l                       alias for ls -la
    tree                    list local directory contents in a tree-like format
    cd                      change local working directory
    mkdir                   create a local directory
    cp                      copy files and directories locally
    mv                      move files and directories locally
    rm                      remove files and directories locally
    exec, :                 execute an arbitrary command locally

Remote commands
    rpwd                    show the name of current remote working directory
    rls                     list remote directory contents
    rl                      alias for rls -la
    rtree                   list remote directory contents in a tree-like format
    rcd                     change remote working directory
    rmkdir                  create a remote directory
    rcp                     copy files and directories remotely
    rmv                     move files and directories remotely
    rrm                     remove files and directories remotely
    rexec, ::               execute an arbitrary command remotely (disabled by default) since it will compromise server security

Server information commands
    info, i                 show information about the remote server
    list                    list the sharings of the remote server
    ping                    test the connection with the remote server"""

LS = """\
COMMAND
    ls - list local directory contents
    
    List content of the FILE or the current directory if no FILE is specified.
    
SYNOPSIS
    ls [OPTION]... [FILE]

OPTIONS:
    -a, --all               show hidden files too
    -g, --group             group by file type
    -l,                     show more details
    -r, --reverse           reverse sort order
    -S, --size              show file size
    -s, --sort-size         sort by size"""



if __name__ == "__main__":
    print(parse_help_markdown_string(HELP))
