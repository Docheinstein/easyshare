import threading
from abc import ABC, abstractmethod
from typing import Callable

from Pyro5.server import expose

from easyshare.esd.daemons.transfer import get_transfer_daemon
from easyshare.esd.services import BaseClientSharingService, BaseClientService, check_sharing_service_owner, FPath

from easyshare.esd.common import ClientContext, Sharing
from easyshare.logging import get_logger
from easyshare.protocol.services import ITransferService
from easyshare.protocol.responses import TransferOutcomes, create_success_response, Response, ResponseError
from easyshare.sockets import SocketTcpIn
from easyshare.utils.pyro.server import trace_api, try_or_command_failed_response

log = get_logger(__name__)


# =============================================
# ============= TRANSFER SERVICE ==============
# =============================================


class TransferService(ITransferService, BaseClientSharingService, ABC):
    """
    Base implementation of 'ITransferService' interface that will be published with Pyro.
    Defines the common stuff for a single execution of transfer (get/put) command.
    """
    def __init__(self,
                 sharing: Sharing,
                 sharing_rcwd: FPath,
                 client: ClientContext,
                 conn_callback: Callable[['BaseClientService'], None],
                 end_callback: Callable[[BaseClientService], None]):
        super().__init__(sharing, sharing_rcwd, client, conn_callback, end_callback)
        log.d("Creating a transfer service")
        get_transfer_daemon().add_callback(self._handle_new_connection)
        self._outcome_sync = threading.Semaphore(0)
        self._outcome = None
        self._errors = []

    @expose
    @trace_api
    @check_sharing_service_owner
    @try_or_command_failed_response
    def outcome(self) -> Response:
        log.d("Blocking and waiting for outcome...")

        self._outcome_sync.acquire()
        outcome = self._outcome
        self._outcome_sync.release()

        log.i("Transfer outcome: %d", outcome)

        self._notify_service_end()

        # It's always a success response, but eventually will have errors
        # (e.g. a transfer is failed (invalid path, ...) but the transaction is ok)

        if not self._errors:
            return create_success_response({"outcome": outcome})

        return create_success_response({
            "outcome": outcome,
            "errors": self._errors
        })

    @abstractmethod
    def _run(self):
        """ Subclasses should override this for implement the real transfer logic """
        pass

    def _handle_new_connection(self, sock: SocketTcpIn) -> bool:
        """
        Handles a new socket connection;
        if it is valid, invoke the _run of the subclass .
        """
        if not sock:
            self._finish(TransferOutcomes.CONNECTION_ESTABLISHMENT_ERROR)
            return False # not handled - eventually will be closed

        if sock.remote_endpoint()[0] != self.client.endpoint[0]:
            log.e("Unexpected client connected: forbidden")
            return False # not handled - eventually will be closed

        log.i("Received connection from valid endpoint %s", sock.remote_endpoint())
        self._transfer_sock = sock

        # Finally execute the transfer logic
        th = threading.Thread(target=self._run, daemon=True)
        th.start()

        return True # handled

    def _success(self):
        """
        Sets the outcome to 0 and release the semaphore,
        so that who is waiting will be notified
        """
        self._finish(0)

    def _finish(self, outcome):
        """
        Sets the outcome and release the semaphore,
        so that who is waiting will be notified
        """
        self._outcome = outcome
        self._outcome_sync.release()

    def _add_error(self, err: ResponseError):
        self._errors.append(err)