"""Where Zotero is in the interface's navigation bar: one link, to the list of every item (`ZoteroBacked`). Its fallback class
is what that lists anyway, and a library is only the sync's own record. Both still have their pages. Read by
`pangloss_interface` only when it is installed."""

from pangloss_interface import InterfaceConfig, NavModel

config = InterfaceConfig(
    nav=[
        NavModel("ZoteroObject", hidden=True),
        NavModel("ZoteroLibrary", hidden=True),
    ]
)
