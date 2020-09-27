from easyshare.commands.commands import Commands
from easyshare.common import DEFAULT_SERVER_PORT
from easyshare.es.client import Client
from easyshare.utils.net import get_primary_ip
from tests.utils import EsdTest
from easyshare.esd.__main__ import wait_until_start as wait_until_esd_start

esd = EsdTest()

with esd:
    # Wait for server to start
    wait_until_esd_start()

    def test_connect_by_name(): # connect server-name
        client = Client()
        client.execute_command(Commands.CONNECT, esd.server_name)
        assert client.is_connected_to_server()
        client.execute_command(Commands.DISCONNECT)

    def test_connect_by_ip(): # connect 192.168.1.110
        client = Client()
        client.execute_command(Commands.CONNECT, get_primary_ip())
        assert client.is_connected_to_server()
        client.execute_command(Commands.DISCONNECT)

    def test_disconnect():
        client = Client()
        client.execute_command(Commands.CONNECT, esd.server_name)
        assert client.is_connected_to_server()
        client.execute_command(Commands.DISCONNECT)
        assert not client.is_connected_to_server()

    def test_open_by_sharing_name(): # open sharing-name
        client = Client()
        client.execute_command(Commands.OPEN, esd.server_root.name)
        assert client.is_connected_to_sharing()
        client.execute_command(Commands.DISCONNECT)

    def test_open_by_sharing_name_at_server_name():
        client = Client()
        client.execute_command(Commands.OPEN, f"{esd.server_root.name}@{esd.server_name}")
        assert client.is_connected_to_sharing()
        client.execute_command(Commands.DISCONNECT)

    def test_open_by_sharing_name_at_ip():
        client = Client()
        client.execute_command(Commands.OPEN, f"{esd.server_root.name}@{get_primary_ip()}")
        assert client.is_connected_to_sharing()
        client.execute_command(Commands.DISCONNECT)

    def test_open_by_sharing_name_at_ip_port():
        client = Client()
        client.execute_command(Commands.OPEN, f"{esd.server_root.name}@{get_primary_ip():{DEFAULT_SERVER_PORT}}")
        assert client.is_connected_to_sharing()
        client.execute_command(Commands.DISCONNECT)
