import os
from pathlib import Path

"""

>>> p = PurePath('/usr/bin/python3')
>>> p.parts
('/', 'usr', 'bin', 'python3')

>>> p = PureWindowsPath('c:/foo/bar/setup.py')
>>> p.parents[0]
PureWindowsPath('c:/foo/bar')

>>> p = PurePosixPath('/a/b/c/d')
>>> p.parent
PurePosixPath('/a/b/c')

>>> PurePosixPath('my/library/setup.py').name
'setup.py'

>>> PurePosixPath('my/library/setup.py').name
'setup.py'

>>> p = PurePosixPath('/etc/passwd')
>>> p.relative_to('/')
PurePosixPath('etc/passwd')

>>> p = PureWindowsPath('c:/Downloads/pathlib.tar.gz')
>>> p.with_name('setup.py')
PureWindowsPath('c:/Downloads/setup.py')

-----------------


>>> Path.cwd()
PosixPath('/home/antoine/pathlib')

>>> Path.home()
PosixPath('/home/antoine')


>>> p = Path('setup.py')
>>> p.stat().st_size
956
>>> p.stat().st_mtime
1327883547.852554


>>> Path('setup.py').exists()
True

>>> p.expanduser()
PosixPath('/home/eric/films/Monty Python')


>>> sorted(Path('.').glob('*.py'))
[PosixPath('pathlib.py'), PosixPath('setup.py'), PosixPath('test_pathlib.py')]


>>> p = Path()
>>> p
PosixPath('.')
>>> p.resolve()
PosixPath('/home/antoine/pathlib')

- Path.is_dir()
- Path.is_file()
- Path.mkdir
- Path.open
- Path.unlink

- for x in Path.iterdir()


"""


if __name__ == "__main__":
    # os.listdir(None)
    for f in Path(None).expanduser().iterdir():
        print(f.name)
    # p = Path("~").name
    # print(type(p))
    # p = p.expanduser()
    # for f in p.iterdir():
    #     print(f)
    # print(Path("lol").resolve())
    # print(Path("lol"))
    # print(Path("lol").is_dir())
    # print(Path("/tmp").is_dir())
    # print(Path("/tmp").resolve().expanduser().is_dir())
    # print(Path("").resolve())
    # for x in Path("/tmp/ajiwejw").iterdir():
    #     print(x)
    # print(Path("/home/stefano/"))
    # print(str(Path("/home/stefano/")))
    #
    #
    # print("--- parents ---")
    # for p in Path("/home/stefano/").parents:
    #     print(p)
    # print("---")
    # print("--- parts ---")
    # for p in Path("/home/stefano/").parts:
    #     print(p)
    # print("---")
    # print(Path("/home/stefano").parent)
    # print(Path("/home/stefano/").parent)
    # print(Path("/home/stefano/").name)
    # print(Path("/home/stef").parent)
    #
    # print(os.path.split("/home/stefano/"))
    #
    # print("base", os.path.basename("/home/stefano/"))
    # print("dir", os.path.dirname("/home/stefano/"))
    #
    # print("base", os.path.basename("/home/stefano"))
    # print("dir", os.path.dirname("/home/stefano"))
    # print("----")
    # print(os.listdir(os.path.expanduser("~")))
    # print("----")

    # print("----")
