"""Where the interface's own pages are in its navigation bar: the list of merges of entities (a page of the
interface module of this package), for someone logged in."""

from pangloss_interface.config import InterfaceConfig, NavLink

config = InterfaceConfig(
    nav=[NavLink("Merges", href="/merges", requires_login=True)],
)
