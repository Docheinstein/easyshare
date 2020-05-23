import os
from pathlib import Path
from typing import Callable, List, Tuple, Optional

from Pyro5.server import expose
from easyshare.esd.services import BaseClientSharingService, BaseClientService, check_sharing_service_owner, FPath

from easyshare.esd.common import ClientContext, Sharing
from easyshare.esd.services.transfer.get import GetService
from easyshare.esd.services.transfer.put import PutService
from easyshare.logging import get_logger
from easyshare.protocol.services import ISharingService
from easyshare.protocol.responses import create_success_response, ServerErrors, create_error_response, Response, \
    create_error_of_response
from easyshare.protocol.types import FTYPE_FILE, FTYPE_DIR
from easyshare.utils.json import j
from easyshare.utils.os import rm, mv, cp, tree, ls, os_error_str
from easyshare.utils.pyro.server import pyro_client_endpoint, trace_api, try_or_command_failed_response
from easyshare.utils.str import q
from easyshare.utils.types import is_str, is_list, is_bool, is_valid_list

log = get_logger(__name__)

# =============================================
# ============== SHARING SERVICE ==============
# =============================================


def check_write_permission(api):
    def check_write_permission_wrapper(service: 'SharingService', *vargs, **kwargs):
        if service._sharing.read_only:
            log.e("Forbidden: write action on read only sharing by [%s]", pyro_client_endpoint())
            return service._err_resp(ServerErrors.NOT_WRITABLE)
        return api(service, *vargs, **kwargs)

    check_write_permission_wrapper.__name__ = api.__name__

    return check_write_permission_wrapper


def ensure_d_sharing(api):
    def ensure_d_sharing_wrapper(service: 'SharingService', *vargs, **kwargs):
        if service._sharing.ftype != FTYPE_DIR:
            log.e("Forbidden: command allowed only for DIR sharing by [%s]", pyro_client_endpoint())
            return service._err_resp(ServerErrors.NOT_ALLOWED_FOR_F_SHARING)
        return api(service, *vargs, **kwargs)

    ensure_d_sharing_wrapper.__name__ = api.__name__

    return ensure_d_sharing_wrapper



class SharingService(ISharingService, BaseClientSharingService):
    """
    Implementation of 'ISharingService' interface that will be published with Pyro.
    Offers all the methods that operate on a sharing (e.g. rls, rmv, get, put).
    """

    def __init__(self,
                 server_port: int,
                 sharing: Sharing,
                 sharing_rcwd: Path,
                 client: ClientContext,
                 end_callback: Callable[[BaseClientService], None]):
        super().__init__(sharing, sharing_rcwd, client, end_callback)
        self._server_port = server_port


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_sharing_service_owner
    @ensure_d_sharing
    def rcd(self, spath: str) -> Response:
        spath = spath or "/"

        if not is_str(spath):
            return self._err_resp(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RCD %s [%s]", spath, str(client_endpoint))
        new_rcwd_fpath = self._fpath_joining_rcwd_and_spath(spath)

        log.d("User would cd into: %s", new_rcwd_fpath)

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(new_rcwd_fpath):
            return self._err_resp(ServerErrors.INVALID_PATH, q(spath))

        # Check if it actually exists
        if not new_rcwd_fpath.is_dir():
            return self._err_resp(ServerErrors.NOT_A_DIRECTORY, new_rcwd_fpath)

        # The path is allowed and exists, setting it as new rcwd
        self._rcwd_fpath = new_rcwd_fpath

        log.i("New valid rcwd: %s", self._rcwd_fpath)

        # Tell the client the new rcwd
        rcwd_spath_str = str(self._rcwd_spath)
        rcwd_spath_str = "" if rcwd_spath_str == "." else rcwd_spath_str

        log.d("RCWD for the client: %s", rcwd_spath_str)

        print(f"[{self._client.tag}] rcd '{self._rcwd_fpath}'")

        return create_success_response(rcwd_spath_str)

    @expose
    @trace_api
    @try_or_command_failed_response
    @check_sharing_service_owner
    @ensure_d_sharing
    def rpwd(self) -> Response:
        client_endpoint = pyro_client_endpoint()
        log.i("<< RPWD %s", str(client_endpoint))

        rcwd_spath_str = str(self._rcwd_spath)
        rcwd_spath_str = "" if rcwd_spath_str == "." else rcwd_spath_str

        print(f"[{self._client.tag}] rpwd'")

        return create_success_response(rcwd_spath_str)

    @expose
    @trace_api
    @try_or_command_failed_response
    @check_sharing_service_owner
    @ensure_d_sharing
    def rls(self, *,
            path: str = None, sort_by: List[str] = None,
            reverse: bool = False, hidden: bool = False) -> Response:

        path = path or "."
        sort_by = sort_by or ["name"]
        reverse = reverse or False

        if not is_str(path) or not is_list(sort_by) or not is_bool(reverse):
            return self._err_resp(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RLS %s %s%s [%s]",
              path, sort_by,
              " | reverse " if reverse else "",
              str(client_endpoint))

        # Compute real path and check path legality
        real_path = self._real_path_from_rcwd(path)

        if not self._is_real_path_allowed(real_path):
            log.e("Path is invalid (out of sharing domain)")
            return self._err_resp(ServerErrors.INVALID_PATH)

        log.i("Going to ls on %s", real_path)

        ls_result = ls(real_path, sort_by=sort_by, reverse=reverse)
        if ls_result is None:  # Check is None, since might be empty
            return self._err_resp(ServerErrors.COMMAND_EXECUTION_FAILED)

        log.i("RLS response %s", str(ls_result))

        return create_success_response(ls_result)


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_sharing_service_owner
    @ensure_d_sharing
    def rtree(self, *, path: str = None, sort_by: List[str] = None,
              reverse: bool = False, hidden: bool = False,
              max_depth: int = None, ) -> Response:

        path = path or "."
        sort_by = sort_by or ["name"]
        reverse = reverse or False

        if not is_str(path) or not is_list(sort_by) or not is_bool(reverse):
            return self._err_resp(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RTREE %s %s%s [%s]",
              path, sort_by,
              " | reverse " if reverse else "",
              str(client_endpoint))

        # Compute real path and check path legality
        real_path = self._real_path_from_rcwd(path)

        if not self._is_real_path_allowed(real_path):
            log.e("Path is invalid (out of sharing domain)")
            return self._err_resp(ServerErrors.INVALID_PATH)

        log.i("Going to tree on %s", real_path)

        tree_root = tree(real_path, sort_by=sort_by, reverse=reverse, max_depth=max_depth)
        if tree_root is None:  # Check is None, since might be empty
            return self._err_resp(ServerErrors.COMMAND_EXECUTION_FAILED)

        log.i("RTREE response %s", j(tree_root))

        return create_success_response(tree_root)



    @expose
    @trace_api
    @try_or_command_failed_response
    @check_sharing_service_owner
    @check_write_permission
    @ensure_d_sharing
    def rmkdir(self, directory: str) -> Response:
        if not is_str(directory):
            return self._err_resp(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RMKDIR %s [%s]", directory, str(client_endpoint))

        directory_fpath = self._fpath_joining_rcwd_and_spath(directory)
        log.d("User would create directory: %s", directory_fpath)

        # Check if it's inside the sharing domain
        if not self._is_fpath_allowed(directory_fpath):
            return self._err_resp(ServerErrors.INVALID_PATH, q(directory))

        log.i("Going to mkdir on valid path %s", directory_fpath)

        try:
            directory_fpath.mkdir(parents=True)
            print(f"[{self._client.tag}] rmkdir '{directory_fpath}'")
        except PermissionError:
            return self._err_resp(ServerErrors.PERMISSION_DENIED, directory_fpath)
        except FileExistsError:
            return self._err_resp(ServerErrors.DIRECTORY_ALREADY_EXISTS, directory_fpath)
        except OSError as oserr:
            return self._err_resp(os_error_str(oserr), directory_fpath)

        return create_success_response()

    @expose
    @trace_api
    @try_or_command_failed_response
    @check_sharing_service_owner
    @check_write_permission
    @ensure_d_sharing
    def rcp(self, sources: List[str], destination: str) -> Response:
        errors = []

        def handle_errno(errno: int, *subjects):
            errors.append(create_error_of_response(errno, *subjects))

        def handle_cp_exception(exc: Exception, src: FPath, dst: FPath):
            if isinstance(exc, PermissionError):
                errors.append(create_error_of_response(ServerErrors.CP_PERMISSION_DENIED,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, FileNotFoundError):
                errors.append(create_error_of_response(ServerErrors.CP_NOT_EXISTS,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, OSError):
                errors.append(create_error_of_response(ServerErrors.CP_SPECIFIED_ERROR,
                                                       os_error_str(exc), *self._qspathify(src, dst)))
            else:
                errors.append(create_error_of_response(ServerErrors.CP_SPECIFIED_ERROR,
                                                       exc, *self._qspathify(src, dst)))

        resp = self._rmvcp(sources, destination, cp, "CP",
                           errno_callback=handle_errno,
                           exception_callback=handle_cp_exception)
        if resp:
            return resp # e.g. invalid path

        if errors:
            return create_error_response(errors) # e.g. permission denied

        return create_success_response()

    @expose
    @trace_api
    @try_or_command_failed_response
    @check_sharing_service_owner
    @check_write_permission
    @ensure_d_sharing
    def rmv(self, sources: List[str], destination: str) -> Response:
        errors = []

        def handle_errno(errno: int, *subjects):
            errors.append(create_error_of_response(errno, *subjects))

        def handle_mv_exception(exc: Exception, src: FPath, dst: FPath):
            if isinstance(exc, PermissionError):
                errors.append(create_error_of_response(ServerErrors.MV_PERMISSION_DENIED,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, FileNotFoundError):
                errors.append(create_error_of_response(ServerErrors.MV_NOT_EXISTS,
                                                       *self._qspathify(src, dst)))
            elif isinstance(exc, OSError):
                errors.append(create_error_of_response(ServerErrors.MV_SPECIFIED_ERROR,
                                                       os_error_str(exc), *self._qspathify(src, dst)))
            else:
                errors.append(create_error_of_response(ServerErrors.MV_SPECIFIED_ERROR,
                                                       exc, *self._qspathify(src, dst)))

        resp = self._rmvcp(sources, destination, mv, "MV",
                           errno_callback=handle_errno,
                           exception_callback=handle_mv_exception)

        if resp:
            return resp  # e.g. invalid path

        if errors:
            return create_error_response(errors)  # e.g. permission denied

        return create_success_response()

    def _rmvcp(self,
               sources: List[str], destination: str,
               primitive: Callable[[Path, Path], bool],
               primitive_name: str = "MV/CP",
               errno_callback: Callable[..., None] = None,
               exception_callback: Callable[[Exception, FPath, FPath], None] = None) -> Optional[Response]:

        # mv <src>... <dest>
        #
        # A1  At least two parameters
        # A2  If a <src> doesn't exist => IGNORES it
        #
        # 2 args:
        # B1  If <dest> exists
        #     B1.1    If type of <dest> is DIR => put <src> into <dest> anyway
        #
        #     B1.2    If type of <dest> is FILE
        #         B1.2.1  If type of <src> is DIR => ERROR
        #         B1.2.2  If type of <src> is FILE => OVERWRITE
        # B2  If <dest> doesn't exist => preserve type of <src>
        #
        # 3 args:
        # C1  if <dest> exists => must be a dir
        # C2  If <dest> doesn't exist => ERROR


        if not is_valid_list(sources, str) or not is_str(destination):
            return self._err_resp(ServerErrors.INVALID_COMMAND_SYNTAX)

        destination_fpath = self._fpath_joining_rcwd_and_spath(destination)

        if not self._is_fpath_allowed(destination_fpath):
            log.e("Path is invalid (out of sharing domain)")
            return self._err_resp(ServerErrors.INVALID_PATH, q(destination))

        # sources_paths will be checked after, since if we are copy more than
        # a file and only one is invalid we won't throw a global exception

        # C1/C2 check: with 3+ arguments
        if len(sources) >= 2:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not destination_fpath.is_dir():
                log.e("'%s' must be an existing directory", destination_fpath)
                return self._err_resp(ServerErrors.NOT_A_DIRECTORY, destination_fpath)

        errors = []

        client_endpoint = pyro_client_endpoint()

        log.i("<< %s %s %s [%s]",
              primitive_name, sources, destination, str(client_endpoint))

        for source_path in sources:
            source_fpath = self._fpath_joining_rcwd_and_spath(source_path)

            # Path validity check
            if self._is_fpath_allowed(source_fpath):
                try:
                    log.i("%s %s -> %s", primitive_name, source_fpath, destination_fpath)
                    primitive(source_fpath, destination_fpath)
                except Exception as ex:
                    if exception_callback:
                        exception_callback(ex, source_fpath, destination_fpath)
            else:
                log.e("Path is invalid (out of sharing domain)")

                if errno_callback:
                    errno_callback(ServerErrors.INVALID_PATH, q(source_path))

        return None


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_sharing_service_owner
    @check_write_permission
    @ensure_d_sharing
    def rrm(self, paths: List[str]) -> Response:
        client_endpoint = pyro_client_endpoint()

        if not is_list(paths) or len(paths) < 1:
            return self._err_resp(ServerErrors.INVALID_COMMAND_SYNTAX)

        log.i("<< RRM %s [%s]", paths, str(client_endpoint))

        errors = []

        def handle_rm_error(err):
            log.i("RM error: %s", err)
            errors.append(str(err))


        for path in paths:
            rm_path = self._real_path_from_rcwd(path)

            log.i("RM on path: %s", rm_path)

            if not self._is_real_path_allowed(rm_path):
                log.e("Path is invalid (out of sharing domain)")
                errors.append(ServerErrors.INVALID_PATH)
                continue

            # Do not allow to remove the entire sharing
            try:
                if os.path.samefile(self._sharing.path, rm_path):
                    log.e("Cannot delete the sharing's root directory")
                    errors.append(ServerErrors.INVALID_PATH)
                    continue
            except:
                # Maybe the file does not exists, don't worry and pass
                # it to rm that will handle it properly with error_callback
                # and report the error description
                pass
            finally:
                rm(rm_path, error_callback=handle_rm_error)

        # Eventually put errors in the response
        response_data = None

        if errors:
            log.e("Reporting %d errors to the es", len(errors))

            if len(paths) == 1:
                # Only a request with a fail: global fail
                return self._err_resp(errors[0])

            response_data = {"errors": errors}

        return create_success_response(response_data)

    @expose
    @trace_api
    @try_or_command_failed_response
    @check_sharing_service_owner
    # NO  @ensure_d_sharing, allowed for files too
    def get(self, paths: List[str], check: bool = False) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i("<< GET %s [%s]", str(paths), str(client_endpoint))

        if not paths:
            paths = ["."]


        # Compute real path for each name
        real_paths: List[Tuple[str, str]] = []
        for f in paths:
            if f == ".":
                # get the sharing, wrapped into a folder with this sharing name
                real_paths.append((self._current_real_path(), self._sharing.name))  # no prefixes
            else:
                f = f.replace("*", ".")  # glob
                real_paths.append((self._real_path_from_rcwd(f), ""))  # no prefixes

        normalized_paths = sorted(real_paths, reverse=True)
        log.i("Normalized paths:\n%s", normalized_paths)

        get = GetService(
            normalized_paths,
            check=check,
            sharing=self._sharing,
            sharing_rcwd=self._rcwd,
            client=self._client,
            end_callback=lambda getserv: getserv.unpublish()
        )

        uid = get.publish()

        return create_success_response({
            "uid": uid,
        })


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_sharing_service_owner
    @ensure_d_sharing
    def put(self, check: bool = False) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i("<< PUT [%s]", str(client_endpoint))

        if self._sharing.ftype == FTYPE_FILE:
            # Cannot put within a file
            log.e("Cannot put within a file sharing")
            return create_error_response(ServerErrors.NOT_ALLOWED)

        put = PutService(
            check=check,
            sharing=self._sharing,
            sharing_rcwd=self._rcwd,
            client=self._client,
            end_callback=lambda putserv: putserv.unpublish()
        )

        uid = put.publish()

        return create_success_response({
            "uid": uid,
        })

    @expose
    @trace_api
    @check_sharing_service_owner
    def close(self):
        client_endpoint = pyro_client_endpoint()

        log.i("<< CLOSE [%s]", str(client_endpoint))
        log.i("Deallocating es resources...")

        # TODO remove gets/puts

        self._notify_service_end()
