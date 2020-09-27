import tempfile
from pathlib import Path

from easyshare.commands.commands import Commands
from tests.utils import EsdTest, EsConnectionTest, tmpfile
from easyshare.esd.__main__ import wait_until_start as wait_until_esd_start

esd = EsdTest()

def test_setup():
    esd.__enter__()
    wait_until_esd_start()


def test_get_file():
    with tempfile.TemporaryDirectory() as local_tmp:

        conn = EsConnectionTest(esd.server_root.name, local_tmp)
        client = conn.enter()

        f = tmpfile(esd.server_root)
        assert not (Path(local_tmp) / f.name).exists()

        client.execute_command(Commands.GET, f.name)

        assert (Path(local_tmp) / f.name).exists()

        conn.exit()


def test_teardown():
    esd.__exit__(None, None, None)