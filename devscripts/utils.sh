CLEAR=$(tput sgr0)
RED=$(tput setaf 1)
GREEN=$(tput setaf 2)
YELLOW=$(tput setaf 3)
BLUE=$(tput setaf 4)
MAGENTA=$(tput setaf 5)
CYAN=$(tput setaf 6)

echo_red() { echo "${RED}$*${CLEAR}" ; }
echo_green() { echo "${GREEN}$*${CLEAR}" ; }
echo_yellow() { echo "${YELLOW}$*${CLEAR}" ; }
echo_cyan() { echo "${CYAN}$*${CLEAR}" ; }
echo_blue() { echo "${BLUE}$*${CLEAR}" ; }
echo_magenta() { echo "${MAGENTA}$*${CLEAR}" ; }

command_exists() {
  command -v "$@" > /dev/null 2>&1
}

pip_module_exists() {
  pip show "$1" > /dev/null 2>&1
}

abort() {
  echo_red "$@"
  exit 1
}