import tempfile
from pathlib import Path
from random import randint
from typing import Union, Dict, Callable

from easyshare.commands.commands import Commands, Get
from easyshare.common import VERBOSITY_MIN, VERBOSITY_DEBUG
from easyshare.es.errors import ClientErrors
from easyshare.es.ui import print_files_info_tree
from easyshare.logging import get_logger
from easyshare.styling import red
from easyshare.utils.os import tree, rm
from tests.utils import EsdTest, EsConnectionTest, tmpfile, tmpdir
from easyshare.esd.__main__ import wait_until_start as wait_until_esd_start

K = 2 << 10
M = 2 << 20
esd = EsdTest()

CLIENT_TAG = "easyshare.es.client"

def log_on(*tags):
    for t in tags:
        get_logger(t).set_level(VERBOSITY_DEBUG)

def log_off(*tags):
    for t in tags:
        get_logger(t).set_level(VERBOSITY_MIN)

def logged(*tags):
    class LoggedContext:
        def __init__(self, tags_):
            self.tags = tags_

        def __enter__(self):
            log_on(self.tags)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            log_off(self.tags)
            return False

    return LoggedContext(tags)



def print_hierarchy(root: Union[Path, str], styler=lambda s: s):
    print(styler("Hierarchy START -----------------------------------------"))
    print_files_info_tree(tree(Path(root)))
    print(styler("Hierarchy END -------------------------------------------"))

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
        print_hierarchy(root, styler=red)
        raise ae

def assert_dir(directory: Union[Path, str]):
    assert Path(directory).is_dir()


def assert_file(file: Union[Path, str], size_checker=lambda s: s > 0):
    assert Path(file).is_file()
    assert size_checker(Path(file).stat().st_size)

def assert_notexists(something: Union[Path, str]):
    assert not Path(something).exists()

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

D2 = {
    "ff1": assert_file,
    "ff2": assert_file
}
D1 = {
    "dd1": assert_dir
}

D0 = {
    "f1": assert_file,
    "d1": D1,
    "d2": D2
}

HIERARCHY = {
    "f0": assert_file,
    "d0": D0
}

def test_setup():
    esd.__enter__()
    wait_until_esd_start()

    create_test_hierarchy(esd.sharing_root_d)

def test_log_on_client():
    log_on(CLIENT_TAG)

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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET)
            )
            check_hierarchy(Path(local_tmp), {
                esd.sharing_root_d.name: HIERARCHY
            })
#
# def test_get_sharing_content():
#     """
#     ===========================
#     ======== COMMANDS =========
#     ===========================
#
#     > cd client-XXXX
#     > get *
#
#     ===========================
#     ========== BEFORE =========
#     ===========================
#
#     --------- LOCAL -----------
#
#     client-XXXX
#
#     --------- REMOTE -----------
#
#     dir-YYYY (sharing name: dir-YYYY)
#     ├── f0
#     └── d0
#         ├── d1
#         │   └── dd1
#         ├── d2
#         │   ├── ff1
#         │   └── ff2
#         └── f1
#
#     ===========================
#     ======== EXPECTED =========
#     ===========================
#
#     --------- LOCAL -----------
#
#     client-XXXX
#     ├── f0
#     └── d0
#         ├── d1
#         │   └── dd1
#         ├── d2
#         │   ├── ff1
#         │   └── ff2
#         └── f1
#     """
#     with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
#         with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
#             assert_success(
#                 client.execute_command(Commands.GET, "*")
#             )
#             check_hierarchy(Path(local_tmp), TEST_HIERARCHY)
#
# def test_get_sharing_content_multiple(): # illegal
#     """
#     ===========================
#     ======== COMMANDS =========
#     ===========================
#
#     > cd client-XXXX
#     > get * d0
#
#     ===========================
#     ========== BEFORE =========
#     ===========================
#
#     --------- LOCAL -----------
#
#     client-XXXX
#
#     --------- REMOTE -----------
#
#     dir-YYYY (sharing name: dir-YYYY)
#     ├── f0
#     └── d0
#         ├── d1
#         │   └── dd1
#         ├── d2
#         │   ├── ff1
#         │   └── ff2
#         └── f1
#
#     ===========================
#     ======== EXPECTED =========
#     ===========================
#     (ERROR)
#     """
#     with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
#         with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
#             assert_fail(
#                 client.execute_command(Commands.GET, "* d0")
#             )

def test_get_fsharing():
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

    file-YYYY (file-sharing)

    ===========================
    ======== EXPECTED =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    └── file-YYYY
    """
    with tempfile.TemporaryDirectory("client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_f.name, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET)
            )
            check_hierarchy(Path(local_tmp), {
                esd.sharing_root_f: assert_file
            })



def test_get_fsharing_not_opened():
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

    file-YYYY (file-sharing)

    ===========================
    ======== EXPECTED =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    └── file-YYYY
    """
    with tempfile.TemporaryDirectory("client-") as local_tmp:
        with EsConnectionTest(sharing_name=None, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET, esd.sharing_root_f.name)
            )
            check_hierarchy(Path(local_tmp), {
                esd.sharing_root_f: assert_file
            })


def test_get_file2none():
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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET, "f0")
            )
            check_hierarchy(Path(local_tmp), {
                "f0": assert_file
            })


def test_get_file2dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir f0
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
    └── f0  // ftype == dir
    """
    with tempfile.TemporaryDirectory("client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            f0 = tmpdir(parent=local_tmp, name="f0")

            assert_success(
                client.execute_command(Commands.GET, "f0")
            )

            assert_dir(f0)


def test_get_dir2none():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get d0/d1//dd1

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
    └── dd1
    """
    with tempfile.TemporaryDirectory("client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET, "d0/d1/dd1")
            )
            check_hierarchy(Path(local_tmp), {
                "dd1": assert_dir
            })


def test_get_dir2dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir d0
    > get d0

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
    └── d0
        ├── d1
        │   └── dd1
        ├── d2
        │   ├── ff1
        │   └── ff2
        └── f1
    """
    with tempfile.TemporaryDirectory("client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            tmpdir(parent=local_tmp, name="d0")

            assert_success(
                client.execute_command(Commands.GET, "d0")
            )

            check_hierarchy(Path(local_tmp), {
                "d0": D0
            })



def test_get_dir2file():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > touch d0
    > get d0

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
    (ERROR ~ soft)

    client-XXXX
    └── f0  // ftype == file
    """
    with tempfile.TemporaryDirectory("client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            log_on(CLIENT_TAG)
            d0 = tmpfile(parent=local_tmp, name="d0", size=666)

            # Allow implementation to either fail or success
            client.execute_command(Commands.GET, "d0")

            assert_file(d0, size_checker=lambda s: s == 666)


def test_get_file2file_overwrite_yes():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > touch f0 // 666 bytes
    > get -y f0

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

    client-XXXX
    └── f0  // == 666 bytes
    """
    with tempfile.TemporaryDirectory("client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            f0 = tmpfile(parent=local_tmp, name="f0", size=666)

            assert_success(
                client.execute_command(Commands.GET, f"{Get.OVERWRITE_YES[0]} f0")
            )

            assert_file(f0, size_checker=lambda s: s != 666)


def test_get_file2file_overwrite_no():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > touch f0 // 666 bytes
    > get -y f0

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

    client-XXXX
    └── f0  // != 666 bytes
    """
    with tempfile.TemporaryDirectory("client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            f0 = tmpfile(parent=local_tmp, name="f0", size=666)

            assert_success(
                client.execute_command(Commands.GET, f"{Get.OVERWRITE_NO[0]} f0")
            )

            assert_file(f0, size_checker=lambda s: s == 666)

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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET, "f0 d0/d2/ff1")
            )

            check_hierarchy(local_tmp, {
                "f0": assert_file,
                "ff1": assert_file
            })



def test_get_dest_sharing2dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir sharing_wrapper
    > get -d sharing_wrapper

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
    └── sharing_wrapper
        └── dir-YYYY
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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            tmpdir(local_tmp, name="sharing_wrapper")
            
            assert_success(
                client.execute_command(Commands.GET, f"{Get.DESTINATION[0]} sharing_wrapper")
            )
            
            check_hierarchy(Path(local_tmp), {
                "sharing_wrapper": {
                    esd.sharing_root_d.name: HIERARCHY
                }
            })

def test_get_dest_sharing2file():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > touch sharing.file
    > get -d sharing.file

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
    (ERROR ~ soft)

    client-XXXX
    └── sharing.file  // ftype == file
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            sharingfile = tmpfile(local_tmp, name="sharing.file", size=666)

            # Allow implementation to either fail or success
            client.execute_command(Commands.GET, f"{Get.DESTINATION[0]} sharing.file")

            assert_file(sharingfile, size_checker=lambda s: s == 666)

def test_get_dest_sharing2none():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get -d sharing_wrapper.notexists

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
    └── sharing_wrapper.notexists
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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET, f"{Get.DESTINATION[0]} sharing_wrapper.notexists")
            )

            check_hierarchy(Path(local_tmp), {
                "sharing_wrapper.notexists": HIERARCHY
            })


def test_get_dest_fsharing2dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir sharing_wrapper
    > get -d sharing_wrapper

    ===========================
    ========== BEFORE =========
    ===========================

    --------- LOCAL -----------

    client-XXXX

    --------- REMOTE -----------

    file-YYYY (file-sharing)

    ===========================
    ======== EXPECTED =========
    ===========================

    --------- LOCAL -----------

    client-XXXX
    └── sharing_wrapper
        └── file-YYYY
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_f.name, cd=local_tmp) as client:
            tmpdir(local_tmp, name="sharing_wrapper")
            log_on(CLIENT_TAG)

            assert_success(
                client.execute_command(Commands.GET, f"{Get.DESTINATION[0]} sharing_wrapper")
            )

            check_hierarchy(Path(local_tmp), {
                "sharing_wrapper": {
                    esd.sharing_root_f.name: assert_file
                }
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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET, f"d0/d2/ff1 {Get.DESTINATION[0]} ff1.renamed")
            )
            check_hierarchy(Path(local_tmp), {
                "ff1.renamed": assert_file
            })

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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            tmpfile(local_tmp, name="ff1.something")
            assert_success(
                client.execute_command(Commands.GET, f"-y d0/d2/ff1 {Get.DESTINATION[0]} ff1.something")
            )
            check_hierarchy(Path(local_tmp), {"ff1.something": assert_file })

def test_get_dest_1_file2dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir dx
    > get d0/d2/ff2 -d dx

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
        └── ff2
    """
    # local_tmp = tempfile.mkdtemp(prefix="client-")
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            dx = tmpdir(local_tmp, name="dx")
            assert_success(
                client.execute_command(Commands.GET, f"d0/d2/ff2 {Get.DESTINATION[0]} dx")
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
    > get d0/d2 -d d2.notexists

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
    ├── d2.notexists
        ├── ff1
        └── ff2
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET, f"d0/d2 {Get.DESTINATION[0]} d2.notexists")
            )

            check_hierarchy(Path(local_tmp), {
                "d2.notexists": D2
            })

def test_get_dest_1_dir2none_empty():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > get d0/d1/dd1 -d d2.notexists

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
    ├── d2.notexists
        ├── ff1
        └── ff2
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            assert_success(
                client.execute_command(Commands.GET, f"d0/d1/dd1 {Get.DESTINATION[0]} d2.notexists")
            )

            check_hierarchy(Path(local_tmp), {
                "d2.notexists": assert_dir
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
    (ERROR ~ soft)

    client-XXXX
    └── f2.exists  // ftype == file
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            f2exists = tmpfile(parent=local_tmp, name="f2.exists", size=666)

            # Allow implementation to either fail or success
            client.execute_command(Commands.GET, f"d0/d2 {Get.DESTINATION[0]} f2.exists")

            assert_file(f2exists, size_checker=lambda s: s == 666)

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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            tmpdir(local_tmp, name="d2.exists")

            assert_success(
                client.execute_command(Commands.GET, f"d0/d2 {Get.DESTINATION[0]} d2.exists")
            )

            check_hierarchy(Path(local_tmp), {
                "d2.exists": {
                    "d2": D2
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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            assert_fail(
                client.execute_command(Commands.GET, f"d0/d2 f0 {Get.DESTINATION[0]} d2.notexists")
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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            tmpfile(local_tmp, name="fx.exists")
            assert_fail(
                client.execute_command(Commands.GET, f"d0/d2 f0 {Get.DESTINATION[0]} fx.exists")
            )


def test_get_dest_2_any2dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir dx.exists
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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            tmpdir(local_tmp, name="dx.exists")
            assert_success(
                client.execute_command(Commands.GET, f"d0/d2 f0 {Get.DESTINATION[0]} dx.exists")
            )
            
            check_hierarchy(Path(local_tmp), {
                "dx.exists": {
                    "f0": assert_file,
                    "d2": D2
                }
            })

def test_get_sync_sharing():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > touch wont.be.removed
    > get -s

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
    (put the content of the sharing into the current dir
     wrapped into a dir with the sharing name)

    client-XXXX
    ├── wont.be.removed
    └── dir-YYYY
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
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            wontberemoved = tmpfile(local_tmp, name="wont.be.removed", size=K)
            assert_file(wontberemoved)

            assert_success(
                client.execute_command(Commands.GET, f"{Get.SYNC[0]}")
            )

            check_hierarchy(Path(local_tmp), {
                esd.sharing_root_d.name: HIERARCHY
            })

            assert_file(wontberemoved)

def test_get_sync_dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir d2
    > touch wont.be.removed
    > touch d2/will.be.removed
    > get -s d0/d2

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
    ├── wont.be.removed
    ├── d2
    │   ├── ff1
    │   └── ff2
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            d2 = tmpdir(local_tmp, name="d2")
            willberemoved = tmpfile(d2, name="will.be.removed", size=K)
            wontberemoved = tmpfile(local_tmp, name="wont.be.removed", size=K)

            assert_file(willberemoved)
            assert_file(wontberemoved)

            assert_success(
                client.execute_command(Commands.GET, f"{Get.SYNC[0]} d0/d2")
            )

            check_hierarchy(Path(local_tmp), {
                "d2": D2
            })

            assert_notexists(willberemoved)
            assert_file(wontberemoved)

def test_get_sync_dir_twice():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir d2
    > touch wont.be.removed
    > touch d2/will.be.removed
    > get -s d0/d2
    > rm d0/d2/ff1
    > get -s d0/d2

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
    ├── wont.be.removed
    ├── d2
    │   ├── ff1
    │   └── ff2
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            d2 = tmpdir(local_tmp, name="d2")
            willberemoved = tmpfile(d2, name="will.be.removed", size=K)
            wontberemoved = tmpfile(local_tmp, name="wont.be.removed", size=K)

            assert_file(willberemoved)
            assert_file(wontberemoved)

            assert_success(
                client.execute_command(Commands.GET, f"{Get.SYNC[0]} d0/d2")
            )

            check_hierarchy(Path(local_tmp), {
                "d2": {
                    "ff1": assert_file,
                    "ff2": assert_file
                }
            })


            assert_notexists(willberemoved)
            assert_file(wontberemoved)

            ff1 = Path(local_tmp) / "d2" / "ff1"
            rm(ff1)
            assert_notexists(ff1)

            assert_success(
                client.execute_command(Commands.GET, f"{Get.SYNC[0]} d0/d2")
            )

            check_hierarchy(Path(local_tmp), {
                "d2": {
                    "ff1": assert_file,
                    "ff2": assert_file
                }
            })



def test_get_sync_file():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > touch wont.be.removed
    > get -s d0/d2/ff1

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
    ├── wont.be.removed
    ├── ff1
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            wontberemoved = tmpfile(local_tmp, name="wont.be.removed", size=K)

            assert_file(wontberemoved)

            assert_success(
                client.execute_command(Commands.GET, f"{Get.SYNC[0]} d0/d2/ff1")
            )

            check_hierarchy(Path(local_tmp), {
                "ff1": assert_file
            })

            assert_file(wontberemoved)


def test_get_syncdest_1_dir2dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir d2.wrapper
    > touch wont.be.removed
    > touch d2.wrapper/wont.be.removed2
    > mkdir d2.wrapper/d2
    > touch d2.wrapper/d2/will.be.removed
    > get -s -d d2.wrapper d0/d2

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
    ├── wont.be.removed
    ├── d2.wrapper
        ├── d2
        │   ├── ff1
        │   └── ff2
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            """
            > cd client-XXXX
            > mkdir d2.wrapper
            > touch wont.be.removed
            > touch d2.wrapper/wont.be.removed2
            > mkdir d2.wrapper/d2
            > touch d2.wrapper/d2/will.be.removed
            > get -s d0/d2 -d d2.wrapper
            """

            d2wrapper = tmpdir(local_tmp, name="d2.wrapper")
            wontberemoved = tmpfile(local_tmp, name="wont.be.removed", size=K)
            wontberemoved2 = tmpfile(d2wrapper, name="wont.be.removed2", size=K)
            d2 = tmpdir(d2wrapper, name="d2")
            willberemoved = tmpfile(d2, name="will.be.removed", size=K)

            assert_file(willberemoved)
            assert_file(wontberemoved)
            assert_file(wontberemoved2)

            assert_success(
                client.execute_command(Commands.GET,
                                       f"{Get.DESTINATION[0]} d2.wrapper {Get.SYNC[0]} d0/d2")
            )

            check_hierarchy(Path(local_tmp), {
                "d2.wrapper": {
                    "d2": D2
                }
            })

            print_hierarchy(local_tmp)

            assert_notexists(willberemoved)
            assert_file(wontberemoved2)
            assert_file(wontberemoved)


def test_get_syncdest_2_any2dir():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir dx.exists
    > touch dx.exists/wont.be.removed
    > get d0/d2 f0 -d dx.exists -s

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
    ├── dx.exists
        ├── wont.be.removed
        ├── f0
        └── d2
            ├── ff1
            └── ff2
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            dxexists = tmpdir(local_tmp, name="dx.exists")
            wontberemoved = tmpfile(dxexists, name="wont.be.removed", size=666)

            assert_file(wontberemoved)

            assert_success(
                client.execute_command(Commands.GET, f"{Get.DESTINATION[0]} dx.exists {Get.SYNC[0]} d0/d2 f0")
            )

            check_hierarchy(Path(local_tmp), {
                "dx.exists": {
                    "f0": assert_file,
                    "d2": D2
                }
            })

            assert_file(wontberemoved)

def test_get_syncdest_2_any2dir_bis():
    """
    ===========================
    ======== COMMANDS =========
    ===========================

    > cd client-XXXX
    > mkdir dx.exists
    > mkdir dx.exists/d0
    > touch dx.exists/d0/will.be.removed
    > get d0/d2 d0/d1 -d dx.exists -s

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
    ├── dx.exists
        ├── wont.be.removed
        ├── d0
            ├── dd1
        └── d2
            ├── ff1
            └── ff2
    """
    with tempfile.TemporaryDirectory(prefix="client-") as local_tmp:
        with EsConnectionTest(esd.sharing_root_d.name, cd=local_tmp) as client:
            """
            > cd client-XXXX
            > mkdir dx.exists
            > mkdir dx.exists/d1
            > touch dx.exists/d1/will.be.removed
            > get d0/d2 d0/d1 -d dx.exists -s
            """

            dxexists = tmpdir(local_tmp, name="dx.exists")
            d1 = tmpdir(dxexists, name="d1")
            wontberemoved = tmpfile(dxexists, name="wont.be.removed", size=666)
            willberemoved = tmpfile(d1, name="will.be.removed", size=666)

            assert_file(wontberemoved)
            assert_file(willberemoved)

            assert_success(
                client.execute_command(Commands.GET, f"{Get.DESTINATION[0]} dx.exists {Get.SYNC[0]} d0/d2 d0/d1")
            )

            check_hierarchy(Path(local_tmp), {
                "dx.exists": {
                    "d1": D1,
                    "d2": D2
                }
            })

            print_hierarchy(local_tmp)

            assert_file(wontberemoved)
            assert_notexists(willberemoved)


def test_teardown():
    esd.__exit__(None, None, None)