"""The Pangloss interface: a Solid application for the models of a project."""

from pangloss_models import register_meta_slot

lazy from pangloss_interface.config import InterfaceConfig, NavLink, NavModel

from pangloss_interface.markers import Slider
from pangloss_interface.meta import COLOURS, Collapse, Colour, InterfaceMeta

# (a model class says how it is shown with `_interface_meta = InterfaceMeta(...)`)
register_meta_slot("_interface_meta", InterfaceMeta)

__all__ = [
    "COLOURS",
    "Collapse",
    "Colour",
    "InterfaceConfig",
    "InterfaceMeta",
    "NavLink",
    "NavModel",
    "Slider",
]
