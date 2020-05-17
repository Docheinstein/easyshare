# SYNOPSIS

esd [*OPTION*]... [*SHARING* [*SHARING_NAME*] [*SHARING_OPTION*]...]

# DESCRIPTION
**easyshare** is a client-server command line application written in Python for transfer files between network hosts.  

**esd** is the server of the easyshare network application.

Files and directories can be shared in one of the following manners:
> `-` By providing the path of the file/directory to share in the command line as *SHARING*

> `-` By creating a configuration file and specifying it with the option **-c** *config*

The option 1. should be preferred for an easy one-shot sharing of a file or 
directory, since doesn't need the creation a configuration file, but has the 
limit that only a file or folder can be shared.

If given, *SHARING* must be a valid path to a local file or directory.
*SHARING_NAME* is an optional name to assign to the sharing, as it will 
be seen by clients. If not given, the name of the file/directory is used instead.
Currently the only supported *SHARING_OPTION* is the read-only flag, which can be 
enabled with **-r**, and denies any write operation on a directory sharing.

The server can be configured either with a configuration file (2.) or by 
giving esd the options you need. The command line arguments have precedence 
over the corresponding setting of the configuration file (i.e. if you specify 
an option in both the configuration file and as an argument, 
the argument will be taken into account).

# OPTIONS

**-a**, **--address**  
>> Server address.

>> Default is the primary interface.

**-c**, **--config** *config_path*
>> Load settings from a esd configuration file

**-d**, **--discover-port** *port*
>> Port used to listen to discovery messages.

>> Default is 12021.
>
**-e**, **--rexec**
>> Enable rexec (remote execution of arbitrary commands). 
>
>> Disabled by default.

**-h**, **--help**
>> Show this help

**-n**, **--name** *name*
>> Server name

**--no-color**                    
>> Don't print ANSI escape characters

**-P**, **--password** *password*
>> Server password, plain or hashed with **es-tools**

**-p**, **--port** *port*
>> Server port.

>> Default is 12021

**--ssl-cert** *cert_path*         
>> Path to an SSL certificate; must always be used together **--ssl-cert**

**--ssl-privkey** *privkey_path*
>> Path to an SSL private key; must always be used together **--ssl-privkey**

**-t**, **--trace** [*0_or_1*]
>> Enable tracing
>
>> If *0_or_1* is not given, enable tracing.

**-v**, **--verbose** [*level*]   
>> Set verbosity level (from 0 to 5).

>> If *level* is not given, set the verbosity to DEBUG (4).

**-V**, **--version**                 
>> Show the easyshare version

# CONFIGURATION FILE

The configuration file can be given to **esd** with the option **-c** *config*.

The configuration file is composed of two parts.
> `-` Global section

> `-` Sharings sections

Each line of a section has the form \<key\>=\<value\>.

The available \<key\> of the global section are:
> **address**

> **discover_port**

> **name**

> **no_color**

> **password**

> **port**

> **rexec**

> **ssl**

> **ssl_cert**

> **ssl_privkey**

> **trace**

> **verbose**

The available \<key\> of the sharings sections are:
> **path**

> **readonly**


# EXAMPLES

- Share a file
> *esd* */tmp/file*

- Share a directory, assigning it a name
> **esd**  */tmp/shared_directory* *shared*

- Share multiples directories, and other settings
> **esd** **-c** */home/user/.easyshare/esd.conf*

- Configuration file example (esd.conf):
```
# ===== SERVER SETTINGS =====

name=stefano-arch
password=aSecurePassword

port=12020
discover_port=12019

ssl=true
ssl_cert="/tmp/cert.pem"
ssl_privkey="/tmp/privkey.pem"
ssl_privkey="/tmp/privkey.pem"

rexec=false

verbose=4
trace=1

# ===== SHARINGS =====

[download]
    path="/home/stefano/Downloads"

[shared]
    path="/tmp/shared"
    readonly=true

# Automatic sharing name
[]
    path="/tmp/afile"
```