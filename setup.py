import os
from setuptools import setup, find_packages


def read(file_name):
    with open(os.path.join(os.path.dirname(__file__), file_name)) as f:
        return f.read()


setup(
    name="easyshare",
    version="0.1",

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
            "esd = easyshare.esd.__main__:main"
        ]
    },

    # Tests
    # test_suite="tests",

    # Metadata
    author="Stefano Dottore",
    author_email="docheinstein@gmail.com",
    description="FTP/SMB like protocol",
    long_description=read('README.rst'),
    license="MIT",
    keywords="easyshare",
    url="https://github.com/Docheinstein/easyshare",
    install_requires=['Pyro5', 'colorama', 'termcolor']
)
