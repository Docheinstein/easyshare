class ServerErrors:
    ERROR =                     200
    INVALID_COMMAND_SYNTAX =    201
    NOT_IMPLEMENTED =           202
    NOT_CONNECTED =             203
    COMMAND_EXECUTION_FAILED =  204
    SHARING_NOT_FOUND =         205
    INVALID_PATH =              206
    INVALID_TRANSACTION =       207
    NOT_ALLOWED =               208
    AUTHENTICATION_FAILED =     209
    INTERNAL_SERVER_ERROR =     210
    NOT_WRITABLE =              211


class TransferOutcomes:
    SUCCESS = 0
    ERROR = 301
    CHECK_FAILED = 302
