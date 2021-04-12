    SCRIPT       |       PURPOSE
------------------------------------------------------------------
build.sh         |  build a easyshare-<version>.tar.gz in ./dist
deploy.sh        |  push last version to PyPi
install.sh       |  install last version in ./dist locally
make-hmd.sh      |  build hmd (internal help <command>)
make-mans.sh     |  build mans (man <command>)
make_hmd.py      |  python scripts internally used by make-hmd.sh
release.sh       |  create hmd/mans and build
test.sh          |  run tests
uninstall.sh     |  uninstall local version
utils.sh         |  utils used by other scripts
-------------------------------------------------------------------

Typical usage:

RELEASE and DEPLOY
    $ devscripts/release.sh
    $ devscripts/deploy.sh
