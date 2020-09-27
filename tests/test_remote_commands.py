from easyshare.commands.commands import Commands
from easyshare.es.errors import ClientErrors
from easyshare.utils.rand import randstring
from tests.utils import EsdTest, tmpfile, tmpdir, EsConnectionTest
from easyshare.esd.__main__ import wait_until_start as wait_until_esd_start

esd = EsdTest()

def test_setup():
    esd.__enter__()
    wait_until_esd_start()

def test_rpwd():
    pass

def test_rls():
    pass

def test_rtree():
    pass

def test_rfind():
    pass

def test_rdu():
    pass

def test_rmkdir():
    with EsConnectionTest(esd.sharing_root.name) as client:
        r = randstring()
        client.execute_command(Commands.REMOTE_CREATE_DIRECTORY, r)
        assert (esd.sharing_root / r).exists()
        client.execute_command(Commands.REMOTE_REMOVE, r)

def test_rrm_single():
    with EsConnectionTest(esd.sharing_root.name) as client:
        f = tmpfile(esd.sharing_root)
        client.execute_command(Commands.REMOTE_REMOVE, f.name)
        assert not f.exists()


def test_rrm_nested():
    with EsConnectionTest(esd.sharing_root.name) as client:
        d1 = tmpdir(esd.sharing_root)
        f1 = tmpfile(d1)

        client.execute_command(Commands.REMOTE_REMOVE, d1.name)
        assert not d1.exists()
        assert not f1.exists()


def test_rrm_multiple():
    with EsConnectionTest(esd.sharing_root.name) as client:
        f1 = tmpfile(esd.sharing_root)

        d1 = tmpdir(esd.sharing_root)
        f2 = tmpfile(d1)
        f3 = tmpfile(d1)

        client.execute_command(Commands.REMOTE_REMOVE, f"{f1.name} {d1.name}")
        assert not d1.exists()
        assert not f1.exists()
        assert not f2.exists()
        assert not f3.exists()



def _test_rmvcp_rename(move: bool):
    with EsConnectionTest(esd.sharing_root.name) as client:
        cmd = Commands.REMOTE_MOVE if move else Commands.REMOTE_COPY

        f1 = tmpfile(esd.sharing_root)
        f2 = tmpfile(esd.sharing_root, create=False)
        client.execute_command(cmd, f"{f1.name} {f2.name}")

        if move:
            assert not f1.exists()
        assert f2.exists()


def test_rmv_rename():
    _test_rmvcp_rename(move=True)

def test_rcp_rename():
    _test_rmvcp_rename(move=False)

def _test_rmvcp_file_into_dir(move: bool):
    with EsConnectionTest(esd.sharing_root.name) as client:
        cmd = Commands.REMOTE_MOVE if move else Commands.REMOTE_COPY

        d1 = tmpdir(esd.sharing_root)
        f1 = tmpfile(esd.sharing_root)

        client.execute_command(cmd, f"{f1.name} {d1.name}")
        if move:
            assert not f1.exists()
        assert (d1 / f1.name).exists()


def test_rmv_file_into_dir():
    _test_rmvcp_file_into_dir(move=True)

def test_rcp_file_into_dir():
    _test_rmvcp_file_into_dir(move=False)

def _test_rmvcp_dir_into_file(move: bool): # illegal
    with EsConnectionTest(esd.sharing_root.name) as client:
        cmd = Commands.REMOTE_MOVE if move else Commands.REMOTE_COPY

        d1 = tmpdir(esd.sharing_root)
        f1 = tmpfile(esd.sharing_root)

        ret = client.execute_command(cmd, f"{d1.name} {f1.name}")
        print(f"ret = {ret}")
        assert ret != ClientErrors.SUCCESS


def test_rmvcp_dir_into_file():
    _test_rmvcp_dir_into_file(move=True)

def test_rcp_dir_into_file():
    _test_rmvcp_dir_into_file(move=False)

def _test_rmvcp_multiple_file_into_dir(move: bool):
    with EsConnectionTest(esd.sharing_root.name) as client:
        cmd = Commands.REMOTE_MOVE if move else Commands.REMOTE_COPY

        d1 = tmpdir(esd.sharing_root)
        f1 = tmpfile(esd.sharing_root)
        f2 = tmpfile(esd.sharing_root)

        client.execute_command(cmd, f"{f1.name} {f2.name} {d1.name}")
        if move:
            assert not f1.exists()
            assert not f2.exists()
        assert (d1 / f1.name).exists()
        assert (d1 / f2.name).exists()

def test_rmv_multiple_file_into_dir():
    _test_rmvcp_multiple_file_into_dir(move=True)

def test_rcp_multiple_file_into_dir():
    _test_rmvcp_multiple_file_into_dir(move=False)

def _test_mvcp_multiple_file_into_file(move: bool): # illegal
    with EsConnectionTest(esd.sharing_root.name) as client:
        cmd = Commands.REMOTE_MOVE if move else Commands.REMOTE_COPY

        f0 = tmpfile(esd.sharing_root)
        f1 = tmpfile(esd.sharing_root)
        f2 = tmpfile(esd.sharing_root)

        try:
            client.execute_command(cmd, f"{f1.name} {f2.name} {f0.name}")
            assert False
        except:
            pass


def test_mv_multiple_file_into_file():
    _test_mvcp_multiple_file_into_file(move=True)

def test_cp_multiple_file_into_file():
    _test_mvcp_multiple_file_into_file(move=False)

def _test_mvcp_multiple_file_into_nothing(move: bool): # illegal
    with EsConnectionTest(esd.sharing_root.name) as client:
        cmd = Commands.REMOTE_MOVE if move else Commands.REMOTE_COPY

        d0 = tmpdir(esd.sharing_root, create=False)
        f1 = tmpfile(esd.sharing_root)
        f2 = tmpfile(esd.sharing_root)

        ret = client.execute_command(cmd, f"{f1.name} {f2.name} {d0.name}")
        assert ret != ClientErrors.SUCCESS

def test_mv_multiple_file_into_nothing():
    _test_mvcp_multiple_file_into_nothing(move=True)

def test_cp_multiple_file_into_nothing():
    _test_mvcp_multiple_file_into_nothing(move=False)

def test_teardown():
    esd.__exit__(None, None, None)