from easyshare.common import easyshare_setup, VERBOSITY_MAX, TRACING_MAX, VERBOSITY_ERROR, TRACING_TEXT
from easyshare.settings import set_setting, Settings

easyshare_setup()
set_setting(Settings.VERBOSITY, VERBOSITY_ERROR)
# set_setting(Settings.VERBOSITY, VERBOSITY_MAX)
set_setting(Settings.TRACING, TRACING_TEXT)