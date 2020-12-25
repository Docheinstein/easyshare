import os
import sys

from setuptools import setup, find_packages


def read(file_name):
    with open(os.path.join(os.path.dirname(__file__), file_name)) as f:
        return f.read()

print("setup.py prefix:", sys.prefix)

setup(
    name="easyshare",
    version="0.13",

    # Requires python3.6
    python_requires=">=3.6",

    # Automatically import easyshare packages
    packages=find_packages(),

    # Include the files specified in MANIFEST.in in the release archive
    include_package_data=True,

    # Scripts to install to the user executable path.
    entry_points={
        "console_scripts": [
            "es = easyshare.es.__main__:main",
            "esd = easyshare.esd.__main__:main",
            "es-tools = easyshare.tools.__main__:main"
        ]
    },

    data_files=[
        (
            "share/man/man1", [
                "docs/sphinx/build/man/es.1",
                "docs/sphinx/build/man/esd.1",
                "docs/sphinx/build/man/es-tools.1",
            ]
        )
    ],

    # Tests
    test_suite="tests",

    # Metadata
    author="Stefano Dottore",
    author_email="docheinstein@gmail.com",
    description="Client-Server command line application for share files, similar to FTP but more powerful;"
                " written in Python 3.6+",
    long_description=read('README.MD'),
    long_description_content_type="text/markdown",
    license="MIT",
    keywords="easyshare",
    url="https://github.com/Docheinstein/easyshare",
    install_requires=[
        "colorama",
        "hmd",
        "ptyprocess; 'linux' in sys_platform",
        "pywin32; 'win' in sys_platform",
        "pyreadline; 'win' in sys_platform"
    ]
)