# Automatically generated from make-helps.py on date 2020-05-13 08:42:53

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
<b>help</b> [<u>COMMAND</u>]
</I4>

<b>DESCRIPTION</b>
<I4>
Show the help of COMMAND if specified, or show the list of commands if no COMMAND is given.

Available commands are:
    cd
    cp
    exit
    h
    help
    l
    ls
    mkdir
    pwd
    q
    quit
    rcd
    rcp
    rl
    rls
    rmkdir
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
<b>help</b> [<u>COMMAND</u>]
</I4>

<b>DESCRIPTION</b>
<I4>
Show the help of COMMAND if specified, or show the list of commands if no COMMAND is given.

Available commands are:
    cd
    cp
    exit
    h
    help
    l
    ls
    mkdir
    pwd
    q
    quit
    rcd
    rcp
    rl
    rls
    rmkdir
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
<b>exit</b>
<b>quit</b>
<b>q</b>
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
<b>exit</b>
<b>quit</b>
<b>q</b>
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
<b>exit</b>
<b>quit</b>
<b>q</b>
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
<b>trace</b>   [<u>0</u> | <u>1</u>]
<b>t</b>       [<u>0</u> | <u>1</u>]
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
<b>trace</b>   [<u>0</u> | <u>1</u>]
<b>t</b>       [<u>0</u> | <u>1</u>]
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
<b>verbose</b>   [<u>0</u> | <u>1</u> | <u>2</u> | <u>3</u> | <u>4</u>]
<b>v</b>   [<u>0</u> | <u>1</u> | <u>2</u> | <u>3</u> | <u>4</u>]
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
<b>verbose</b>   [<u>0</u> | <u>1</u> | <u>2</u> | <u>3</u> | <u>4</u>]
<b>v</b>   [<u>0</u> | <u>1</u> | <u>2</u> | <u>3</u> | <u>4</u>]
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
<b>pwd</b>
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
<b>ls</b> [<u>OPTION</u>]... [<u>DIR</u>]
</I4>

<b>DESCRIPTION</b>
<I4>
List content of the local <u>DIR</u> or the current local directory if no <u>DIR</u> is specified.
                              <A> # options alignment (34 = 4 + 30)

<b>-a, --all</b>                 show hidden files too
<b>-g, --group</b>               group by file type
<b>-l</b>                        show more details
<b>-r, --reverse</b>             reverse sort order
<b>-s, --sort-size</b>           sort by size
<b>-S</b>                        show files size
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
<b>tree</b> [<u>OPTION</u>]... [<u>DIR</u>]
</I4>

<b>DESCRIPTION</b>
<I4>
List recursively, in a tree-like format, the local <u>DIR</u> or the current local directory if no <u>DIR</u> is specified.
                              <A> # options alignment (34 = 4 + 30)

<b>-a, --all</b>                 show hidden files too
<b>-d, --depth</b> <u>depth</u>         maximum display depth of tree
<b>-g, --group</b>               group by file type
<b>-l</b>                        show more details
<b>-r, --reverse</b>             reverse sort order
<b>-s, --sort-size</b>           sort by size
<b>-S</b>                        show files size
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

CD = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
cd - change local working directory
</I4>

<b>SYNOPSIS</b>
<I4>
<b>cd</b> [<u>DIR</u>]
</I4>

<b>DESCRIPTION</b>
<I4>
Change the current local working directory to <u>DIR</u> or to the user's home directory if <u>DIR</u> is not specified.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

MKDIR = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
mkdir - create a local directory
</I4>

<b>SYNOPSIS</b>
<I4>
<b>mkdir</b> <u>DIR</u>
</I4>

<b>DESCRIPTION</b>
<I4>
Create the local directory <u>DIR</u>.

Parent directories of <u>DIR</u> are automatically created when needed.

If <u>DIR</u> already exists, it does nothing.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

CP = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
cp - copy files and directories locally
</I4>

<b>SYNOPSIS</b>
<I4>

<b>cp</b> <u>SOURCE</u> <u>DEST</u>
<b>cp</b> <u>SOURCE</u>... <u>DIR</u>
</I4>

<b>DESCRIPTION</b>
<I4>
Copy <u>SOURCE</u> file or directory to <u>DEST</u>, or copy multiple </u>SOURCE</u>s to the <u>DIR</u>.

If used with two arguments as "<b>cp</b> <u>SOURCE</u> <u>DEST</u>" the following rules are applied:
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will copied as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be copied into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>

If used with at least arguments as "<b>cp</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must be an existing directory and <u>SOURCE</u>s will be copied into it.
                              <A> # options alignment (34 = 4 + 30)
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
<b>rpwd</b>

SHARING_LOCATION must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format.
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
<b>rls</b> [<u>OPTION</u>]... [<u>DIR</u>]
<b>rls</b> [<u>OPTION</u>]... [<u>SHARING_LOCATION</u>] [<u>DIR</u>]

SHARING_LOCATION must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format.
</I4>

<b>DESCRIPTION</b>
<I4>
List content of the remote <u>DIR</u> or the current remote directory if no <u>DIR</u> is specified.
                              <A> # options alignment (34 = 4 + 30)

<b>-a, --all</b>                 show hidden files too
<b>-g, --group</b>               group by file type
<b>-l</b>                        show more details
<b>-r, --reverse</b>             reverse sort order
<b>-s, --sort-size</b>           sort by size
<b>-S</b>                        show files size
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
<b>rtree</b> - list remote directory contents in a tree-like format
</I4>

<b>SYNOPSIS</b>
<I4>
<b>tree</b> [<u>OPTION</u>]... [<u>DIR</u>]

SHARING_LOCATION must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format.
</I4>

<b>DESCRIPTION</b>
<I4>
List recursively, in a tree-like format, the remote <u>DIR</u> or the current remote directory if no <u>DIR</u> is specified
                              <A> # options alignment (34 = 4 + 30)

<b>-a, --all</b>                 show hidden files too
<b>-d, --depth</b> <u>depth</u>         maximum display depth of tree
<b>-g, --group</b>               group by file type
<b>-l</b>                        show more details
<b>-r, --reverse</b>             reverse sort order
<b>-s, --sort-size</b>           sort by size
<b>-S</b>                        show files size
</I4>
    <A> # paragraph alignment (4)
"""

# ============================================================

RCD = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
rcd - change remote working directory
</I4>

<b>SYNOPSIS</b>
<I4>
<b>rcd</b> [<u>DIR</u>]
<b>rcd</b> [<u>SHARING_LOCATION</u>] [<u>DIR</u>]

SHARING_LOCATION must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format.
</I4>

<b>DESCRIPTION</b>
<I4>
Change the current remote working directory to <u>DIR</u> or to the root of the current sharing if no <u>DIR</u> is specified.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>EXAMPLES</b>
<I4>
Usage example:

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> <u>rcd</u> dir
<b>/tmp - remote.shared:/dir></b> <u>rcd</u> subdir
<b>/tmp - remote.shared:/dir/subdir></b> <u>rcd</u>
<b>/tmp - remote.shared:/></b>
</I4>"""

# ============================================================

RMKDIR = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
rmkdir - create a remote directory
</I4>

<b>SYNOPSIS</b>
<I4>
<b>rmkdir</b> <u>DIR</u>

SHARING_LOCATION must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format.
</I4>

<b>DESCRIPTION</b>
<I4>
Create the remote directory <u>DIR</u>.

Parent directories of <u>DIR</u> are automatically created when needed.

If <u>DIR</u> already exists, it does nothing.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>EXAMPLES</b>
<I4>
Usage example:

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> <u>rmkdir</u> newdir
<b>/tmp - remote.shared:/></b> rcd newdir
<b>/tmp - remote.shared:/newdir></b>
</I4>"""

# ============================================================

RCP = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
rcp - copy files and directories remotely
</I4>

<b>SYNOPSIS</b>
<I4>
rcp SOURCE... DEST

SHARING_LOCATION must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format.
</I4>

<b>DESCRIPTION</b>
<I4>
Copy <u>SOURCE</u> file or directory to <u>DEST</u>, or copy multiple </u>SOURCE</u>s to the <u>DIR</u>.

If used with two arguments as "<b>cp</b> <u>SOURCE</u> <u>DEST</u>" the following rules are applied:
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will copied as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be copied into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>

If used with three arguments "<b>cp</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must be an existing directory.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>EXAMPLES</b>
<I4>
Usage example:

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> <u>rmkdir</u> newdir
<b>/tmp - remote.shared:/></b> rcd newdir
<b>/tmp - remote.shared:/newdir></b>
</I4>"""

# ============================================================

