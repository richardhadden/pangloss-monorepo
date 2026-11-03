"""Where review is in the interface's navigation bar: a link to the queue of documents to check (a page of the
review interface module), for someone logged in. Read by `pangloss_interface` only when it is installed."""

from pangloss_interface.config import InterfaceConfig, NavLink

config = InterfaceConfig(
    nav=[NavLink("Review", href="/review", requires_login=True)],
)
