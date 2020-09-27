import tempfile

from easyshare.commands.commands import Commands
from easyshare.es.client import Client
from easyshare.es.errors import ClientErrors

from tests.utils import tmpfile, tmpdir

client = Client()


def test_pwd():
    pass

def test_ls():
    pass

def test_tree():
    pass

def test_find():
    pass

def test_du():
    pass

def test_mkdir():
    with tempfile.TemporaryDirectory() as tmp:
        d = tmpdir(tmp)

        client.execute_command(Commands.LOCAL_CREATE_DIRECTORY, str(d))
        assert d.exists()

def test_rm_single():
    with tempfile.TemporaryDirectory() as tmp:
        f1 = tmpfile(tmp)

        client.execute_command(Commands.LOCAL_REMOVE, str(f1))
        assert not f1.exists()

def test_rm_nested():
    with tempfile.TemporaryDirectory() as tmp:
        d1 = tmpdir(tmp)
        f1 = tmpfile(d1)

        client.execute_command(Commands.LOCAL_REMOVE, str(d1))
        assert not d1.exists()
        assert not f1.exists()

def test_rm_multiple():
    with tempfile.TemporaryDirectory() as tmp:
        f1 = tmpfile(tmp)

        d1 = tmpdir(tmp)
        f2 = tmpfile(d1)
        f3 = tmpfile(d1)

        client.execute_command(Commands.LOCAL_REMOVE, f"{f1} {d1}")
        assert not d1.exists()
        assert not f1.exists()
        assert not f2.exists()
        assert not f3.exists()



def _test_mvcp_rename(move: bool):
    cmd = Commands.LOCAL_MOVE if move else Commands.LOCAL_COPY

    with tempfile.TemporaryDirectory() as tmp:
        f1 = tmpfile(tmp)
        f2 = tmpfile(tmp, create=False)
        client.execute_command(cmd, f"{f1} {f2}")

        if move:
            assert not f1.exists()
        assert f2.exists()

def test_mv_rename():
    _test_mvcp_rename(move=True)

def test_cp_rename():
    _test_mvcp_rename(move=False)

def _test_mvcp_file_into_dir(move: bool):
    cmd = Commands.LOCAL_MOVE if move else Commands.LOCAL_COPY

    with tempfile.TemporaryDirectory() as tmp:
        d1 = tmpdir(tmp)
        f1 = tmpfile(tmp)

        client.execute_command(cmd, f"{f1} {d1}")
        if move:
            assert not f1.exists()
        assert (d1 / f1.name).exists()

def test_mv_file_into_dir():
    _test_mvcp_file_into_dir(move=True)

def test_cp_file_into_dir():
    _test_mvcp_file_into_dir(move=False)

def _test_mvcp_dir_into_file(move: bool): # illegal
    cmd = Commands.LOCAL_MOVE if move else Commands.LOCAL_COPY

    with tempfile.TemporaryDirectory() as tmp:
        d1 = tmpdir(tmp)
        f1 = tmpfile(tmp)

        try:
            client.execute_command(cmd, f"{d1} {f1}")
            assert False
        except:
            pass

def test_mvcp_dir_into_file():
    _test_mvcp_dir_into_file(move=True)

def test_cp_dir_into_file():
    _test_mvcp_dir_into_file(move=False)

def _test_mvcp_multiple_file_into_dir(move: bool):
    cmd = Commands.LOCAL_MOVE if move else Commands.LOCAL_COPY

    with tempfile.TemporaryDirectory() as tmp:
        d1 = tmpdir(tmp)
        f1 = tmpfile(tmp)
        f2 = tmpfile(tmp)

        client.execute_command(cmd, f"{f1} {f2} {d1}")
        if move:
            assert not f1.exists()
            assert not f2.exists()
        assert (d1 / f1.name).exists()
        assert (d1 / f2.name).exists()

def test_mv_multiple_file_into_dir():
    _test_mvcp_multiple_file_into_dir(move=True)

def test_cp_multiple_file_into_dir():
    _test_mvcp_multiple_file_into_dir(move=False)

def _test_mvcp_multiple_file_into_file(move: bool): # illegal
    cmd = Commands.LOCAL_MOVE if move else Commands.LOCAL_COPY

    with tempfile.TemporaryDirectory() as tmp:
        f0 = tmpfile(tmp)
        f1 = tmpfile(tmp)
        f2 = tmpfile(tmp)

        ret = client.execute_command(cmd, f"{f1} {f2} {f0}")
        assert ret != ClientErrors.SUCCESS

def test_mv_multiple_file_into_file():
    _test_mvcp_multiple_file_into_file(move=True)

def test_cp_multiple_file_into_file():
    _test_mvcp_multiple_file_into_file(move=False)

def _test_mvcp_multiple_file_into_nothing(move: bool): # illegal
    cmd = Commands.LOCAL_MOVE if move else Commands.LOCAL_COPY

    with tempfile.TemporaryDirectory() as tmp:
        d0 = tmpdir(tmp, create=False)
        f1 = tmpfile(tmp)
        f2 = tmpfile(tmp)

        ret = client.execute_command(cmd, f"{f1} {f2} {d0}")
        assert ret != ClientErrors.SUCCESS

def test_mv_multiple_file_into_nothing():
    _test_mvcp_multiple_file_into_nothing(move=True)

def test_cp_multiple_file_into_nothing():
    _test_mvcp_multiple_file_into_nothing(move=False)

