# Automatically generated from make-helps.py on date 2020-05-12 12:13:27

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
    <A> # paragraph alignment (4)
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
    l
    ls
    pwd
    q
    quit
    rl
    rls
    rpwd
    rtree
    t
    trace
    tree
    v
    verbose
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

H = """\
    <A> # paragraph alignment (4)
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
    l
    ls
    pwd
    q
    quit
    rl
    rls
    rpwd
    rtree
    t
    trace
    tree
    v
    verbose
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

EXIT = """\
    <A> # paragraph alignment (4)
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
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

QUIT = """\
    <A> # paragraph alignment (4)
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
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

Q = """\
    <A> # paragraph alignment (4)
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
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

TRACE = """\
    <A> # paragraph alignment (4)
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

                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
<b>EXAMPLES</b>
<I4>
Here are some examples of data shown with the packet tracing on.

{
    TODO: example
}
</I4>"""

# ============================================================

T = """\
    <A> # paragraph alignment (4)
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

                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
<b>EXAMPLES</b>
<I4>
Here are some examples of data shown with the packet tracing on.

{
    TODO: example
}
</I4>"""

# ============================================================

VERBOSE = """\
    <A> # paragraph alignment (4)
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
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

V = """\
    <A> # paragraph alignment (4)
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
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

PWD = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
pwd - show the name of current local working directory
</I4>

<b>SYNOPSIS</b>
<I4>
pwd
</I4>

<b>DESCRIPTION</b>
<I4>
Show the name of current local working directory.

The local working directory can be changed with the command <b>cd</b>.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

LS = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
ls - list local directory content
</I4>

<b>SYNOPSIS</b>
<I4>
ls [OPTION]... [DIR]
</I4>

<b>DESCRIPTION</b>
<I4>
List content of the local DIR or the current local directory if no DIR is specified.
                              <A> # options alignment (34 = 4 + 30)

-a, --all                 show hidden files too
-g, --group               group by file type
-l                        show more details
-r, --reverse             reverse sort order
-S                        show files size
-s, --sort-size           sort by size
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

L = """\
alias for ls -la"""

# ============================================================

TREE = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
tree - list local directory contents in a tree-like format
</I4>

<b>SYNOPSIS</b>
<I4>
tree [OPTION]... [DIR]
</I4>

<b>DESCRIPTION</b>
<I4>
List recursively, in a tree-like format, the local DIR or the current local directory if no DIR is specified.
                              <A> # options alignment (34 = 4 + 30)

-a, --all                 show hidden files too
-d, --depth <u>depth</u>         maximum display depth of tree
-g, --group               group by file type
-l                        show more details
-r, --reverse             reverse sort order
-S                        show files size
-s, --sort-size           sort by size
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

RPWD = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
rpwd - show the name of current remote working directory
</I4>

<b>SYNOPSIS</b>
<I4>
rpwd

SHARING_LOCATION must be specified <u>if and only if </u> not already connected to a remote sharing, in that case the connection would be established as "open SHARING_LOCATION" would do before execute the command.

Type "<b>help open</b>" for more information about SHARING_LOCATION format.
</I4>

<b>DESCRIPTION</b>
<I4>
Show the name of current remote working directory.

The remote working directory can be changed with the command <b>rcd</b>.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

RLS = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
rls - list remote directory content
</I4>

<b>SYNOPSIS</b>
<I4>
rls [OPTION]... [DIR]
rls [OPTION]... [SHARING_LOCATION] [DIR]

SHARING_LOCATION must be specified <u>if and only if </u> not already connected to a remote sharing, in that case the connection would be established as "open SHARING_LOCATION" would do before execute the command.

Type "<b>help open</b>" for more information about SHARING_LOCATION format.
</I4>

<b>DESCRIPTION</b>
<I4>
List content of the remote DIR or the current remote directory if no DIR is specified.
                              <A> # options alignment (34 = 4 + 30)

-a, --all                 show hidden files too
-g, --group               group by file type
-l                        show more details
-r, --reverse             reverse sort order
-S                        show files size
-s, --sort-size           sort by size
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

RL = """\
alias for rls -la"""

# ============================================================

RTREE = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
rtree - list remote directory contents in a tree-like format
</I4>

<b>SYNOPSIS</b>
<I4>
tree [OPTION]... [DIR]

SHARING_LOCATION must be specified <u>if and only if </u> not already connected to a remote sharing, in that case the connection would be established as "open SHARING_LOCATION" would do before execute the command.

Type "<b>help open</b>" for more information about SHARING_LOCATION format.
</I4>

<b>DESCRIPTION</b>
<I4>
List recursively, in a tree-like format, the remote DIR or the current remote directory if no DIR is specified
                              <A> # options alignment (34 = 4 + 30)

-a, --all                 show hidden files too
-d, --depth <u>depth</u>         maximum display depth of tree
-g, --group               group by file type
-l                        show more details
-r, --reverse             reverse sort order
-S                        show files size
-s, --sort-size           sort by size
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

