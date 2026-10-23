"""(An installed app's `models` module is imported as the server and the commands start, which
is how history begins to listen to writes. It has no models of its own.)"""

from pangloss_history.listener import install

install()
