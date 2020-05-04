import os
from typing import List, Optional, Callable, Union

from Pyro5.api import expose

from easyshare.logging import get_logger
from easyshare.protocol.errors import ServerErrors
from easyshare.protocol.fileinfo import FileInfo
from easyshare.protocol.pyro import ISharingService
from easyshare.protocol.response import Response, create_error_response, create_success_response
from easyshare.server.client import ClientContext
from easyshare.server.clientservice import ClientService, check_service_owner
from easyshare.server.common import try_or_command_failed_response
from easyshare.server.sharing import Sharing
from easyshare.utils.json import json_to_pretty_str
from easyshare.utils.os import ls, is_relpath, relpath, tree, cp, mv, rm
from easyshare.utils.pyro import pyro_client_endpoint, trace_api
from easyshare.utils.str import unprefix
from easyshare.utils.types import is_str, is_list, is_bool, is_int

log = get_logger(__name__)


def check_write_permission(api):
    def check_write_permission_wrapper(service: 'SharingService', *vargs, **kwargs):
        if service._sharing.read_only:
            log.e("Forbidden: write action on read only sharing by [%s]", pyro_client_endpoint())
            return service._create_sharing_error_response(ServerErrors.NOT_WRITABLE)
        return api(service, *vargs, **kwargs)

    check_write_permission_wrapper.__name__ = api.__name__

    return check_write_permission_wrapper


class SharingService(ISharingService, ClientService):

    def get(self, files: List[str]) -> Response:
        pass

    def get_next_info(self, transaction) -> Response:
        pass

    def put(self) -> Response:
        pass

    def put_next_info(self, transaction, info: FileInfo) -> Response:
        pass

    def __init__(self, sharing: Sharing, *,
                 client: ClientContext,
                 end_callback: Callable[[ClientService], None]):
        super().__init__(client, end_callback)
        self._sharing = sharing
        self._rcwd = ""

    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    def rls(self, *,
            path: str = None, sort_by: List[str] = None,
            reverse: bool = False, hidden: bool = False) -> Response:

        path = path or "."
        sort_by = sort_by or ["name"]
        reverse = reverse or False

        if not is_str(path) or not is_list(sort_by) or not is_bool(reverse):
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RLS %s %s%s [%s]",
              path, sort_by,
              " | reverse " if reverse else "",
              str(client_endpoint))

        # Compute real path and check path legality
        real_path = self._real_path_from_rcwd(path)

        if not self._is_real_path_allowed(real_path):
            log.e("Path is invalid (out of sharing domain)")
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        log.i("Going to ls on %s", real_path)

        ls_result = ls(real_path, sort_by=sort_by, reverse=reverse)
        if ls_result is None:  # Check is None, since might be empty
            return self._create_sharing_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

        log.i("RLS response %s", str(ls_result))

        return create_success_response(ls_result)


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    def rtree(self, *, path: str = None, sort_by: List[str] = None,
              reverse: bool = False, hidden: bool = False,
              max_depth: int = None, ) -> Response:

        path = path or "."
        sort_by = sort_by or ["name"]
        reverse = reverse or False

        if not is_str(path) or not is_list(sort_by) or not is_bool(reverse):
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RTREE %s %s%s [%s]",
              path, sort_by,
              " | reverse " if reverse else "",
              str(client_endpoint))

        # Compute real path and check path legality
        real_path = self._real_path_from_rcwd(path)

        if not self._is_real_path_allowed(real_path):
            log.e("Path is invalid (out of sharing domain)")
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        log.i("Going to tree on %s", real_path)

        tree_root = tree(real_path, sort_by=sort_by, reverse=reverse, max_depth=max_depth)
        if tree_root is None:  # Check is None, since might be empty
            return self._create_sharing_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

        log.i("RTREE response %s", json_to_pretty_str(tree_root))

        return create_success_response(tree_root)


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    def rpwd(self) -> Response:
        client_endpoint = pyro_client_endpoint()

        log.i("<< RPWD %s", str(client_endpoint))
        return create_success_response(self._rcwd)


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    def rcd(self, path: str) -> Response:
        path = path or "."

        if not is_str(path):
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RCD %s [%s]", path, str(client_endpoint))

        new_real_path = self._real_path_from_rcwd(path)

        if not self._is_real_path_allowed(new_real_path):
            log.e("Path is invalid (out of sharing domain)")
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        if not os.path.isdir(new_real_path):
            log.e("Path does not exists")
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        log.i("New rcwd real path: %s", new_real_path)

        self._rcwd = self._trailing_path_from_root(new_real_path)
        log.i("New rcwd: %s", self._rcwd)

        return create_success_response(self._rcwd)


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    @check_write_permission
    def rmkdir(self, directory: str) -> Response:
        if not is_str(directory):
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        client_endpoint = pyro_client_endpoint()

        log.i("<< RMKDIR %s [%s]", directory, str(client_endpoint))

        real_path = self._real_path_from_rcwd(directory)

        if not self._is_real_path_allowed(real_path):
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        log.i("Going to mkdir on %s", real_path)

        try:
            os.mkdir(real_path)
        except Exception as ex:
            log.exception("mkdir exception")
            return self._create_sharing_error_response(str(ex))

        return create_success_response()

    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    @check_write_permission
    def rcp(self, sources: List[str], destination: str) -> Response:
        return self._rmvcp(sources, destination, cp, "CP")


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    @check_write_permission
    def rmv(self, sources: List[str], destination: str) -> Response:
        return self._rmvcp(sources, destination, mv, "MV")


    def _rmvcp(self, sources: List[str], destination: str,
               primitive: Callable[[str, str], bool],
               primitive_name: str = "MV/CP"):

        if not is_list(sources) or len(sources) < 1 or not is_str(destination):
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

        dest_real_path = self._real_path_from_rcwd(destination)

        if not self._is_real_path_allowed(dest_real_path):
            log.e("Path is invalid (out of sharing domain)")
            return self._create_sharing_error_response(ServerErrors.INVALID_PATH)

        # C1/C2 check: with 3+ arguments
        if len(sources) >= 2:
            # C1  if <dest> exists => must be a dir
            # C2  If <dest> doesn't exist => ERROR
            # => must be a valid dir
            if not os.path.isdir(dest_real_path):
                log.e("'%s' must be an existing directory", dest_real_path)
                return self._create_sharing_error_response(ServerErrors.COMMAND_EXECUTION_FAILED)

        errors = []

        client_endpoint = pyro_client_endpoint()

        log.i("<< %s %s %s [%s]",
              primitive_name, sources, destination, str(client_endpoint))

        for src in sources:

            src_real_path = self._real_path_from_rcwd(src)

            # Path validity check
            if not self._is_real_path_allowed(src_real_path):
                log.e("Path is invalid (out of sharing domain)")
                errors.append(ServerErrors.INVALID_PATH)
                continue

            try:
                log.i("%s %s -> %s", primitive_name, src_real_path, dest_real_path)
                primitive(src_real_path, dest_real_path)
            except Exception as ex:
                errors.append(str(ex))

        # Eventually report errors
        response_data = None

        if errors:
            log.e("Reporting %d errors to the client", len(errors))

            if len(sources) == 1:
                # Only a request with a fail: global fail
                return self._create_sharing_error_response(errors[0])

            response_data = {"errors": errors}

        return create_success_response(response_data)


    @expose
    @trace_api
    @try_or_command_failed_response
    @check_service_owner
    @check_write_permission
    def rrm(self, paths: List[str]) -> Response:
        client_endpoint = pyro_client_endpoint()

        if not is_list(paths) or len(paths) < 1:
            return self._create_sharing_error_response(ServerErrors.INVALID_COMMAND_SYNTAX)

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
            log.e("Reporting %d errors to the client", len(errors))

            if len(paths) == 1:
                # Only a request with a fail: global fail
                return self._create_sharing_error_response(errors[0])

            response_data = {"errors": errors}

        return create_success_response(response_data)


    @expose
    @trace_api
    @check_service_owner
    def close(self):
        client_endpoint = pyro_client_endpoint()

        log.i("<< CLOSE [%s]", str(client_endpoint))
        log.i("Deallocating client resources...")

        self._notify_service_end()

        # CHECK CLIENT


        # Remove any pending transaction
        # for get_trans_id in client.gets:
        #     # self._end_get_transaction(get_trans_id, client, abort=True)
        #     if get_trans_id in self.gets:
        #         log.i("Removing GET transaction = %s", get_trans_id)
        #         self.gets.pop(get_trans_id).abort()
        #
        # # Remove from clients
        # log.i("Removing %s from clients", client)
        #
        # del self.clients[client_endpoint]
        # log.i("Client connection closed gracefully")
        #
        # log.i("# clients = %d", len(self.clients))
        # log.i("# gets = %d", len(self.gets))

        # self.unpublish()

    def _current_real_path(self):
        return self._real_path_from_rcwd("")

    def _real_path_from_rcwd(self, path: str) -> Optional[str]:
        """
        Returns the path of the location composed by the 'path' of the
        sharing the client is currently on and the 'path' itself.
        The method allows:
            * 'path' starting with a leading / (absolute w.r.t the sharing path)
            * 'path' not starting with a leading / (relative w.r.t the rpwd)

        e.g.
            (ABSOLUTE)
            client sharing path =  /home/stefano/Applications
            client rpwd =                                     InsideAFolder
            path                =  /AnApp
                                => /home/stefano/Applications/AnApp

            (RELATIVE)
            client sharing path =  /home/stefano/Applications
            client rpwd =                                     InsideAFolder
            path                =  AnApp
                                => /home/stefano/Applications/InsideAFolder/AnApp

        """

        if is_relpath(path):
            # It refers to a subdirectory starting from the client's current directory
            path = os.path.join(self._rcwd, path)

        # Take the trail part (without leading /)
        trail = relpath(path)

        return os.path.normpath(os.path.join(self._sharing.path, trail))


    def _is_real_path_allowed(self, path: str) -> bool:
        """
        Returns whether the given path is legal for the given client, based
        on the its sharing and rpwd.

        e.g. ALLOWED
            client sharing path = /home/stefano/Applications
            client rpwd         =                            AnApp
            path                = /home/stefano/Applications/AnApp/AFile.mp4

        e.g. NOT ALLOWED
            client sharing path = /home/stefano/Applications
            client rpwd         =                            AnApp
            path                = /home/stefano/Applications/AnotherApp/AFile.mp4

            client sharing path = /home/stefano/Applications
            client rpwd         =                           AnApp
            path                = /tmp/afile.mp4

        :param path: the path to check
        :param client: the client
        :return: whether the path is allowed for the client
        """

        normalized_path = os.path.normpath(path)

        try:
            common_path = os.path.commonpath([normalized_path, self._sharing.path])
            log.d("Common path between '%s' and '%s' = '%s'",
                  normalized_path, self._sharing.path, common_path)

            return self._sharing.path == common_path
        except:
            return False

    @staticmethod
    def _trailing_path(prefix: str, full: str) -> Optional[str]:
        """
        Returns the trailing part of the path 'full' by stripping the path 'prefix'.
        The path is relative w.r.t the root of the sharing path.
        e.g.
            prefix                = /home/stefano/Applications
            full                  = /home/stefano/Applications/AnApp/afile.mp4
                                  =>                           AnApp/afile.mp4
        """

        if not full or not prefix:
            return None

        if not full.startswith(prefix):
            return None

        return relpath(unprefix(full, prefix))

    def _trailing_path_from_root(self, path: str) -> Optional[str]:
        """
        Returns the trailing part of the 'path' by stripping the path of the
        sharing from the string's beginning.
        The path is relative w.r.t the root of the sharing path.
        e.g.
            sharing path        = /home/stefano/Applications
            path                = /home/stefano/Applications/AnApp/afile.mp4
                                =>                           AnApp/afile.mp4
        """
        return self._trailing_path(self._sharing.path, path)


    def _trailing_path_from_rcwd(self, path: str) -> Optional[str]:
        """
        Returns the trailing part of the 'path' by stripping the path of the
        sharing from the string's beginning.
        The path is relative w.r.t the rpwd of the sharing path the client
        is currently on.
        e.g.
            client sharing path = /home/stefano/Applications
            client rpwd         =                            AnApp
            (client path        = /home/stefano/Applications/AnApp          )
            path                = /home/stefano/Applications/AnApp/afile.mp4
                                =>                                 afile.mp4
        """
        return self._trailing_path(self._current_real_path(), path)


    def _create_sharing_error_response(self, err: Union[int, str]):
        if is_int(err):
            return create_error_response(err)

        if is_str(err):
            safe_err = err.replace(self._sharing.path, "")
            return create_error_response(safe_err)

        return create_error_response()