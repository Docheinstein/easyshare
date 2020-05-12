# Automatically generated from make-helps.py on date 2020-05-12 10:25:26

USAGE = """\
See the manual page (man es) for a complete description of the commands.
Type "help <command>" for the documentation of <command>.

Available commands are:     
                        <a>
<b>General commands</b>
    help                show this help
    exit, quit, q       exit from the interactive shell
    trace, t            enable/disable packet tracing
    verbose, v          change verbosity level

<b>Connection establishment commands</b>
    scan, s             scan the network for easyshare servers
    connect             connect to a remote server
    disconnect          disconnect from a remote server
    open, o             open a remote sharing (eventually discovering it)
    close, c            close the remote sharing

<b>Transfer commands</b>
    get, g              get files and directories from the remote sharing
    put, p              put files and directories in the remote sharing

<b>Local commands</b>
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

<b>Remote commands</b>
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

<b>Server information commands</b>
    info, i             show information about the remote server
    list                list the sharings of the remote server
    ping                test the connection with the remote server"""

# ============================================================

HELP = """\
    <A> # alignment
<b>COMMAND</b>
<I4>
help - show the help of a command
</I4>

<b>SYNOPSIS</b>
<I4>
help [COMMAND]
</I4>

<b>DESCRIPTION</b>
<I4>
Show the help of COMMAND if specified, or show the list of commands if no COMMAND is given.

Available commands are:
    exit
    h
    help
    ls
    q
    quit
    rls
    t
    trace
    v
    verbose
</I4>"""

# ============================================================

H = """\
    <A> # alignment
<b>COMMAND</b>
<I4>
help - show the help of a command
</I4>

<b>SYNOPSIS</b>
<I4>
help [COMMAND]
</I4>

<b>DESCRIPTION</b>
<I4>
Show the help of COMMAND if specified, or show the list of commands if no COMMAND is given.

Available commands are:
    exit
    h
    help
    ls
    q
    quit
    rls
    t
    trace
    v
    verbose
</I4>"""

# ============================================================

EXIT = """\
    <A> # alignment
<b>COMMAND</b>
<I4>
exit - exit from the interactive shell
</I4>

<b>SYNOPSIS</b>
<I4>
exit
quit
q
</I4>

<b>DESCRIPTION</b>
<I4>
Exit from the interactive shell.

Open connections are automatically closed.
</I4>"""

# ============================================================

QUIT = """\
    <A> # alignment
<b>COMMAND</b>
<I4>
exit - exit from the interactive shell
</I4>

<b>SYNOPSIS</b>
<I4>
exit
quit
q
</I4>

<b>DESCRIPTION</b>
<I4>
Exit from the interactive shell.

Open connections are automatically closed.
</I4>"""

# ============================================================

Q = """\
    <A> # alignment
<b>COMMAND</b>
<I4>
exit - exit from the interactive shell
</I4>

<b>SYNOPSIS</b>
<I4>
exit
quit
q
</I4>

<b>DESCRIPTION</b>
<I4>
Exit from the interactive shell.

Open connections are automatically closed.
</I4>"""

# ============================================================

TRACE = """\
    <A> # alignment
<b>COMMAND</b>
<I4>
trace - enable/disable packet tracing
</I4>

<b>SYNOPSIS</b>
<I4>
trace   [0 | 1]
t       [0 | 1]
</I4>

<b>DESCRIPTION</b>
<I4>
Show (1) or hide (0) the packets sent and received to and from the server for any operation.

If no argument is given, toggle the packet tracing mode.

</I4>

<b>EXAMPLES</b>
<I4>
Here are some examples of data shown with the packet tracing on.

{
    TODO: example
}
</I4>"""

# ============================================================

T = """\
    <A> # alignment
<b>COMMAND</b>
<I4>
trace - enable/disable packet tracing
</I4>

<b>SYNOPSIS</b>
<I4>
trace   [0 | 1]
t       [0 | 1]
</I4>

<b>DESCRIPTION</b>
<I4>
Show (1) or hide (0) the packets sent and received to and from the server for any operation.

If no argument is given, toggle the packet tracing mode.

</I4>

<b>EXAMPLES</b>
<I4>
Here are some examples of data shown with the packet tracing on.

{
    TODO: example
}
</I4>"""

# ============================================================

VERBOSE = """\
    <A> # alignment
<b>COMMAND</b>
<I4>
verbose - change verbosity level           
</I4>

<b>SYNOPSIS</b>
<I4>
verbose   [0 | 1 | 2 | 3 | 4]
v         [0 | 1 | 2 | 3 | 4]
</I4>

<b>DESCRIPTION</b>
<I4>
None
</I4>"""

# ============================================================

V = """\
    <A> # alignment
<b>COMMAND</b>
<I4>
verbose - change verbosity level           
</I4>

<b>SYNOPSIS</b>
<I4>
verbose   [0 | 1 | 2 | 3 | 4]
v         [0 | 1 | 2 | 3 | 4]
</I4>

<b>DESCRIPTION</b>
<I4>
None
</I4>"""

# ============================================================

LS = """\
    <A> # alignment
<b>COMMAND</b>
<I4>
ls - list local directory content
</I4>

<b>SYNOPSIS</b>
<I4>
ls [OPTION]... [FILE]
</I4>

<b>DESCRIPTION</b>
<I4>
List content of the local FILE or the current local directory if no FILE is specified.
</I4>

<I4>
-a, --all               show hidden files too
-g, --group             group by file type
-l                      show more details
-r, --reverse           reverse sort order
-S                      show files size
-s, --sort-size         sort by size
</I4>"""

# ============================================================

RLS = """\
    <A> # alignment
<b>COMMAND</b>
<I4>
rls - list remote directory content
</I4>

<b>SYNOPSIS</b>
<I4>
rls [OPTION]... [FILE]
rls [OPTION]... [SHARING_LOCATION] [FILE]
</I4>

<b>DESCRIPTION</b>
<I4>
List content of the remote FILE or the current remote directory if no FILE is specified.

SHARING_LOCATION must be specified <u>if and only if </u> not already connected to a remote sharing, in that case the connection would be established as "open SHARING_LOCATION" would do before execute the command.

See "help open" for more information about SHARING_LOCATION format.
</I4>

<I4>
-a, --all               show hidden files too
-g, --group             group by file type
-l                      show more details
-r, --reverse           reverse sort order
-S                      show files size
-s, --sort-size         sort by size
</I4>"""

# ============================================================

