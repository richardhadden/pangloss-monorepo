"""Where the calendar is in the interface's navigation bar: a link to the list of years (a page of the calendar
interface module, `pangloss_calendar/interface/`). Read by `pangloss_interface` only when it is installed."""

from pangloss_interface import InterfaceConfig, NavLink

config = InterfaceConfig(nav=[NavLink("Calendar", href="/calendar")])
