# import fcntl
# import os
# import random
# import select
# import sys
# import threading
# import time
# from getpass import getpass
# from stat import S_ISDIR, S_ISREG
# from typing import Optional, Callable, List, Dict, Union, Tuple, TypeVar
#
# import Pyro4
#
# from easyshare.client.args import PositionalArgs, StopParseArgs, VariadicArgs, ArgsParser
# from easyshare.client.commands import Commands, is_special_command
#
# from easyshare.client.connection import Connection
# from easyshare.client.discover import Discoverer
# from easyshare.client.errors import ClientErrors, print_error, errcode_string
# from easyshare.consts.net import ADDR_BROADCAST
# from easyshare.logging import get_logger
# from easyshare.protocol.fileinfo import FileInfo, FileInfoTreeNode
# from easyshare.protocol.filetype import FTYPE_DIR, FTYPE_FILE, FileType
# from easyshare.protocol.pyro import IRexecTransaction
# from easyshare.protocol.response import Response, is_error_response, is_success_response, is_data_response
# from easyshare.protocol.serverinfo import ServerInfo
# from easyshare.protocol.sharinginfo import SharingInfo
# from easyshare.shared.args import Args
# from easyshare.shared.common import PROGRESS_COLOR, DONE_COLOR, is_server_name
# from easyshare.shared.endpoint import Endpoint
# from easyshare.shared.progress import FileProgressor
# from easyshare.ssl import get_ssl_context
# from easyshare.socket.tcp import SocketTcpOut
# from easyshare.utils.app import eprint
# from easyshare.utils.colors import red
# from easyshare.utils.json import json_to_pretty_str
# from easyshare.utils.net import is_valid_ip, is_valid_port
# from easyshare.utils.ssl import parse_ssl_certificate, SSLCertificate, create_client_ssl_context
# from easyshare.utils.types import to_int, bool_to_str, is_int, is_str, bytes_to_str
# from easyshare.utils.os import ls, rm, tree, mv, cp, pathify, run_attached
# from easyshare.args import Args as Args, KwArgSpec, INT_PARAM, PRESENCE_PARAM
#
#
# log = get_logger(__name__)
#
#
# # ==================================================================
#
#
# class LsArgs(PositionalArgs):
#     SORT_BY_SIZE = ["-s", "--sort-size"]
#     REVERSE = ["-r", "--reverse"]
#     GROUP = ["-g", "--group"]
#
#     SHOW_ALL = ["-a", "--all"]
#     SHOW_DETAILS = ["-l"]
#     SHOW_SIZE = ["-S"]
#
#     def __init__(self, mandatory: int):
#         super().__init__(mandatory, 1)
#
#     def _kwargs_specs(self) -> Optional[List[KwArgSpec]]:
#         return [
#             KwArgSpec(LsArgs.SORT_BY_SIZE, PRESENCE_PARAM),
#             KwArgSpec(LsArgs.REVERSE, PRESENCE_PARAM),
#             KwArgSpec(LsArgs.GROUP, PRESENCE_PARAM),
#             KwArgSpec(LsArgs.SHOW_ALL, PRESENCE_PARAM),
#             KwArgSpec(LsArgs.SHOW_DETAILS, PRESENCE_PARAM),
#             KwArgSpec(LsArgs.SHOW_SIZE, PRESENCE_PARAM),
#         ]
#
#
# class TreeArgs(PositionalArgs):
#     SORT_BY_SIZE = ["-s", "--sort-size"]
#     REVERSE = ["-r", "--reverse"]
#     GROUP = ["-g", "--group"]
#
#     SHOW_ALL = ["-a", "--all"]
#     SHOW_DETAILS = ["-l"]
#     SHOW_SIZE = ["-S"]
#
#     MAX_DEPTH = ["-d", "--depth"]
#
#     def __init__(self, mandatory: int):
#         super().__init__(mandatory, 1)
#
#     def _kwargs_specs(self) -> Optional[List[KwArgSpec]]:
#         return [
#             KwArgSpec(TreeArgs.SORT_BY_SIZE, PRESENCE_PARAM),
#             KwArgSpec(TreeArgs.REVERSE, PRESENCE_PARAM),
#             KwArgSpec(TreeArgs.GROUP, PRESENCE_PARAM),
#             KwArgSpec(TreeArgs.SHOW_ALL, PRESENCE_PARAM),
#             KwArgSpec(TreeArgs.SHOW_DETAILS, PRESENCE_PARAM),
#             KwArgSpec(TreeArgs.SHOW_SIZE, PRESENCE_PARAM),
#             KwArgSpec(TreeArgs.MAX_DEPTH, INT_PARAM),
#         ]
#
#
# class PingArgs(PositionalArgs):
#     COUNT = ["-c", "--count"]
#
#     def __init__(self, mandatory: int):
#         super().__init__(mandatory, 0)
#
#     def _kwargs_specs(self) -> Optional[List[KwArgSpec]]:
#         return [
#             KwArgSpec(PingArgs.COUNT, INT_PARAM),
#         ]
#
# class GetArguments:
#     YES_TO_ALL = ["-Y", "--yes"]
#     NO_TO_ALL = ["-N", "--no"]
#
#
# class PutArguments:
#     YES_TO_ALL = ["-Y", "--yes"]
#     NO_TO_ALL = ["-N", "--no"]
#
#
# # ==================================================================
#
#
#
# # ==================================================================
#
#
# def response_error_string(resp: Response) -> str:
#     return errcode_string(resp.get("error"))
#
# #
# # API = TypeVar('API', bound=Callable[..., None])
# #
# #
# # def provide_sharing_connection(api: API) -> API:
# #     def provide_sharing_connection_api_wrapper(client: 'Client', args: Args, _: Connection = None):
# #         # Wraps api providing the connection parameters.
# #         # The provided connection is the client current connection,
# #         # if it is established, or a temporary one that will be closed
# #         # just after the api call.
# #         # The connection is established treating the first arg of
# #         # args as a 'ServerSpecifier'
# #         log.d("Checking if connection exists before invoking %s", api.__name__)
# #
# #         conn = client._get_current_or_create_connection_from_sharing_spec_args(args)
# #
# #         if not conn or not conn.is_connected():
# #             raise BadOutcome(ClientErrors.NOT_CONNECTED)
# #
# #         log.d("Connection established, invoking %s", api.__name__)
# #         api(client, args, conn)
# #
# #         if conn != client.connection:
# #             log.d("Closing temporary connection")
# #             conn.close()
# #
# #     return provide_sharing_connection_api_wrapper
# #
# #
# # def provide_server_connection(api: API) -> API:
# #     def provide_server_connection_api_wrapper(client: 'Client', args: Args, _: Connection = None):
# #         # Wraps api providing the connection parameters.
# #         # The provided connection is the client current connection,
# #         # if it is established, or a temporary one that will be closed
# #         # just after the api call.
# #         # The connection is established treating the first arg of
# #         # args as a 'ServerSpecifier'
# #         log.d("Checking if connection exists before invoking %s", api.__name__)
# #
# #         conn = client._get_current_or_create_connection_from_server_spec_args(args)
# #
# #         if not conn:
# #             raise BadOutcome(ClientErrors.NOT_CONNECTED)
# #
# #         log.d("Connection established, invoking %s", api.__name__)
# #         api(client, args, conn)
# #
# #         if conn != client.connection:
# #             log.d("Closing temporary connection")
# #             conn.close()
# #
# #     return provide_server_connection_api_wrapper
#
#
# # ==================================================================
#
# class BadOutcome(Exception):
#     pass
#
# # ==================================================================
#
#
# class ClientSharing:
#
#     def __init__(self, uri: str, discover_port: int):
#         self._discover_port = discover_port
#
#         self._certs_cache: Dict[Endpoint, dict] = {}
#
#         def connectionless(parser: ArgsParser, func: Callable[[Args], None]) -> \
#                 Tuple[ArgsParser, ArgsParser, Callable[[Args], None]]:
#             return parser, parser, func
#
#         # connectionful, connectionless, executor
#
#         self._command_dispatcher: Dict[
#             str, Tuple[ArgsParser, ArgsParser, Callable[[Args, Optional[Connection]], None]]] = {
#
#             Commands.LOCAL_CHANGE_DIRECTORY: connectionless(PositionalArgs(0, 1), Client.cd),
#             Commands.LOCAL_LIST_DIRECTORY: connectionless(LsArgs(0), Client.ls),
#             Commands.LOCAL_LIST_DIRECTORY_ENHANCED: connectionless(PositionalArgs(0, 1), Client.l),
#             Commands.LOCAL_TREE_DIRECTORY: connectionless(TreeArgs(0), Client.tree),
#             Commands.LOCAL_CREATE_DIRECTORY: connectionless(PositionalArgs(1), Client.mkdir),
#             Commands.LOCAL_CURRENT_DIRECTORY: connectionless(PositionalArgs(0), Client.pwd),
#             Commands.LOCAL_REMOVE: connectionless(VariadicArgs(1), Client.rm),
#             Commands.LOCAL_MOVE: connectionless(VariadicArgs(2), Client.mv),
#             Commands.LOCAL_COPY: connectionless(VariadicArgs(2), Client.cp),
#             Commands.LOCAL_EXEC: connectionless(StopParseArgs(), Client.exec),
#             Commands.LOCAL_EXEC_SHORT: connectionless(StopParseArgs(), Client.exec),
#
#             Commands.REMOTE_CHANGE_DIRECTORY: (PositionalArgs(0, 1), PositionalArgs(1, 1), self.rcd),
#             Commands.REMOTE_LIST_DIRECTORY: (LsArgs(0), LsArgs(1), self.rls),
#             Commands.REMOTE_TREE_DIRECTORY: (TreeArgs(0), TreeArgs(1), self.rtree),
#             Commands.REMOTE_CREATE_DIRECTORY: (PositionalArgs(1), PositionalArgs(2), self.rmkdir),
#             Commands.REMOTE_CURRENT_DIRECTORY: (PositionalArgs(0), PositionalArgs(1), self.rpwd),
#             Commands.REMOTE_REMOVE: (VariadicArgs(1), VariadicArgs(2), self.rrm),
#             Commands.REMOTE_MOVE: (VariadicArgs(2), VariadicArgs(3), self.rmv),
#             Commands.REMOTE_COPY: (VariadicArgs(2), VariadicArgs(3), self.rcp),
#             Commands.REMOTE_EXEC: (StopParseArgs(), StopParseArgs(1), self.rexec),
#             Commands.REMOTE_EXEC_SHORT: (StopParseArgs(), StopParseArgs(1), self.rexec),
#
#             Commands.SCAN: (ScanArgs(), ScanArgs(), self.scan),
#             Commands.OPEN: (PositionalArgs(1), PositionalArgs(1), self.open),
#             Commands.CLOSE: (PositionalArgs(0), PositionalArgs(1), self.close),
#
#             Commands.GET: self.get,
#             Commands.PUT: self.put,
#
#             Commands.INFO: (PositionalArgs(0, 1), PositionalArgs(1, 0), self.info),
#             Commands.PING: (PingArgs(0), PingArgs(1), self.ping),
#         }
#
#     def has_command(self, command: str) -> bool:
#         return command in self._command_dispatcher or \
#                is_special_command(command)
#
#     def execute_command(self, command: str, command_args: List[str]) -> Union[int, str]:
#         if not self.has_command(command):
#             return ClientErrors.COMMAND_NOT_RECOGNIZED
#
#         command_args_normalized = command_args.copy()
#
#         # Handle special commands (':')
#         command_parts = command.rsplit(":", maxsplit=1)
#         if len(command_parts) > 1:
#             command = command_parts[0] + ":"
#             log.d("Found special command: '%s'", command)
#             if command_parts[1]:
#                 command_args_normalized.insert(0, command_parts[1])
#
#         log.i("Executing %s(%s)", command, command_args_normalized)
#
#         # Check which parser to use
#         # The local commands and the connected remote commands use
#         # the same parsers, while the unconnected remote commands
#         # need one more leading parameter (the remote sharing specifier)
#         connectionful_parser, connectionless_parser, executor = self._command_dispatcher[command]
#
#         if self.is_connected():
#             log.d("Parser type: 'already connected'")
#             parser = connectionful_parser
#         else:
#             log.d("Parser type: 'not connected'")
#             parser = connectionless_parser
#
#         # Parse args using the parsed bound to the command
#         args = parser.parse(command_args_normalized)
#
#         if not args:
#             log.e("Command's arguments parse failed")
#             return ClientErrors.INVALID_COMMAND_SYNTAX
#
#         log.i("Parsed command arguments\n%s", args)
#
#         try:
#             executor(args, None)
#             return 0
#         except BadOutcome as ex:
#             log.exception("Internal trouble, throwing it up")
#             return ex.args[0]
#             # return ex.args[0]
#         except Exception as ex:
#             log.exception("Exception caught while executing command\n%s", ex)
#             return ClientErrors.COMMAND_EXECUTION_FAILED
#
#     def is_connected(self) -> bool:
#         return self.connection and self.connection.is_connected()
#
#     # === LOCAL COMMANDS ===
#
#     @staticmethod
#     def cd(args: Args):
#         directory = pathify(args.get_varg(default="~"))
#
#         log.i(">> CD %s", directory)
#
#         if not os.path.isdir(os.path.join(os.getcwd(), directory)):
#             raise BadOutcome(ClientErrors.INVALID_PATH)
#
#         os.chdir(directory)
#
#     @staticmethod
#     def ls(args: Args):
#
#         def ls_provider(path, **kwargs):
#             path = pathify(path or os.getcwd())
#             kws = {k: v for k, v in kwargs.items() if k in ["sort_by", "name", "reverse"]}
#             return ls(path, **kws)
#
#         Client._ls(args, data_provider=ls_provider, data_provider_name="LS")
#
#     @staticmethod
#     def l(args: Args):
#         # Just call ls -la
#         # Reuse the parsed args for keep the (optional) path
#         args._parsed[LsArgs.SHOW_ALL[0]] = True
#         args._parsed[LsArgs.SHOW_DETAILS[0]] = True
#         Client.ls(args)
#
#     @staticmethod
#     def tree(args: Args):
#
#         def tree_provider(path, **kwargs):
#             path = pathify(path or os.getcwd())
#             kws = {k: v for k, v in kwargs.items() if k in ["sort_by", "name", "reverse", "max_depth"]}
#             return tree(path, **kws)
#
#         Client._tree(args, data_provider=tree_provider, data_provider_name="TREE")
#
#     @staticmethod
#     def mkdir(args: Args):
#         directory = pathify(args.get_varg())
#
#         if not directory:
#             raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)
#
#         log.i(">> MKDIR %s", directory)
#
#         os.mkdir(directory)
#
#     @staticmethod
#     def pwd(_: Args):
#         log.i(">> PWD")
#
#         print(os.getcwd())
#
#     @staticmethod
#     def rm(args: Args):
#         paths = [pathify(p) for p in args.get_vargs()]
#
#         if not paths:
#             raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)
#
#         log.i(">> RM %s", paths)
#
#         for p in paths:
#             rm(p, error_callback=lambda err: eprint(err))
#
#     @staticmethod
#     def mv(args: Args):
#         Client._mvcp(args, mv, "MV")
#
#     @staticmethod
#     def cp(args: Args):
#         Client._mvcp(args, cp, "CP")
#
#     @staticmethod
#     def exec(args: Args):
#         exec_args = args.get_unparsed_args()
#         exec_fullarg = " ".join(exec_args)
#         log.i(">> EXEC %s", exec_fullarg)
#         retcode = run_attached(exec_fullarg)
#         if retcode != 0:
#             log.w("Command failed with return code: %d", retcode)
#             raise BadOutcome(ClientErrors.COMMAND_EXECUTION_FAILED)
#
#     # === REMOTE COMMANDS ===
#
#     # RPWD
#
#     @provide_sharing_connection
#     def rpwd(self, _: Args, connection: Connection = None):
#         if not connection or not connection.is_connected():
#             raise BadOutcome(ClientErrors.NOT_CONNECTED)
#
#         log.i(">> RPWD")
#         print(connection.rpwd())
#
#     @provide_sharing_connection
#     def rcd(self, args: Args, connection: Connection = None):
#         if not connection or not connection.is_connected():
#             raise BadOutcome(ClientErrors.NOT_CONNECTED)
#
#         directory = args.get_varg(default="/")
#
#         log.i(">> RCD %s", directory)
#
#         resp = connection.rcd(directory)
#
#         if is_error_response(resp):
#             raise BadOutcome(resp.get("error"))
#
#     @provide_sharing_connection
#     def rls(self, args: Args, connection: Connection = None):
#         if not connection or not connection.is_connected():
#             raise BadOutcome(ClientErrors.NOT_CONNECTED)
#
#         def rls_provider(f, **kwargs):
#             resp = connection.rls(**kwargs, path=f)
#             if is_error_response(resp):
#                 raise BadOutcome(resp.get("error"))
#             return resp.get("data")
#
#         Client._ls(args, data_provider=rls_provider, data_provider_name="RLS")
#
#     @provide_sharing_connection
#     def rtree(self, args: Args, connection: Connection = None):
#         if not connection or not connection.is_connected():
#             raise BadOutcome(ClientErrors.NOT_CONNECTED)
#
#         def rtree_provider(f, **kwargs):
#             resp = connection.rtree(**kwargs, path=f)
#             if is_error_response(resp):
#                 raise BadOutcome(resp.get("error"))
#             return resp.get("data")
#
#         Client._tree(args, data_provider=rtree_provider, data_provider_name="RTREE")
#
#     @provide_sharing_connection
#     def rmkdir(self, args: Args, connection: Connection = None):
#         if not connection or not connection.is_connected():
#             raise BadOutcome(ClientErrors.NOT_CONNECTED)
#
#         directory = args.get_varg()
#
#         if not directory:
#             raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)
#
#         log.i(">> RMKDIR %s", directory)
#
#         resp = connection.rmkdir(directory)
#
#         if is_error_response(resp):
#             raise BadOutcome(resp.get("error"))
#
#     @provide_sharing_connection
#     def rrm(self, args: Args, connection: Connection = None):
#         if not connection or not connection.is_connected():
#             raise BadOutcome(ClientErrors.NOT_CONNECTED)
#
#         paths = args.get_vargs()
#
#         if not paths:
#             raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)
#
#         log.i(">> RRM %s ", paths)
#
#         resp = connection.rrm(paths)
#
#         if is_error_response(resp):
#             raise BadOutcome(resp.get("error"))
#
#         if is_data_response(resp, "errors"):
#             errors = resp.get("data").get("errors")
#             log.e("%d errors occurred while doing rrm", len(errors))
#             for err in errors:
#                 eprint(err)
#
#     @provide_sharing_connection
#     def rmv(self, args: Args, connection: Connection = None):
#         if not connection or not connection.is_connected():
#             raise BadOutcome(ClientErrors.NOT_CONNECTED)
#
#         Client._rmvcp(args, api=connection.rmv, api_name="RMV")
#
#     @provide_sharing_connection
#     def rcp(self, args: Args, connection: Connection = None):
#         if not connection or not connection.is_connected():
#             raise BadOutcome(ClientErrors.NOT_CONNECTED)
#
#         Client._rmvcp(args, api=connection.rcp, api_name="RCP")
#
#     @provide_server_connection
#     def rexec(self, args: Args, connection: Connection = None):
#         popen_args = args.get_unparsed_args()
#         popen_fullarg = " ".join(popen_args)
#         log.i(">> REXEC %s", popen_fullarg)
#
#         resp = connection.rexec(popen_fullarg)
#
#         if is_error_response(resp):
#             raise BadOutcome(resp.get("error"))
#
#         rexec_uri = resp.get("data")
#
#         log.d("URI: %s", rexec_uri)
#         rexec_transaction: Union[Pyro4.Proxy, IRexecTransaction] = Pyro4.Proxy(rexec_uri)
#         Pyro4.asyncproxy(rexec_transaction)
#         # resp = rx.jump()
#         # print(json_to_pretty_str(resp))
#
#         retcode = None
#
#         # --- STDOUT RECEIVER ---
#
#         def rexec_stdout_receiver():
#             nonlocal retcode
#             # nonlocal connection
#             nonlocal rexec_transaction
#
#             while retcode is None:
#                 resp = rexec_transaction.recv().value
#
#                 if is_error_response(resp):
#                     raise BadOutcome(resp.get("error"))
#
#                 recv_data = resp.get("data")
#
#                 # log.d("REXEC recv: %s", str(recv))
#                 stdout = recv_data.get("stdout")
#                 stderr = recv_data.get("stderr")
#                 retcode = recv_data.get("retcode")
#
#                 for line in stdout:
#                     print(line, end="", flush=True)
#
#                 for line in stderr:
#                     print(red(line), end="", flush=True)
#
#             log.i("REXEC done (%d)", retcode)
#
#         rexec_stdout_receiver_th = threading.Thread(
#             target=rexec_stdout_receiver, daemon=True)
#         rexec_stdout_receiver_th.start()
#
#         # --- STDIN SENDER ---
#
#         # Put stdin in non-blocking mode
#
#         stding_flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
#         fcntl.fcntl(sys.stdin, fcntl.F_SETFL, stding_flags | os.O_NONBLOCK)
#
#         # try:
#         while retcode is None:
#             try:
#                 rlist, wlist, xlist = select.select([sys.stdin], [], [], 0.04)
#
#                 if sys.stdin in rlist:
#                     data_b = sys.stdin.buffer.read()
#
#                     if data_b:
#                         data_s = bytes_to_str(data_b)
#                         log.d("Sending data: %s", data_s)
#                         rexec_transaction.send_data(data_s)
#                     else:
#                         log.d("rexec CTRL+D")
#                         rexec_transaction.send_event(IRexecTransaction.Event.EOF)
#             except KeyboardInterrupt:
#                 log.d("rexec CTRL+C")
#                 rexec_transaction.send_event(IRexecTransaction.Event.TERMINATE)
#
#         # Restore stdin in blocking mode
#
#         fcntl.fcntl(sys.stdin, fcntl.F_SETFL, stding_flags)
#
#         # Wait everybody
#
#         rexec_stdout_receiver_th.join()
#
#
#     def open(self, args: Args, _: Connection = None):
#         newconn = self._create_connection_from_sharing_spec(SharingSpecifier.parse(args.get_varg()))
#         if self.connection:
#             log.i("Closing current connection before create the new one")
#             self.connection.close()
#         self.connection = newconn
#
#     @provide_sharing_connection
#     def close(self, _: Optional[Args], connection: Connection = None):
#         if not connection or not connection.is_connected():
#             raise BadOutcome(ClientErrors.NOT_CONNECTED)
#
#         log.i(">> CLOSE")
#
#         connection.close()
#
#     def scan(self, args: Args, _: Connection = None):
#         show_details = ScanArgs.SHOW_DETAILS in args
#
#         log.i(">> SCAN")
#
#         servers_found = 0
#
#         def response_handler(client: Endpoint,
#                              server_info: ServerInfo) -> bool:
#             nonlocal servers_found
#
#             log.i("Handling DISCOVER response from %s\n%s", str(client), str(server_info))
#             # Print as soon as they come
#
#             if not servers_found:
#                 log.i("======================")
#             else:
#                 print("")
#
#             print("{} ({}:{})".format(
#                 server_info.get("name"),
#                 server_info.get("ip"),
#                 server_info.get("port")))
#
#             print(Client._sharings_string(server_info.get("sharings"),
#                                           details=show_details))
#
#             servers_found += 1
#
#             return True     # Continue DISCOVER
#
#         Discoverer(
#             server_discover_port=self._discover_port,
#             response_handler=response_handler).discover()
#
#         log.i("======================")
#
#     def info(self, args: Args, _: Connection = None):
#         # Can be done either
#         # 1. If connected to a server: we already have the server info
#         # 2. If not connected to a server: we have to fetch the server info
#
#         # Without parameter it means we are trying to see the info of the
#         # current connection
#         # With a parameter it means we are trying to see the info of a server
#         # The param should be a server specifier: <hostname>|<ip>[:<port>]
#
#         def print_server_info(info: ServerInfo):
#
#             SEP = "================================"
#
#             SEP_FIRST =              SEP + "\n\n"
#             SEP_MID =       "\n\n" + SEP + "\n\n"
#             SEP_LAST  =     "\n\n" + SEP
#
#             # Server info
#             s = SEP_FIRST + \
#                 "SERVER INFO\n\n" + \
#                 "Name:  {}\n".format(info.get("name")) + \
#                 "IP:    {}\n".format(info.get("ip")) + \
#                 "Port:  {}\n".format(info.get("port")) + \
#                 "SSL:   {}".format(info.get("ssl")) + \
#                 SEP_MID
#
#             # SSL?
#             if info.get("ssl"):
#                 ssl_cert = self._get_cached_or_fetch_ssl_certificate_for_endpoint(
#                     (info.get("ip"), info.get("port")))
#
#                 s += \
#                     "SSL CERTIFICATE\n\n" + \
#                     ssl_certificate_to_str(ssl_cert) + \
#                     SEP_MID
#
#             # Sharings
#             s += \
#                 "SHARINGS\n\n" + \
#                 Client._sharings_string(info.get("sharings"), details=True) + \
#                 SEP_LAST
#
#             print(s)
#
#         server_spec = ServerSpecifier.parse(args.get_varg())
#
#         server_info: Optional[ServerInfo] = None
#
#         if not server_spec:
#             if self.is_connected():
#                 log.d("Using server info of the current connection "
#                       "since server specifier not provided")
#                 server_info = self.connection.server_info
#             else:
#                 log.e("Server specifier must be provided (since not connected to a server)")
#                 return ClientErrors.INVALID_COMMAND_SYNTAX
#
#         if server_spec:
#             server_info = self._discover_server(server_spec)
#
#         if not server_info:
#             return ClientErrors.SERVER_NOT_FOUND
#
#         # Server info retrieved successfully
#         print_server_info(server_info)
#
#     @provide_server_connection
#     def ping(self, args: Args, connection: Connection = None):
#         # if not connection or not connection.is_connected():
#         if not connection:
#             raise BadOutcome(ClientErrors.NOT_CONNECTED)
#
#         count = args.get_kwarg_param(PingArgs.COUNT, default=None)
#
#         i = 1
#         while not count or i <= count:
#             start = time.monotonic_ns()
#             resp = connection.ping()
#             end = time.monotonic_ns()
#
#             if is_data_response(resp) and resp.get("data") == "pong":
#                 print("[{}] OK      time={:.1f}ms".format(i, (end - start) * 1e-6))
#             else:
#                 print("[{}] FAIL")
#
#             i += 1
#             time.sleep(1)
#
#
#     def put_files(self, args: Args):
#         if not self.is_connected():
#             print_error(ClientErrors.NOT_CONNECTED)
#             return
#
#         files = args.get_params(default=[])
#
#         log.i(">> PUT [files] %s", files)
#         self._do_put(self.connection, files, args)
#
#
#     def put_sharing(self, args: Args):
#         if self.is_connected():
#             # We should not reach this point if we are connected to a sharing
#             print_error(ClientErrors.IMPLEMENTATION_ERROR)
#             return
#
#         params = args.get_params()
#         sharing_specifier = params.pop(0)
#
#         if not sharing_specifier:
#             print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
#             return
#
#         sharing_name, _, sharing_location = sharing_specifier.rpartition("@")
#
#         if not sharing_name:
#             # if @ is not found, rpartition put the entire string on
#             # the last element of th tuple
#             sharing_name = sharing_location
#             sharing_location = None
#
#         timeout = to_int(args.get_param(ScanArgs.TIMEOUT,
#                                         default=Discoverer.DEFAULT_TIMEOUT))
#
#         if not timeout:
#             print_error(ClientErrors.INVALID_PARAMETER_VALUE)
#             return False
#
#         # We have to perform a discover
#
#         sharing_info, server_info = self._discover_sharing(
#             name=sharing_name,
#             location=sharing_location,
#             timeout=timeout
#         )
#
#         if not server_info:
#             print_error(ClientErrors.SHARING_NOT_FOUND)
#             return False
#
#         log.d("Creating new temporary connection with %s", server_info.get("uri"))
#         connection = Connection(server_info)
#
#         # FIXME: refactor - introduce password in the method
#
#         # Open a temporary connection
#
#         log.i("Opening temporary connection")
#         open_response = connection.open(sharing_name)
#
#         if not is_success_response(open_response):
#             log.w("Cannot open connection; aborting")
#             print_response_error(open_response)
#             return
#
#         files = ["."] if not params else params
#         log.i(">> PUT [sharing] %s %s", sharing_name)
#         self._do_put(connection, files, args)
#
#         # Close connection
#         log.d("Closing temporary connection")
#         connection.close()
#
#     def get_files(self, args: Args):
#         if not self.is_connected():
#             print_error(ClientErrors.NOT_CONNECTED)
#             return
#
#         files = args.get_params(default=[])
#
#         log.i(">> GET [files] %s", files)
#         self._do_get(self.connection, files, args)
#
#     def get_sharing(self, args: Args):
#         if self.is_connected():
#             # We should not reach this point if we are connected to a sharing
#             print_error(ClientErrors.IMPLEMENTATION_ERROR)
#             return
#
#         params = args.get_params()
#         sharing_specifier = params.pop(0)
#
#         if not sharing_specifier:
#             print_error(ClientErrors.INVALID_COMMAND_SYNTAX)
#             return
#
#         sharing_name, _, sharing_location = sharing_specifier.rpartition("@")
#
#         if not sharing_name:
#             # if @ is not found, rpartition put the entire string on
#             # the last element of th tuple
#             sharing_name = sharing_location
#             sharing_location = None
#
#         timeout = to_int(args.get_param(ScanArgs.TIMEOUT,
#                                         default=Discoverer.DEFAULT_TIMEOUT))
#
#         if not timeout:
#             print_error(ClientErrors.INVALID_PARAMETER_VALUE)
#             return False
#
#         # We have to perform a discover
#
#         sharing_info, server_info = self._discover_sharing(
#             name=sharing_name,
#             location=sharing_location,
#             timeout=timeout
#         )
#
#         if not server_info:
#             print_error(ClientErrors.SHARING_NOT_FOUND)
#             return False
#
#         log.d("Creating new temporary connection with %s", server_info.get("uri"))
#         connection = Connection(server_info)
#
#         # Open connection
#
#         log.i("Opening temporary connection")
#         open_response = connection.open(sharing_name)
#
#         if not is_success_response(open_response):
#             log.w("Cannot open connection; aborting")
#             print_response_error(open_response)
#             return
#
#         files = ["."] if not params else params
#         log.i(">> GET [sharing] %s %s", sharing_name)
#         self._do_get(connection, files, args)
#
#         # Close connection
#         log.d("Closing temporary connection")
#         connection.close()
#
#     def _do_put(self,
#                 connection: Connection,
#                 files: List[str],
#                 args: Args):
#         if not connection.is_connected():
#             log.e("Connection must be opened for do GET")
#             return
#
#         if len(files) == 0:
#             files = ["."]
#
#         overwrite_all: Optional[bool] = None
#
#         if PutArguments.YES_TO_ALL in args:
#             overwrite_all = True
#         if PutArguments.NO_TO_ALL in args:
#             overwrite_all = False
#
#         log.i("Overwrite all mode: %s", bool_to_str(overwrite_all))
#
#         put_response = connection.put()
#
#         # if not is_data_response(put_response):
#         #     print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
#         #     return
#
#         if not is_success_response(put_response):
#             Client._handle_connection_error_response(connection, put_response)
#             return
#
#         transaction_id = put_response["data"].get("transaction")
#         port = put_response["data"].get("port")
#
#         if not transaction_id or not port:
#             print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
#             return
#
#         log.i("Successfully PUTed")
#         transfer_socket = SocketTcpOut(
#             connection.server_info.get("ip"), port,
#             ssl_context=get_ssl_context(),
#             ssl_server_side=False
#         )
#
#         files = sorted(files, reverse=True)
#         sendfiles: List[dict] = []
#
#         for f in files:
#             _, trail = os.path.split(f)
#             log.i("-> trail: %s", trail)
#             sendfile = {
#                 "local": f,
#                 "remote": trail
#             }
#             log.i("Adding sendfile %s", json_to_pretty_str(sendfile))
#             sendfiles.append(sendfile)
#
#
#         def send_file(local_path: str, remote_path: str):
#             nonlocal overwrite_all
#
#             fstat = os.lstat(local_path)
#             fsize = fstat.st_size
#
#             if S_ISDIR(fstat.st_mode):
#                 ftype = FTYPE_DIR
#             elif S_ISREG(fstat.st_mode):
#                 ftype = FTYPE_FILE
#             else:
#                 log.w("Unknown file type")
#                 return
#
#             finfo = {
#                 "name": remote_path,
#                 "ftype": ftype,
#                 "size": fsize
#             }
#
#             log.i("send_file finfo: %s", json_to_pretty_str(finfo))
#
#             log.d("doing a put_next_info")
#
#             resp = connection.put_next_info(transaction_id, finfo)
#
#             if not is_success_response(resp):
#                 Client._handle_connection_error_response(connection, resp)
#                 return
#
#             # Overwrite handling
#
#             if is_data_response(resp) and resp.get("data") == "ask_overwrite":
#
#                 # Ask whether overwrite just once or forever
#                 current_overwrite_decision = overwrite_all
#
#                 # Ask until we get a valid answer
#                 while current_overwrite_decision is None:
#
#                     overwrite_answer = input(
#                         "{} already exists, overwrite it? [Y : yes / yy : yes to all / n : no / nn : no to all] "
#                             .format(remote_path)
#                     ).lower()
#
#                     if not overwrite_answer or overwrite_answer == "y":
#                         current_overwrite_decision = True
#                     elif overwrite_answer == "n":
#                         current_overwrite_decision = False
#                     elif overwrite_answer == "yy":
#                         current_overwrite_decision = overwrite_all = True
#                     elif overwrite_answer == "nn":
#                         current_overwrite_decision = overwrite_all = False
#                     else:
#                         log.w("Invalid answer, asking again")
#
#                 if current_overwrite_decision is False:
#                     log.i("Skipping " + remote_path)
#                     return
#                 else:
#                     log.d("Will overwrite file")
#
#             progressor = FileProgressor(
#                 fsize,
#                 description="PUT " + local_path,
#                 color_progress=PROGRESS_COLOR,
#                 color_done=DONE_COLOR
#             )
#
#             if ftype == FTYPE_DIR:
#                 log.d("Sent a DIR, nothing else to do")
#                 progressor.done()
#                 return
#
#             log.d("Actually sending the file")
#
#             BUFFER_SIZE = 4096
#
#             f = open(local_path, "rb")
#
#             cur_pos = 0
#
#             while cur_pos < fsize:
#                 r = random.random() * 0.001
#                 time.sleep(0.001 + r)
#
#                 chunk = f.read(BUFFER_SIZE)
#                 log.i("Read chunk of %dB", len(chunk))
#
#                 if not chunk:
#                     log.i("Finished %s", local_path)
#                     # FIXME: sending something?
#                     break
#
#                 transfer_socket.send(chunk)
#
#                 cur_pos += len(chunk)
#                 progressor.update(cur_pos)
#
#             log.i("DONE %s", local_path)
#             f.close()
#
#             progressor.done()
#
#
#         while sendfiles:
#             log.i("Putting another file info")
#             next_file = sendfiles.pop()
#
#             # Check what is this
#             # 1. Non existing: skip
#             # 2. A file: send it directly (parent dirs won't be replicated)
#             # 3. A dir: send it recursively
#
#             next_file_local = next_file.get("local")
#             next_file_remote = next_file.get("remote")
#
#             if os.path.isfile(next_file_local):
#                 # Send it directly
#                 log.d("-> is a FILE")
#                 send_file(next_file_local, next_file_remote)
#
#             elif os.path.isdir(next_file_local):
#                 # Send it recursively
#
#                 log.d("-> is a DIR")
#
#                 # Directory found
#                 dir_files = sorted(os.listdir(next_file_local), reverse=True)
#
#                 if dir_files:
#
#                     log.i("Found a filled directory: adding all inner files to remaining_files")
#                     for f in dir_files:
#                         f_path_local = os.path.join(next_file_local, f)
#                         f_path_remote = os.path.join(next_file_remote, f)
#                         # Push to the begin instead of the end
#                         # In this way we perform a breadth-first search
#                         # instead of a depth-first search, which makes more sense
#                         # because we will push the files that belongs to the same
#                         # directory at the same time
#                         sendfile = {
#                             "local": f_path_local,
#                             "remote": f_path_remote
#                         }
#                         log.i("Adding sendfile %s", json_to_pretty_str(sendfile))
#
#                         sendfiles.append(sendfile)
#                 else:
#                     log.i("Found an empty directory")
#                     log.d("Pushing an info for the empty directory")
#
#                     send_file(next_file_local, next_file_remote)
#             else:
#                 eprint("Failed to send '{}'".format(next_file_local))
#                 log.w("Unknown file type, doing nothing")
#
#     def _do_get(self,
#                 connection: Connection,
#                 files: List[str],
#                 args: Args):
#         if not connection.is_connected():
#             log.e("Connection must be opened for do GET")
#             return
#
#         get_response = connection.get(files)
#
#         if not is_data_response(get_response):
#             print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
#             return
#
#         if is_error_response(get_response):
#             Client._handle_connection_error_response(connection, get_response)
#             return
#
#         transaction_id = get_response["data"].get("transaction")
#         port = get_response["data"].get("port")
#
#         if not transaction_id or not port:
#             print_error(ClientErrors.UNEXPECTED_SERVER_RESPONSE)
#             return
#
#         log.i("Successfully GETed")
#
#         transfer_socket = SocketTcpOut(
#             connection.server_info.get("ip"), port,
#             ssl_context=get_ssl_context(),
#             ssl_server_side=False
#         )
#
#         overwrite_all: Optional[bool] = None
#
#         if GetArguments.YES_TO_ALL in args:
#             overwrite_all = True
#         if GetArguments.NO_TO_ALL in args:
#             overwrite_all = False
#
#         log.i("Overwrite all mode: %s", bool_to_str(overwrite_all))
#
#         while True:
#             log.i("Fetching another file info")
#             get_next_resp = connection.get_next_info(transaction_id)
#
#             log.i("get_next_info()\n%s", get_next_resp)
#
#             if not is_success_response(get_next_resp):
#                 print_error(ClientErrors.COMMAND_EXECUTION_FAILED)
#                 return
#
#             next_file: FileInfo = get_next_resp.get("data")
#
#             if not next_file:
#                 log.i("Nothing more to GET")
#                 break
#
#             fname = next_file.get("name")
#             fsize = next_file.get("size")
#             ftype = next_file.get("ftype")
#
#             log.i("NEXT: %s of type %s", fname, ftype)
#
#             progressor = FileProgressor(
#                 fsize,
#                 description="GET " + fname,
#                 color_progress=PROGRESS_COLOR,
#                 color_done=DONE_COLOR
#             )
#
#             # Case: DIR
#             if ftype == FTYPE_DIR:
#                 log.i("Creating dirs %s", fname)
#                 os.makedirs(fname, exist_ok=True)
#                 progressor.done()
#                 continue
#
#             if ftype != FTYPE_FILE:
#                 log.w("Cannot handle this ftype")
#                 continue
#
#             # Case: FILE
#             parent_dirs, _ = os.path.split(fname)
#             if parent_dirs:
#                 log.i("Creating parent dirs %s", parent_dirs)
#                 os.makedirs(parent_dirs, exist_ok=True)
#
#             # Check wheter it already exists
#             if os.path.isfile(fname):
#                 log.w("File already exists, asking whether overwrite it (if needed)")
#
#                 # Ask whether overwrite just once or forever
#                 current_overwrite_decision = overwrite_all
#
#                 # Ask until we get a valid answer
#                 while current_overwrite_decision is None:
#
#                     overwrite_answer = input(
#                         "{} already exists, overwrite it? [Y : yes / yy : yes to all / n : no / nn : no to all] "
#                             .format(fname)
#                     ).lower()
#
#                     if not overwrite_answer or overwrite_answer == "y":
#                         current_overwrite_decision = True
#                     elif overwrite_answer == "n":
#                         current_overwrite_decision = False
#                     elif overwrite_answer == "yy":
#                         current_overwrite_decision = overwrite_all = True
#                     elif overwrite_answer == "nn":
#                         current_overwrite_decision = overwrite_all = False
#                     else:
#                         log.w("Invalid answer, asking again")
#
#                 if current_overwrite_decision is False:
#                     log.i("Skipping " + fname)
#                     continue
#                 else:
#                     log.d("Will overwrite file")
#
#             log.i("Opening file '{}' locally".format(fname))
#             file = open(fname, "wb")
#
#             # Really get it
#
#             BUFFER_SIZE = 4096
#
#             read = 0
#
#             while read < fsize:
#                 recv_size = min(BUFFER_SIZE, fsize - read)
#                 chunk = transfer_socket.recv(recv_size)
#
#                 if not chunk:
#                     log.i("END")
#                     break
#
#                 chunk_len = len(chunk)
#
#                 log.i("Read chunk of %dB", chunk_len)
#
#                 written_chunk_len = file.write(chunk)
#
#                 if chunk_len != written_chunk_len:
#                     log.w("Written less bytes than expected: something will go wrong")
#                     exit(-1)
#
#                 read += written_chunk_len
#                 log.i("%d/%d (%.2f%%)", read, fsize, read / fsize * 100)
#                 progressor.update(read)
#
#             progressor.done()
#             log.i("DONE %s", fname)
#             file.close()
#
#             if os.path.getsize(fname) == fsize:
#                 log.d("File OK (length match)")
#             else:
#                 log.e("File length mismatch. %d != %d",
#                   os.path.getsize(fname), fsize)
#
#         log.i("GET transaction %s finished, closing socket", transaction_id)
#         transfer_socket.close()
#
#     def get(self, args: Args):
#         # 'get' command is multipurpose
#         # 1. Inside a connection: get a list of files (or directories)
#         # 2. Outside a connection:
#         #   2.1 get a file sharing (ftype = 'file')
#         #   2.2 get all the content of directory sharing (ftype = 'dir')
#
#         if self.is_connected():
#             log.d("GET => get_files")
#             self.get_files(args)
#         else:
#             log.d("GET => get_sharing")
#             self.get_sharing(args)
#
#     def put(self, args: Args):
#         if self.is_connected():
#             log.d("PUT => put_files")
#             self.put_files(args)
#         else:
#             log.d("PUT => put_sharing")
#             self.put_sharing(args)
#
#     @staticmethod
#     def _ls(args: Args,
#             data_provider: Callable[..., Optional[List[FileInfo]]],
#             data_provider_name: str = "LS"):
#
#         path = args.get_varg()
#         reverse = LsArgs.REVERSE in args
#         show_hidden = LsArgs.SHOW_ALL in args
#
#         # Sorting
#         sort_by = ["name"]
#
#         if LsArgs.SORT_BY_SIZE in args:
#             sort_by.append("size")
#         if LsArgs.GROUP in args:
#             sort_by.append("ftype")
#
#         log.i(">> %s %s (sort by %s%s)",
#               data_provider_name, path or "*", sort_by, " | reverse" if reverse else "")
#
#         ls_result = data_provider(path, sort_by=sort_by, reverse=reverse)
#
#         if ls_result is None:
#             raise BadOutcome(ClientErrors.COMMAND_EXECUTION_FAILED)
#
#         print_files_info_list(
#             ls_result,
#             show_file_type=LsArgs.SHOW_DETAILS in args,
#             show_hidden=LsArgs.SHOW_ALL in args,
#             show_size=LsArgs.SHOW_SIZE in args or LsArgs.SHOW_DETAILS in args,
#             compact=LsArgs.SHOW_DETAILS not in args
#         )
#
#     @staticmethod
#     def _tree(args: Args,
#               data_provider: Callable[..., Optional[FileInfoTreeNode]],
#               data_provider_name: str = "TREE"):
#
#         path = args.get_varg()
#         reverse = TreeArgs.REVERSE in args
#         show_hidden = TreeArgs.SHOW_ALL in args
#         max_depth = args.get_kwarg_param(TreeArgs.MAX_DEPTH, default=None)
#
#         sort_by = ["name"]
#
#         if TreeArgs.SORT_BY_SIZE in args:
#             sort_by.append("size")
#         if TreeArgs.GROUP in args:
#             sort_by.append("ftype")
#
#         log.i(">> %s %s (sort by %s%s)",
#               data_provider_name, path or "*", sort_by, " | reverse" if reverse else "")
#
#         tree_result: FileInfoTreeNode = data_provider(
#             path,
#             sort_by=sort_by, reverse=reverse,
#             hidden=show_hidden, max_depth=max_depth
#         )
#
#         if tree_result is None:
#             raise BadOutcome(ClientErrors.COMMAND_EXECUTION_FAILED)
#
#         print_files_info_tree(tree_result,
#                               max_depth=max_depth,
#                               show_hidden=show_hidden,
#                               show_size=TreeArgs.SHOW_SIZE in args or TreeArgs.SHOW_DETAILS in args)
#
#     @staticmethod
#     def _mvcp(args: Args,
#               primitive: Callable[[str, str], bool],
#               primitive_name: str = "MV/CP"):
#         """
#                 mv <src>... <dest>
#
#                 A1  At least two parameters
#                 A2  If a <src> doesn't exist => IGNORES it
#
#                 2 args:
#                 B1  If <dest> exists
#                     B1.1    If type of <dest> is DIR => put <src> into <dest> anyway
#
#                     B1.2    If type of <dest> is FILE
#                         B1.2.1  If type of <src> is DIR => ERROR
#                         B1.2.2  If type of <src> is FILE => OVERWRITE
#                 B2  If <dest> doesn't exist => preserve type of <src>
#
#                 3 args:
#                 C1  if <dest> exists => must be a dir
#                 C2  If <dest> doesn't exist => ERROR
#
#                 """
#         mvcp_args = [pathify(f) for f in args.get_vargs()]
#
#         if not mvcp_args or len(mvcp_args) < 2:
#             raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)
#
#         dest = mvcp_args.pop()
#
#         # C1/C2 check: with 3+ arguments
#         if len(mvcp_args) >= 3:
#             # C1  if <dest> exists => must be a dir
#             # C2  If <dest> doesn't exist => ERROR
#             # => must be a valid dir
#             if not os.path.isdir(dest):
#                 log.e("'%s' must be an existing directory", dest)
#                 raise BadOutcome(ClientErrors.INVALID_PATH)
#
#         # Every other constraint is well handled by shutil.move()
#         errors = []
#
#         for src in mvcp_args:
#             log.i(">> %s '%s' '%s'", primitive_name, src, dest)
#             try:
#                 primitive(src, dest)
#             except Exception as ex:
#                 errors.append(str(ex))
#
#         if errors:
#             log.e("%d errors occurred", len(errors))
#
#         for err in errors:
#             eprint(err)
#
#     @staticmethod
#     def _rmvcp(args: Args,
#                api: Callable[[List[str], str], Response],
#                api_name: str = "RMV/RCP"):
#         paths = args.get_vargs()
#
#         if not paths:
#             raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)
#
#         dest = paths.pop()
#
#         if not dest or not paths:
#             raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)
#
#         log.i(">> %s %s -> %s", api_name, str(paths), dest)
#
#         resp = api(paths, dest)
#
#         if is_error_response(resp):
#             raise BadOutcome(resp.get("error"))
#
#         if is_data_response(resp, "errors"):
#             errors = resp.get("data").get("errors")
#             log.e("%d errors occurred while doing %s", len(errors), api_name)
#             for err in errors:
#                 eprint(err)
#
#     def _create_connection_from_sharing_spec(self, sharing_spec: SharingSpecifier) -> Connection:
#         if not sharing_spec:
#             raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)
#
#         log.d("Sharing specifier: %s", sharing_spec)
#
#         # Discover the server to which connect
#         sharing_info, server_info = self._discover_sharing(
#             sharing_spec, ftype=FTYPE_DIR
#         )
#
#         if not sharing_info or not server_info:
#             raise BadOutcome(ClientErrors.SHARING_NOT_FOUND)
#
#         log.i("Creating new connection with %s", server_info.get("uri"))
#         conn = Connection(server_info)
#
#         # open() the connection
#
#         passwd = None
#
#         # Ask the password if the sharing is protected by auth
#         if sharing_info.get("auth"):
#             log.i("Sharing '%s' is protected by password", sharing_spec.name)
#             passwd = getpass()
#         else:
#             log.i("Sharing '%s' is not protected", sharing_spec.name)
#
#         # Actually send open()
#         resp = conn.open(sharing_spec.name, password=passwd)
#         if is_error_response(resp):
#             raise BadOutcome(resp.get("error"))
#
#         log.i("Connection established with %s:%d",
#               server_info.get("ip"), server_info.get("port"))
#
#         if server_info.get("ssl"):
#             ssl_cert = self._get_cached_or_fetch_ssl_certificate_for_connection(conn)
#
#             if ssl_cert:
#                 log.i("Remote SSL certificate\n"
#                       "================================\n"
#                       "%s\n"
#                       "================================", ssl_certificate_to_str(ssl_cert))
#             else:
#                 log.w("Remote SSL certificate cannot be verified")
#         else:
#             log.w("Opened a plain connection; use SSL if possible")
#
#         return conn
#
#
#     def _create_connection_from_server_spec(self, server_spec: ServerSpecifier) -> Connection:
#         if not server_spec:
#             raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)
#
#         log.d("Server specifier: %s", server_spec)
#
#         # Discover the server to which connect
#         server_info = self._discover_server(server_spec)
#
#         if not server_info:
#             raise BadOutcome(ClientErrors.SERVER_NOT_FOUND)
#
#         log.i("Creating new connection with %s", server_info.get("uri"))
#         conn = Connection(server_info)
#
#         # open() the connection
#
#         passwd = None
#
#         # Ask the password if the sharing is protected by auth
#         if server_info.get("auth"):
#             log.i("Server '%s' is protected by password", server_spec.name)
#             passwd = getpass()
#         else:
#             log.i("Server '%s' is not protected", server_spec.name)
#
#         log.i("Connection established with %s:%d",
#               server_info.get("ip"), server_info.get("port"))
#
#         #
#         # # Actually send open()
#         # resp = conn.open(sharing_spec.name, password=passwd)
#         # if is_error_response(resp):
#         #     raise BadOutcome(resp.get("error"))
#         #
#         #
#         # if server_info.get("ssl"):
#         #     ssl_cert = self._get_cached_or_fetch_ssl_certificate_for_connection(conn)
#         #
#         #     if ssl_cert:
#         #         log.i("Remote SSL certificate\n"
#         #               "================================\n"
#         #               "%s\n"
#         #               "================================", ssl_certificate_to_str(ssl_cert))
#         #     else:
#         #         log.w("Remote SSL certificate cannot be verified")
#         # else:
#         #     log.w("Opened a plain connection; use SSL if possible")
#
#         return conn
#
#
#     def _get_current_or_create_connection_from_sharing_spec_args(self, args: Args) -> Connection:
#         if self.is_connected():
#             log.i("Providing already established connection")
#             return self.connection
#
#         # Create temporary connection
#         log.i("No established connection; creating a new one")
#
#         vargs = args.get_vargs()
#
#         if not vargs:
#             raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)
#
#         sharing_spec = SharingSpecifier.parse(vargs.pop(0))
#         return self._create_connection_from_sharing_spec(sharing_spec)
#
#
#     def _get_current_or_create_connection_from_server_spec_args(self, args: Args) -> Connection:
#         if self.is_connected():
#             log.i("Providing already established connection")
#             return self.connection
#
#         # Create temporary connection
#         log.i("No established connection; creating a new one")
#
#         vargs = args.get_vargs()
#
#         if not vargs:
#             raise BadOutcome(ClientErrors.INVALID_COMMAND_SYNTAX)
#
#         server_spec = ServerSpecifier.parse(vargs.pop(0))
#         return self._create_connection_from_server_spec(server_spec)
#
#     def _discover_server(self, server_spec: ServerSpecifier) -> Optional[ServerInfo]:
#         if not server_spec:
#             log.w("Null server spec, no server will be found")
#             return None
#
#         server_info: Optional[ServerInfo] = None
#
#         def response_handler(client_endpoint: Endpoint,
#                              a_server_info: ServerInfo) -> bool:
#             nonlocal server_info
#             log.d("Handling DISCOVER response from %s\n%s",
#                   str(client_endpoint), str(a_server_info))
#
#             # Check against the location filters
#
#             # Server name check (optional)
#             if server_spec.name and a_server_info.get("name") != server_spec.name:
#                 log.d("Discarding server info which does not match the server name filter '%s'",
#                       server_spec.name)
#                 return True  # Continue DISCOVER
#
#             # Server ip check (optional)
#             if server_spec.ip and a_server_info.get("ip") != server_spec.ip:
#                 log.d("Discarding server info which does not match the ip filter '%s'",
#                       server_spec.ip)
#                 return True  # Continue DISCOVER
#
#             # Server port check (optional)
#             if server_spec.port and a_server_info.get("port") != server_spec.port:
#                 log.d("Discarding server info which does not match the port filter '%d'",
#                       server_spec.port)
#                 return True  # Continue DISCOVER
#
#             server_info = a_server_info
#             return False  # Stop DISCOVER
#
#         Discoverer(
#             server_discover_port=self._discover_port,
#             server_discover_addr=server_spec.ip or ADDR_BROADCAST,
#             response_handler=response_handler).discover()
#
#         return server_info
#
#     def _discover_sharing(self,
#                           sharing_spec: SharingSpecifier,
#                           ftype: FileType = None) -> Tuple[Optional[SharingInfo], Optional[ServerInfo]]:
#
#         if not sharing_spec:
#             log.w("Null sharing spec, no sharing will be found")
#             return None, None
#
#         sharing_info: Optional[SharingInfo] = None
#         server_info: Optional[ServerInfo] = None
#
#         def response_handler(client_endpoint: Endpoint,
#                              a_server_info: ServerInfo) -> bool:
#
#             nonlocal sharing_info
#             nonlocal server_info
#
#             log.d("Handling DISCOVER response from %s\n%s",
#                   str(client_endpoint), str(a_server_info))
#
#             # Check against the location filters
#
#             # Server name check (optional)
#             if sharing_spec.server_name and a_server_info.get("name") != sharing_spec.server_name:
#                 log.d("Discarding server info which does not match the server name filter '%s'",
#                       sharing_spec.server_name)
#                 return True  # Continue DISCOVER
#
#             # Server ip check (optional)
#             if sharing_spec.server_ip and a_server_info.get("ip") != sharing_spec.server_ip:
#                 log.d("Discarding server info which does not match the ip filter '%s'",
#                       sharing_spec.server_ip)
#                 return True  # Continue DISCOVER
#
#             # Server port check (optional)
#             if sharing_spec.server_port and a_server_info.get("port") != sharing_spec.server_port:
#                 log.d("Discarding server info which does not match the port filter '%d'",
#                       sharing_spec.server_port)
#                 return True  # Continue DISCOVER
#
#             for a_sharing_info in a_server_info.get("sharings"):
#                 # Sharing name check (mandatory)
#                 if sharing_spec.name and a_sharing_info.get("name") != sharing_spec.name:
#                     log.d("Ignoring sharing which does not match the sharing name filter '%s'",
#                           sharing_spec.name)
#                     continue
#
#                 # Ftype check (optional)
#                 if ftype and a_sharing_info.get("ftype") != ftype:
#                     log.d("Ignoring sharing which does not match the ftype filter '%s'", ftype)
#                     log.w("Found a sharing with the right name but wrong ftype, wrong command maybe?")
#                     continue
#
#                 # FOUND
#                 log.i("Sharing [%s] found at %s:%d",
#                       a_sharing_info.get("name"),
#                       a_server_info.get("ip"),
#                       a_server_info.get("port"))
#
#                 server_info = a_server_info
#                 sharing_info = a_sharing_info
#                 return False        # Stop DISCOVER
#
#             return True             # Continue DISCOVER
#
#         Discoverer(
#             server_discover_port=self._discover_port,
#             server_discover_addr=sharing_spec.server_ip or ADDR_BROADCAST,
#             response_handler=response_handler).discover()
#
#         return sharing_info, server_info
#
#     @staticmethod
#     def _sharings_string(sharings: List[SharingInfo], details: bool = False) -> str:
#         s = ""
#
#         d_sharings = [sh for sh in sharings if sh.get("ftype") == FTYPE_DIR]
#         f_sharings = [sh for sh in sharings if sh.get("ftype") == FTYPE_FILE]
#
#         def sharing_string(sharing: SharingInfo):
#             ss = "  - " + sharing.get("name")
#
#             if details:
#                 details_list = []
#                 if sharing.get("auth"):
#                     details_list.append("auth required")
#                 if sharing.get("read_only"):
#                     details_list.append("read only")
#                 if details_list:
#                     ss += "  ({})".format(", ".join(details_list))
#             ss += "\n"
#             return ss
#
#         if d_sharings:
#             s += "  DIRECTORIES\n"
#             for dsh in d_sharings:
#                 s += sharing_string(dsh)
#
#         if f_sharings:
#             s += "  FILES\n"
#             for fsh in f_sharings:
#                 s += sharing_string(fsh)
#
#         return s.rstrip("\n")
#
#     def _handle_error_response(self, resp: Response):
#         Client._handle_connection_error_response(self.connection, resp)
#
#     def _get_cached_or_fetch_ssl_certificate(
#             self,
#             endpoint: Endpoint,
#             peercert_provider: Callable[..., Optional[bytes]]) -> Optional[SSLCertificate]:
#
#         if endpoint not in self._certs_cache:
#             log.d("No cached SSL cert found for %s, fetching and parsing now", endpoint)
#             cert_bin = peercert_provider()
#             cert = None
#             try:
#                 cert = parse_ssl_certificate(cert_bin)
#             except:
#                 log.exception("Certificate parsing error occurred")
#             self._certs_cache[endpoint] = cert
#         else:
#             log.d("Found cached SSL cert for %s", endpoint)
#
#         return self._certs_cache[endpoint]
#
#     def _get_cached_or_fetch_ssl_certificate_for_connection(self, conn: Connection) -> Optional[SSLCertificate]:
#         return self._get_cached_or_fetch_ssl_certificate(
#             endpoint=(conn.server_info.get("ip"), conn.server_info.get("port")),
#             peercert_provider=lambda: conn.ssl_certificate()
#         )
#
#     def _get_cached_or_fetch_ssl_certificate_for_endpoint(self, endpoint: Endpoint) -> Optional[SSLCertificate]:
#         return self._get_cached_or_fetch_ssl_certificate(
#             endpoint=endpoint,
#             peercert_provider=lambda: SocketTcpOut(
#                 endpoint[0], endpoint[1], ssl_context=create_client_ssl_context()
#             ).ssl_certificate()
#         )
