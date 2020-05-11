# Automatically generated 2020-05-11 23:50:24

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

# ============================================================

LS = """\
    <A> # alignment
<b>COMMAND</b>
    ls - list remote directory content

    List content of the remote FILE or the current remote directory if no FILE is specified.

<b>SYNOPSIS</b>
    ls  [OPTION]... [FILE]

<b>OPTIONS</b>
    -s, --sort-size         sort by size
    -r, --reverse           reverse sort order
    -g, --group             group by file type
    -a, --all               show hidden files too
    -S                      show files size
    -l                      show more details"""

# ============================================================

