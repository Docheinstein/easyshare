# Automatically generated from make-helps.py on date 2020-05-13 10:16:20

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
    exec
    exit
    h
    help
    l
    ls
    mkdir
    mv
    pwd
    q
    quit
    rcd
    rcp
    rexec
    rl
    rls
    rm
    rmkdir
    rmv
    rpwd
    rrm
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
    exec
    exit
    h
    help
    l
    ls
    mkdir
    mv
    pwd
    q
    quit
    rcd
    rcp
    rexec
    rl
    rls
    rm
    rmkdir
    rmv
    rpwd
    rrm
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

<b>SEE ALSO</b>
<I4>
Type "<b>help rpwd</b>" for the remote analogous.
</I4>"""

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

<b>SEE ALSO</b>
<I4>
Type "<b>help rls</b>" for the remote analogous.
</I4>"""

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

<b>SEE ALSO</b>
<I4>
Type "<b>help rtree</b>" for the remote analogous.
</I4>"""

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

<b>SEE ALSO</b>
<I4>
Type "<b>help rcd</b>" for the remote analogous.
</I4>"""

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

<b>SEE ALSO</b>
<I4>
Type "<b>help rmkdir</b>" for the remote analogous.
</I4>"""

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
Copy local <u>SOURCE</u> file or directory to <u>DEST</u>, or copy multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>cp</b> <u>SOURCE</u> <u>DEST</u>" the following rules are applied:
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will copied as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be copied into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>

If used with at least arguments as "<b>cp</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must be an existing directory and <u>SOURCE</u>s will be copied into it.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>SEE ALSO</b>
<I4>
Type "<b>help rcp</b>" for the remote analogous.
</I4>"""

# ============================================================

MV = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
mv - move files and directories locally
</I4>

<b>SYNOPSIS</b>
<I4>
<b>mv</b> <u>SOURCE</u> <u>DEST</u>
<b>mv</b> <u>SOURCE</u>... <u>DIR</u>
</I4>

<b>DESCRIPTION</b>
<I4>
Move local <u>SOURCE</u> file or directory to <u>DEST</u>, or move multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>mv</b> <u>SOURCE</u> <u>DEST</u>" the following rules are applied:
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will moved as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be moved into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>

If used with at least arguments as "<b>mv</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must be an existing directory and <u>SOURCE</u>s will be moved into it.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>SEE ALSO</b>
<I4>
Type "<b>help rmv</b>" for the remote analogous.
</I4>"""

# ============================================================

RM = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
rm - remove files and directories locally
</I4>

<b>SYNOPSIS</b>
<I4>
<b>rm</b> [FILE]...
</I4>

<b>DESCRIPTION</b>
<I4>
Remove local <u>FILE</u>s.

If a <u>FILE</u> is a directory, it will be removed recursively.

If a <u>FILE</u> does not exists, it will be ignored.

This commands never prompts: essentially acts like unix's rm -rf.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>SEE ALSO</b>
<I4>
Type "<b>help rrm</b>" for the remote analogous.
</I4>"""

# ============================================================

EXEC = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
exec - execute an arbitrary command locally
</I4>

<b>SYNOPSIS</b>
<I4>
<b>exec</b> <u>COMMAND</u>
<b>:</b> <u>COMMAND</u>
<b>:</b><u>COMMAND</u>
</I4>

<b>DESCRIPTION</b>
<I4>
Executes an arbitrary <u>COMMAND</u> locally.

The <u>COMMAND</u> is executed via the shell and therefore allows all the shell features (e.g. variables, glob expansions, redirection).

This might be useful for execute commands without exiting the easyshare's shell.

The command can be run either with "<b>exec</b> <u>COMMAND</u>",  "<b>:</b> <u>COMMAND</u>" or "<b>:</b><u>COMMAND</u>".
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>EXAMPLES</b>
<I4>
Usage example:

<b>/tmp></b> ls
f1      f2
<b>/tmp></b> <b>exec</b> touch f3
f1      f2      f3
<b>/tmp></b> <b>:<b> echo "hello" > f3
<b>/tmp></b> <b>:<b>cat f3
hello
</I4>

<b>SEE ALSO</b>
<I4>
Type "<b>help rexec</b>" for the remote analogous.
</I4>"""

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

<u>SHARING_LOCATION</u> must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format.
</I4>

<b>DESCRIPTION</b>
<I4>
Show the name of current remote working directory.

The remote working directory can be changed with the command <b>rcd</b>.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>SEE ALSO</b>
<I4>
Type "<b>help pwd</b>" for the local analogous.
</I4>"""

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

<u>SHARING_LOCATION</u> must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

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

<b>SEE ALSO</b>
<I4>
Type "<b>help ls</b>" for the local analogous.
</I4>"""

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

<u>SHARING_LOCATION</u> must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

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

<b>SEE ALSO</b>
<I4>
Type "<b>help tree</b>" for the local analogous.
</I4>"""

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

<u>SHARING_LOCATION</u> must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

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
<b>/tmp - remote.shared:/></b> <b>rcd</b> dir
<b>/tmp - remote.shared:/dir></b> <b>rcd</b> subdir
<b>/tmp - remote.shared:/dir/subdir></b> <b>rcd</b>
<b>/tmp - remote.shared:/></b>
</I4>

<b>SEE ALSO</b>
<I4>
Type "<b>help cd</b>" for the local analogous.
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
<b>rmkdir</b> [<u>SHARING_LOCATION</u>] <u>DIR</u>

<u>SHARING_LOCATION</u> must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

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
<b>/tmp - remote.shared:/></b> <b>rmkdir</b> newdir
<b>/tmp - remote.shared:/></b> rcd newdir
<b>/tmp - remote.shared:/newdir></b>
</I4>

<b>SEE ALSO</b>
<I4>
Type "<b>help mkdir</b>" for the local analogous.
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
<b>rcp</b> <u>SOURCE</u> <u>DEST</u>
<b>rcp</b> <u>SOURCE</u>... <u>DIR</u>
<b>rcp</b> [<u>SHARING_LOCATION</u>] <u>SOURCE</u> <u>DEST</u>
<b>rcp</b> [<u>SHARING_LOCATION</u>] <u>SOURCE</u>... <u>DIR</u>

<u>SHARING_LOCATION</u> must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format.
</I4>

<b>DESCRIPTION</b>
<I4>
Copy remote <u>SOURCE</u> file or directory to <u>DEST</u>, or copy multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>rcp</b> <u>SOURCE</u> <u>DEST</u>" the following rules are applied:
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will copied as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be copied into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>

If used with at least arguments as "<b>rcp</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must be an existing directory and <u>SOURCE</u>s will be copied into it.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>EXAMPLES</b>
<I4>
Usage example:

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> rls
f1
<b>/tmp - remote.shared:/></b> <b>rcp</b> f1 f2
<b>/tmp - remote.shared:/></b> rls
f1      f2

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> tree
├── dir
├── f1
└── f2
<b>/tmp - remote.shared:/></b> <b>rcp</b> f1 f2 dir
<b>/tmp - remote.shared:/></b> rtree dir
├── dir
│   ├── f1
│   └── f2
├── f1
└── f2
</I4>

<b>SEE ALSO</b>
<I4>
Type "<b>help cp</b>" for the local analogous.
</I4>"""

# ============================================================

RMV = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
rmv - move files and directories remotely
</I4>

<b>SYNOPSIS</b>
<I4>
<b>rmv</b> <u>SOURCE</u> <u>DEST</u>
<b>rmv</b> <u>SOURCE</u>... <u>DIR</u>
<b>rmv</b> [<u>SHARING_LOCATION</u>] <u>SOURCE</u> <u>DEST</u>
<b>rmv</b> [<u>SHARING_LOCATION</u>] <u>SOURCE</u>... <u>DIR</u>

<u>SHARING_LOCATION</u> must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format.
</I4>

<b>DESCRIPTION</b>
<I4>
Move remote <u>SOURCE</u> file or directory to <u>DEST</u>, or move multiple </u>SOURCE</u>s to the directory <u>DIR</u>.

If used with two arguments as "<b>rmv</b> <u>SOURCE</u> <u>DEST</u>" the following rules are applied:
- If <u>DEST</u> doesn't exists, <u>SOURCE</u> will moved as <u>DEST</u>.
- If <u>DEST</u> exists and it is a directory, <u>SOURCE</u> will be moved into <u>DEST</u>
- If <u>DEST</u> exists and it is a file, <u>SOURCE</u> must be a file and it will overwrite <u>DEST</u>

If used with at least arguments as "<b>rmv</b> <u>SOURCE</u>... <u>DIR</u>" then <u>DIR</u> must be an existing directory and <u>SOURCE</u>s will be moved into it.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>EXAMPLES</b>
<I4>
Usage example:

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> rls
f1
<b>/tmp - remote.shared:/></b> <b>rmv</b> f1 f2
<b>/tmp - remote.shared:/></b> rls
f2

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> rtree
├── dir
├── f1
└── f2
<b>/tmp - remote.shared:/></b> <b>rmv</b> f1 f2 dir
<b>/tmp - remote.shared:/></b> rtree dir
└── dir
    ├── f1
    └── f2
</I4>

<b>SEE ALSO</b>
<I4>
Type "<b>help mv</b>" for the local analogous.
</I4>"""

# ============================================================

RRM = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
rmv - remove files and directories remotely
</I4>

<b>SYNOPSIS</b>
<I4>
<b>rm</b> [FILE]...
<b>rm</b> [<u>SHARING_LOCATION</u>] [FILE]...

<u>SHARING_LOCATION</u> must be specified if and only if not already connected to a remote sharing. In that case the connection will be established before execute the command, as "<b>open</b> <u>SHARING_LOCATION</u>" would do.

Type "<b>help open</b>" for more information about <u>SHARING_LOCATION</u> format.
</I4>

<b>DESCRIPTION</b>
<I4>
Remove remote <u>FILE</u>s.

If a <u>FILE</u> is a directory, it will be removed recursively.

If a <u>FILE</u> does not exists, it will be ignored.

This commands never prompts: essentially acts like unix's rm -rf.
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>EXAMPLES</b>
<I4>
Usage example:

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> rls
f1      f2
<b>/tmp - remote.shared:/></b> <b>rrm</b> f2
<b>/tmp - remote.shared:/></b> rls
f1

<b>/tmp></b> open shared
<b>/tmp - remote.shared:/></b> rtree
├── dir
│   ├── f1
│   └── f2
└── f1
<b>/tmp - remote.shared:/></b> <b>rrm</b> dir
<b>/tmp - remote.shared:/></b> tree
└── f1
</I4>

<b>SEE ALSO</b>
<I4>
Type "<b>help rm</b>" for the local analogous.
</I4>"""

# ============================================================

REXEC = """\
    <A> # paragraph alignment (4)
<b>COMMAND</b>
<I4>
rexec - execute an arbitrary command remotely
</I4>

<b>SYNOPSIS</b>
<I4>
<b>rexec</b> <u>COMMAND</u>
<b>::</b> <u>COMMAND</u>
<b>::</b><u>COMMAND</u>

<b>rexec</b> [<u>SERVER_LOCATION</u>] <u>COMMAND</u>
<b>::</b> [<u>SERVER_LOCATION</u>] <u>COMMAND</u>
<b>::</b>[<u>SERVER_LOCATION</u>] <u>COMMAND</u>

<u>SERVER_LOCATION</u> must be specified if and only if not already connected to a remote server. In that case the connection will be established before execute the command, as "<b>connect</b> <u>SERVER_LOCATION</u>" would do.

Type "<b>help connect</b>" for more information about <u>SERVER_LOCATION</u> format.
</I4>

<b>DESCRIPTION</b>
<I4>
THE SERVER REJECTS THIS COMMAND BY DEFAULT, UNLESS IT HAS BEEN MANUALLY 
ENABLED WITH THE SETTING "<u>rexec=true</u>"

Executes an arbitrary <u>COMMAND</u> remotely.

The <u>COMMAND</u> is executed via the shell and therefore allows all the shell features (e.g. variables, glob expansions, redirection).

This might be useful for execute commands remotely, giving the client a kind of easy and plug-and-play shell.

The command can be run either with "<b>rexec</b> <u>COMMAND</u>",  "<b>:</b> <u>COMMAND</u>" or "<b>:</b><u>COMMAND</u>".
                              <A> # options alignment (34 = 4 + 30)
</I4>
    <A> # paragraph alignment (4)

<b>EXAMPLES</b>
<I4>
Usage example:

<b>/tmp></b> rls
f1      f2
<b>/tmp></b> <b>rexec</b> touch f3
f1      f2      f3
<b>/tmp></b> <b>::<b> echo "hello" > f3
<b>/tmp></b> <b>::<b>cat f3
hello
</I4>

<b>SEE ALSO</b>
<I4>
Type "<b>help exec</b>" for the local analogous.
</I4>"""

# ============================================================

