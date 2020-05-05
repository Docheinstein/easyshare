class Commands:
    HELP = "help"
    EXIT = "exit"

    TRACE = "trace"
    TRACE_SHORT = "t"

    VERBOSE = "verbose"
    VERBOSE_SHORT = "v"

    LOCAL_CURRENT_DIRECTORY = "pwd"
    LOCAL_LIST_DIRECTORY = "ls"
    LOCAL_LIST_DIRECTORY_ENHANCED = "l"
    LOCAL_TREE_DIRECTORY = "tree"
    LOCAL_CHANGE_DIRECTORY = "cd"
    LOCAL_CREATE_DIRECTORY = "mkdir"
    LOCAL_COPY = "cp"
    LOCAL_MOVE = "mv"
    LOCAL_REMOVE = "rm"
    LOCAL_EXEC = "exec"
    LOCAL_EXEC_SHORT = ":"

    REMOTE_CURRENT_DIRECTORY = "rpwd"
    REMOTE_LIST_DIRECTORY = "rls"
    REMOTE_TREE_DIRECTORY = "rtree"
    REMOTE_CHANGE_DIRECTORY = "rcd"
    REMOTE_CREATE_DIRECTORY = "rmkdir"
    REMOTE_COPY = "rcp"
    REMOTE_MOVE = "rmv"
    REMOTE_REMOVE = "rrm"
    REMOTE_EXEC = "rexec"
    REMOTE_EXEC_SHORT = "::"

    SCAN = "scan"
    LIST = "list"

    CONNECT = "connect"
    DISCONNECT = "disconnect"

    OPEN = "open"
    CLOSE = "close"

    GET = "get"
    PUT = "put"

    INFO = "info"
    PING = "ping"


def is_special_command(c: str):
    return c.startswith(":")

def matches_special_command(s: str, comm: str):
    return s.startswith(comm) and (len(s) == len(comm) or s[len(comm)] != ":")
