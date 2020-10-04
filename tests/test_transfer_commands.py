import tempfile
from pathlib import Path
from random import randint
from typing import Union, Dict, Callable

from easyshare.commands.commands import Commands
from easyshare.common import VERBOSITY_MAX
from easyshare.es.errors import ClientErrors
from easyshare.es.ui import print_files_info_tree
from easyshare.logging import get_logger
from easyshare.styling import red
from easyshare.utils.json import j
from easyshare.utils.os import tree
from tests.utils import EsdTest, EsConnectionTest, tmpfile, tmpdir
from easyshare.esd.__main__ import wait_until_start as wait_until_esd_start

K = 2 << 10
M = 2 << 20
esd = EsdTest()


def log_client():
    get_logger("easyshare.es.client").set_level(VERBOSITY_MAX)

def check_hierarchy(root: Union[Path, str],
                    hierarchy_or_func: Union[Dict, Callable[[Path], None]]):
    try:
        hierarchy_flat = []

        def flattify(path, children_or_func: Union[Dict, Callable[[Path], None]]):
            nonlocal hierarchy_flat

            if isinstance(children_or_func, dict):
                # children
                for name, content in children_or_func.items():
                    flattify(path / name, content)
            else:
                # func
                hierarchy_flat.append((path, children_or_func))

        flattify(Path(root), hierarchy_or_func)

        for (p, checker) in hierarchy_flat:
            if checker:
                checker(p)
    except AssertionError as ae:
        print(red("Hierarchy START"))
        print_files_info_tree(tree(root))
        print(red("Hierarchy END "))
        raise ae

def assert_dir(directory: Union[Path, str]):
    assert Path(directory).is_dir()


def assert_file(file: Union[Path, str]):
    assert Path(file).is_file()
    assert Path(file).stat().st_size > 0

def assert_success(res):
    assert res == ClientErrors.SUCCESS
    
    
def assert_fail(res):
    assert res != ClientErrors.SUCCESS


def create_test_hierarchy(parent):
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
    f0 = tmpfile(parent, name="f0", size=randint(K, 1 * M))

    d0 = tmpdir(parent, name="d0")
    f1 = tmpfile(d0, name="f1", size=randint(K, 1 * M))
    d1 = tmpdir (d0, name="d1")
    d2 = tmpdir (d0, name="d2")

    dd1 = tmpdir (d1, name="dd1")
    ff1 = tmpfile(d2, name="ff1", size=randint(K, 2 * M))
    ff2 = tmpfile(d2, name="ff2", size=randint(K, 4 * M))
    return d0

TEST_HIERARCHY = {
    "f0": assert_file,
    "d0": {
        "f1": assert_file,
        "d1": {
            "dd1": assert_dir
        },
        "d2": {
            "ff1": assert_file,
            "ff2": assert_file
        }
    }
}

def test_setup():
    esd.__enter__()
    wait_until_esd_start()

    create_test_hierarchy(esd.sharing_root)


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
            assert_success(
                client.execute_command(Commands.GET, "f0")
            )
            check_hierarchy(Path(local_tmp), {
                "f0": assert_file
            })

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
            assert_success(
                client.execute_command(Commands.GET)
            )
            check_hierarchy(Path(local_tmp), {
                esd.sharing_root.name: TEST_HIERARCHY
            })

def test_get_sharing_content():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get *

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
            assert_success(
                client.execute_command(Commands.GET, "*")
            )
            check_hierarchy(Path(local_tmp), TEST_HIERARCHY)

def test_get_sharing_content_multiple(): # illegal
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get * d0

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
    (ERROR)
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            assert_fail(
                client.execute_command(Commands.GET, "* d0")
            )

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
            assert_success(
                client.execute_command(Commands.GET, "f0 d0/d2/ff1")
            )
            
            check_hierarchy(local_tmp, {
                "f0": assert_file,
                "ff1": assert_file
            })

def test_get_dest_1_file2none():
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
    (write file)

    client-XXXX
    └── ff1.renamed
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET, "d0/d2/ff1 -d ff1.renamed")
            )
            check_hierarchy(Path(local_tmp), {"ff1.renamed": assert_file})

def test_get_dest_1_file2file():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > touch ff1.something
    > get d0/d2/ff1 -d ff1.something

    ===========================
    ========== BEFORE =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    ├── ff1.something

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
    (overwrite file)

    client-XXXX
    └── ff1.something
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            tmpfile(local_tmp, name="ff1.something")
            assert_success(
                client.execute_command(Commands.GET, "-y d0/d2/ff1 -d ff1.something")
            )
            check_hierarchy(Path(local_tmp), {"ff1.something": assert_file })

def test_get_dest_1_file2dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir dx
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
    (put file into dir)

    client-XXXX
    ├── dx
        └── f2
    """
    # local_tmp = tempfile.mkdtemp(prefix="client-")
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            dx = tmpdir(local_tmp, name="dx")
            assert_success(
                client.execute_command(Commands.GET, "d0/d2/ff2 -d dx")
            )

            check_hierarchy(local_tmp, {
                dx: {
                    "ff2": assert_file
                }
            })

def test_get_dest_1_dir2none():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get d0/d2 -d d2.renamed

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
    (write dir)

    client-XXXX
    ├── d2.renamed
        ├── ff1
        └── ff2
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET, "d0/d2 -d d2.renamed")
            )

            check_hierarchy(Path(local_tmp), {
                "d2.renamed": {
                    "ff1": assert_file,
                    "ff2": assert_file
                }
            })

def test_get_dest_1_dir2file(): # illegal
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > touch f2.exists
    > get d0/d2 -d f2.exists

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
    (ERROR)
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            tmpfile(local_tmp, name="f2.exists")

            assert_fail(
                client.execute_command(Commands.GET, "d0/d2 -d f2.exists")
            )

def test_get_dest_1_dir2dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir d2.exists
    > get d0/d2 -d d2.exists

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
    (put dir into dir)

    client-XXXX
    ├── d2.exists
        └──d2
            ├── ff1
            └── ff2
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            tmpdir(local_tmp, name="d2.exists")

            assert_success(
                client.execute_command(Commands.GET, "d0/d2 -d d2.exists")
            )

            check_hierarchy(Path(local_tmp), {
                "d2.exists": {
                    "d2": {
                        "ff1": assert_file,
                        "ff2": assert_file
                    }
                }
            })

def test_get_dest_2_any2none():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get d0/d2 f0 -d d2.notexists

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
    (ERROR)
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            assert_fail(
                client.execute_command(Commands.GET, "d0/d2 f0 -d d2.notexists")
            )


def test_get_dest_2_any2file():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > touch fx.exists
    > get d0/d2 f0 -d fx.exists

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
    (ERROR)
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            tmpfile(local_tmp, name="fx.exists")
            assert_fail(
                client.execute_command(Commands.GET, "d0/d2 f0 -d fx.exists")
            )


def test_get_dest_2_any2dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir fx.exists
    > get d0/d2 f0 -d dx.exists

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
    (put dir into dir)

    client-XXXX
    ├── dx.exists
        ├── f0
        └── d2
            ├── ff1
            └── ff2
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root.name, cd=local_tmp) as client:
            tmpdir(local_tmp, name="dx.exists")
            assert_success(
                client.execute_command(Commands.GET, "d0/d2 f0 -d dx.exists")
            )
            
            check_hierarchy(Path(local_tmp), {
                "dx.exists": {
                    "f0": assert_file,
                    "d2": {
                        "ff1": assert_file,
                        "ff2": assert_file
                    }
                }
            })

def test_teardown():
    esd.__exit__(None, None, None)