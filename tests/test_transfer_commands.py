import os
import tempfile
from pathlib import Path
from random import randint

from easyshare.commands.commands import Commands
from tests.utils import EsdTest, EsConnectionTest, tmpfile, tmpdir
from easyshare.esd.__main__ import wait_until_start as wait_until_esd_start

K = 2 << 10
M = 2 << 20
esd = EsdTest()

def _hierarchy(parent):
    """
    f0
    d0
        f1
        d1
            dd1
        d2
            ff1
            ff2
    """
    f0 = tmpdir(parent, name="f0")

    d0 = tmpdir(parent, name="d0")
    f1 = tmpfile(d0, name="f1", size=randint(0, 1 * M))
    d1 = tmpdir (d0, name="d1")
    d2 = tmpdir (d0, name="d2")

    dd1 = tmpdir (d1, name="dd1")
    ff1 = tmpfile(d2, name="ff1", size=randint(0, 2 * M))
    ff2 = tmpfile(d2, name="ff2", size=randint(0, 4 * M))
    return d0

def _check_hierarchy(hierarchy_root):
    assert Path(hierarchy_root).exists()

    assert sorted(os.listdir(hierarchy_root)) == sorted(["d0", "f0"])
    assert sorted(os.listdir(os.path.join(hierarchy_root, "d0"))) == sorted(["d1", "d2", "f1"])
    assert sorted(os.listdir(os.path.join(hierarchy_root, "d0", "d1"))) == sorted(["dd1"])
    assert sorted(os.listdir(os.path.join(hierarchy_root, "d0", "d2"))) == sorted(["ff1", "ff2"])

def test_setup():
    esd.__enter__()
    wait_until_esd_start()

    _hierarchy(esd.sharing_root)


def test_get_file():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get f0

    ===========================
    ========== BEFORE =========
    ===========================

    --------- LOCAL -----------

    client-XXXX

    --------- REMOTE -----------

    dir-YYYY (sharing name: dir-YYYY)
    ├── f0
    └── d0
        ├── d1
        │   └── dd1
        ├── d2
        │   ├── ff1
        │   └── ff2
        └── f1

    ===========================
    ======== EXPECTED =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    └── f0
    """
    with tempfile.TemporaryDirectory("client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            client.execute_command(Commands.GET, "f0")
            assert (Path(local_tmp) / "f0").exists()

def test_get_sharing():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get

    ===========================
    ========== BEFORE =========
    ===========================

    --------- LOCAL -----------

    client-XXXX

    --------- REMOTE -----------

    dir-YYYY (sharing name: dir-YYYY)
    ├── f0
    └── d0
        ├── d1
        │   └── dd1
        ├── d2
        │   ├── ff1
        │   └── ff2
        └── f1

    ===========================
    ======== EXPECTED =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
        dir-YYYY
        ├── f0
        └── d0
            ├── d1
            │   └── dd1
            ├── d2
            │   ├── ff1
            │   └── ff2
            └── f1
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            client.execute_command(Commands.GET)
            _check_hierarchy(Path(local_tmp) / esd.sharing_root.name)

def test_get_sharing_content():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get

    ===========================
    ========== BEFORE =========
    ===========================

    --------- LOCAL -----------

    client-XXXX

    --------- REMOTE -----------

    dir-YYYY (sharing name: dir-YYYY)
    ├── f0
    └── d0
        ├── d1
        │   └── dd1
        ├── d2
        │   ├── ff1
        │   └── ff2
        └── f1

    ===========================
    ======== EXPECTED =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    ├── f0
    └── d0
        ├── d1
        │   └── dd1
        ├── d2
        │   ├── ff1
        │   └── ff2
        └── f1
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            client.execute_command(Commands.GET, "*")
            _check_hierarchy(Path(local_tmp))

def test_get_multiple():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get f0 d0/d2/ff1

    ===========================
    ========== BEFORE =========
    ===========================

    --------- LOCAL -----------

    client-XXXX

    --------- REMOTE -----------

    dir-YYYY (sharing name: dir-YYYY)
    ├── f0
    └── d0
        ├── d1
        │   └── dd1
        ├── d2
        │   ├── ff1
        │   └── ff2
        └── f1

    ===========================
    ======== EXPECTED =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    └── f0
    └── ff1
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            client.execute_command(Commands.GET, "f0 d0/d2/ff1")
            assert sorted(os.listdir(local_tmp)) == sorted(["f0", "ff1"])

def test_get_dest_1e_f2f():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get d0/d2/ff1 -d ff1.renamed

    ===========================
    ========== BEFORE =========
    ===========================

    --------- LOCAL -----------

    client-XXXX

    --------- REMOTE -----------

    dir-YYYY (sharing name: dir-YYYY)
    ├── f0
    └── d0
        ├── d1
        │   └── dd1
        ├── d2
        │   ├── ff1
        │   └── ff2
        └── f1

    ===========================
    ======== EXPECTED =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    └── ff1.renamed
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            client.execute_command(Commands.GET, "d0/d2/ff1 -d ff1.renamed")
            assert (Path(local_tmp) / "ff1.renamed").is_file()

def test_get_dest_1e_x2d():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get d0/d2/ff1 -d dx

    ===========================
    ========== BEFORE =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    ├── dx

    --------- REMOTE -----------

    dir-YYYY (sharing name: dir-YYYY)
    ├── f0
    └── d0
        ├── d1
        │   └── dd1
        ├── d2
        │   ├── ff1
        │   └── ff2
        └── f1

    ===========================
    ======== EXPECTED =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    ├── dx
        └── ff1
    """
    # local_tmp = tempfile.mkdtemp(prefix="client-")
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            dx = tmpdir(local_tmp, name="dx")
            client.execute_command(Commands.GET, "d0/d2/ff2 -d dx")
            assert sorted(os.listdir(dx)) == sorted(["ff2"])

def test_get_dest_1e_d2f():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get d0/d2/ff1 -d dx

    ===========================
    ========== BEFORE =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    ├── dx

    --------- REMOTE -----------

    dir-YYYY (sharing name: dir-YYYY)
    ├── f0
    └── d0
        ├── d1
        │   └── dd1
        ├── d2
        │   ├── ff1
        │   └── ff2
        └── f1

    ===========================
    ======== EXPECTED =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    ├── dx
        └── ff1
    """
    # local_tmp = tempfile.mkdtemp(prefix="client-")
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            dx = tmpdir(local_tmp, name="dx")
            client.execute_command(Commands.GET, "d0/d2/ff2 -d dx")
            assert sorted(os.listdir(dx)) == sorted(["ff2"])

def test_get_file_dest_into_dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get d0/d2/ff1 -d dx

    ===========================
    ========== BEFORE =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    ├── dx

    --------- REMOTE -----------

    dir-YYYY (sharing name: dir-YYYY)
    ├── f0
    └── d0
        ├── d1
        │   └── dd1
        ├── d2
        │   ├── ff1
        │   └── ff2
        └── f1

    ===========================
    ======== EXPECTED =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    ├── dx
        └── ff1
    """
    # local_tmp = tempfile.mkdtemp(prefix="client-")
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            dx = tmpdir(local_tmp, name="dx")
            client.execute_command(Commands.GET, "d0/d2/ff2 -d dx")
            assert sorted(os.listdir(dx)) == sorted(["ff2"])

def test_teardown():
    esd.__exit__(None, None, None)