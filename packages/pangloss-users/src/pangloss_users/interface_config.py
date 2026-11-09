"""Where users are in the interface's navigation bar: a link to the list of them (a page of the users interface module),
for someone logged in. Read by `pangloss_interface` only when it is installed."""

from pangloss_interface import InterfaceConfig, NavLink

config = InterfaceConfig(
    nav=[NavLink("Users", href="/users", requires_login=True)],
)
