# SYNOPSIS

es [*OPTION*]... [*COMMAND* [*COMMAND_OPTIONS*]]

# DESCRIPTION
**easyshare** is a client-server command line application written in Python for transfer files between network hosts.  

**es** is the client of the easyshare network application.

If no *COMMAND* is given, the interactive console is started. If *COMMAND* is a valid command, it is executed and the process quits unless the command is open.

Type "**help** *command*" for the full documentation of a command.

# OPTIONS

**-d**, **--discover-port** *port*
>> Port used for broadcast discovery messages.

>> Default is 12019.

**-h**, **--help**
>> Show this help

**--no-color**                    
>> Don't print ANSI escape characters

**-t**, **--trace** [*0_or_1*]
>> Enable tracing

>> If *0_or_1* is not given, enable tracing.

**-v**, **--verbose** [*level*]   
>> Set verbosity level (from 0 to 5).

>> If *level* is not given, set the verbosity to DEBUG (4).

**-V**, **--version**                 
>> Show the easyshare version

**-w**, **--discover-wait** *seconds*   
>> Time to wait for discovery responses.

>> Default is 2 seconds.

# COMMANDS
## General commands
> help              show this help  

> exit, quit, q     exit from the interactive shell

> trace, t          enable/disable packet tracing

> verbose, v        change verbosity level  

## Connection establishment commands
> scan, s           scan the network for easyshare servers

> connect           connect to a remote server

> disconnect        disconnect from a remote server

> open, o           open a remote sharing (eventually discovering it)

> close, c          close the remote sharing

## Transfer commands
> get, g            get files and directories from the remote sharing

> put, p            put files and directories in the remote sharing

## Local commands
> pwd               show the name of current local working directory

> ls                list local directory content

> l                 alias for ls -la

> tree              list local directory contents in a tree-like format

> cd                change local working directory

> mkdir             create a local directory

> cp                copy files and directories locally

> mv                move files and directories locally

> rm                remove files and directories locally

> exec, :           execute an arbitrary command locally
>
> shell, shell      start a local shell


## Remote commands
> rpwd              show the name of current remote working directory

> rls               list remote directory content

> rl                alias for rls -la

> rtree             list remote directory contents in a tree-like format

> rcd               change remote working directory

> rmkdir            create a remote directory

> rcp               copy files and directories remotely

> rmv               move files and directories remotely

> rrm               remove files and directories remotely

> rexec, ::         execute an arbitrary command remotely (disabled by default)

> rshell, rsh       start a remote shell (disabled by default)


# EXAMPLES

These are only examples, see the *help* section of each command for known exactly
what you can do.

- Start the interactive shell (from which you can use any command)
> **es**
 
- Scan the network for easyshare sharings

> **es** *scan*
```
alice-arch (192.168.1.105:12020)
  DIRECTORIES
  - shared
  - tmp
```
- Open a sharing by name (implicit discovery and server connection) and start the interactive shell
>**es** *open* *shared*
```
alice-arch.shared:/ - /tmp>
```

- Get the content of a sharing by name
> **es** *get* *shared*
```
GET shared/f1    [===================] 100%  745KB/745KB
GET outcome: OK
Files        1  (745KB)
Time         1s
Avg. speed   1MB/s
```

- Open a sharing by name and put some files into it
> **es**
```
/tmp> open shared
alice-arch.shared:/ - /tmp> rls
f1      f2
alice-arch.shared:/ - /tmp> put /tmp/afile
PUT afile    [===================] 100%  745KB/745KB
PUT outcome: OK
Files        1  (745KB)
Time         1s
Avg. speed   1MB/s
alice-arch.shared:/ - /tmp> rls
f1      f2      afile
```

- Connect to a server by specific address and port, then list the available sharings
> **es** *connect* *192.168.1.105:12020*
```
alice-arch:/ - /tmp> list
DIRECTORIES
- shared
- tmp
FILES
- zshrc
```

- See content of the remote sharing, then move some files
> **es** 
```
/tmp> open shared
alice-arch.shared:/ - /tmp> rtree
/tmp> tree
|-- dir
|   |-- f3
|   +-- f4
|-- f1
+-- f2
alice-arch.shared:/ - /tmp> rmv f1 f2 dir
alice-arch.shared:/ - /tmp> rtree
+-- dir
    |-- f1
    |-- f2
    |-- f3
    +-- f4
alice-arch.shared:/ - /tmp> rcd dir
alice-arch.shared:/dir - /tmp> rls
f1      f2      f3      f4
```

- Arbitrary local command execution
> **es** 
```
>/tmp> cd d
/tmp/d> ls
f0  
/tmp> :touch f1
f0      f1
```

- Arbitrary remote command execution (DISABLED BY DEFAULT)
> **es**
``` 
/tmp> connect alice-arch
alice-arch:/ - /tmp> ::whoami
alice
```