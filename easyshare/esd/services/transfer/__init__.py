import threading
from abc import ABC
from typing import Callable

from Pyro5.server import expose

from easyshare.esd.daemons.transfer import get_transfer_daemon
from easyshare.esd.services import BaseClientSharingService, BaseClientService, check_service_owner

from easyshare.esd.common import ClientContext, Sharing
from easyshare.logging import get_logger
from easyshare.protocol.protocol import ITransferService, TransferOutcomes
from easyshare.sockets import SocketTcpIn
from easyshare.utils.pyro.server import trace_api, try_or_command_failed_response

log = get_logger(__name__)

# =============================================
# ============= TRANSFER SERVICE ==============
# =============================================
from easyshare.protocol.protocol import create_success_response, Response


class TransferService(ITransferService, BaseClientSharingService, ABC):

    # Close the connection on the transfer port if none connects within this timeout
    TRANSFER_ACCEPT_CONNECTION_TIMEOUT = 10

    BUFFER_SIZE = 4096

    def __init__(self,
                 port: int,
                 sharing: Sharing,
                 sharing_rcwd,
                 client: ClientContext,
                 end_callback: Callable[[BaseClientService], None]):
        super().__init__(sharing, sharing_rcwd, client, end_callback)
        log.d("Creating a transfer service")
        get_transfer_daemon().add_callback(self._handle_new_connection)
        self._outcome_sync = threading.Semaphore(0)
        self._outcome = None

    @expose
    @trace_api
    @check_service_owner
    @try_or_command_failed_response
    def outcome(self) -> Response:
        log.d("Blocking and waiting for outcome...")

        self._outcome_sync.acquire()
        outcome = self._outcome
        self._outcome_sync.release()

        log.i("Transfer outcome: %d", outcome)

        self._notify_service_end()

        return create_success_response(outcome)


    def _handle_new_connection(self, sock: SocketTcpIn) -> bool:
        if not sock:
            self._finish(TransferOutcomes.CONNECTION_ESTABLISHMENT_ERROR)
            return False # not handled

        if sock.remote_endpoint()[0] != self._client.endpoint[0]:
            log.e("Unexpected es connected: forbidden")
            return False # not handled

        log.i("Received connection from valid endpoint %s", sock.remote_endpoint())
        self._transfer_sock = sock

        # Finally execute the transfer logic
        th = threading.Thread(target=self._run, daemon=True)
        th.start()

        return True # handled


    def _success(self):
        self._finish(0)

    def _finish(self, outcome):
        self._outcome = outcome
        self._outcome_sync.release()