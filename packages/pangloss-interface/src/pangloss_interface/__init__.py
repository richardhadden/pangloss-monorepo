"""The Pangloss interface: a Solid application for the models of a project."""

from pangloss_models.meta_slots import register_meta_slot

from pangloss_interface.meta import COLOURS, Colour, InterfaceMeta

# (a model class says how it is shown with `_interface_meta = InterfaceMeta(...)`)
register_meta_slot("_interface_meta", InterfaceMeta)

__all__ = ["COLOURS", "Colour", "InterfaceMeta"]
