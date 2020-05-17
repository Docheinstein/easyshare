# SYNOPSIS

es-tools [*OPTION*]...

# DESCRIPTION
**easyshare** is a client-server command line application written in Python for transfer files between network hosts.  

**es-tools** is a collection of tools for administrators of easyshare servers.

If neither **-c** nor **-p** is given, an interactive script is started and you will be asked what to do.

# OPTIONS
**-c**, **--generate-config**
>> Generate default esd.conf file as **esd** excepts

**-h**, **--help**
>> Show this help

**-p**, **--hash-password** *password*   
>> Generate an hash of *password* as **esd** excepts
    
**-V**, **--version**
>> Show the easyshare version

# EXAMPLES

- Generate a default config file
> **es-tools** **-c** > /tmp/esd.conf

- Create a secure hash of a password
> **es-tools** **-p** *aSecurePassword*

- Start the interactive script
> **es-tools**
```
What do you want to do?
1. Generate an hash of a password (hash)
2. Generate the default server configuration file
3. Generate a self signed SSL certificate
```