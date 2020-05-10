import socket
import threading
from abc import ABC
from typing import Callable

from Pyro5.server import expose

from easyshare.logging import get_logger
from easyshare.protocol.errors import TransferOutcomes
from easyshare.protocol.exposed import ITransferService
from easyshare.protocol.response import Response, create_success_response
from easyshare.esd.client import ClientContext
from easyshare.esd.common import try_or_command_failed_response
from easyshare.esd.services.base.service import check_service_owner, ClientService
from easyshare.esd.services.base.sharingservice import ClientSharingService
from easyshare.esd.sharing import Sharing
from easyshare.socket import SocketTcpAcceptor, SocketTcpIn
from easyshare.ssl import get_ssl_context
from easyshare.utils.pyro import trace_api

log = get_logger(__name__)

class TransferService(ITransferService, ClientSharingService, ABC):

    # Close the connection on the transfer port if none connects within this timeout
    TRANSFER_ACCEPT_CONNECTION_TIMEOUT = 10

    BUFFER_SIZE = 4096

    def __init__(self,
                 port: int,
                 sharing: Sharing,
                 sharing_rcwd,
                 client: ClientContext,
                 end_callback: Callable[[ClientService], None]):
        super().__init__(sharing, sharing_rcwd, client, end_callback)
        self._transfer_acceptor_sock = SocketTcpAcceptor(
            port=port,
            ssl_context=get_ssl_context()
        )
        self._transfer_sock = None
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

    def run(self):
        th = threading.Thread(target=self._accept_connection_and_run, daemon=True)
        th.start()

    def _accept_connection_and_run(self):
        if not self._transfer_acceptor_sock:
            log.e("Invalid socket acceptor")
            self._finish(TransferOutcomes.CONNECTION_ESTABLISHMENT_ERROR)
            return

        log.d("Waiting for es connection")

        # Wait for the es connection
        self._accept_connection()

        if not self._transfer_sock:
            self._finish(TransferOutcomes.CONNECTION_ESTABLISHMENT_ERROR)
            return

        # Finally execute the transfer logic
        self._run()

        if self._transfer_sock:
            # Paranoid check
            self._transfer_sock.close()


    def _accept_connection(self):
        try:
            while not self._transfer_sock:
                log.i("Waiting for es connection...")

                transfer_sock: SocketTcpIn = self._transfer_acceptor_sock.accept(
                    TransferService.TRANSFER_ACCEPT_CONNECTION_TIMEOUT
                )

                if transfer_sock.remote_endpoint()[0] != self._client.endpoint[0]:
                    log.e("Unexpected es connected: forbidden")
                    transfer_sock.close()
                    continue

                log.i("Received connection from valid es %s", transfer_sock.remote_endpoint())
                self._transfer_sock = transfer_sock

        except socket.timeout:
            log.w("No connection received within %ds; closing service",
                  TransferService.TRANSFER_ACCEPT_CONNECTION_TIMEOUT)
            self._finish(TransferOutcomes.CONNECTION_ESTABLISHMENT_ERROR)
        finally:
            # Close the acceptor anyway
            self._transfer_acceptor_sock.close()

            # DO not self._notify_service_end()
            # wait for outcome() call before unregister from the daemon

    def _success(self):
        self._finish(0)

    def _finish(self, outcome):
        self._outcome = outcome
        self._outcome_sync.release()