"""What a project's models import from `pangloss_interface`, for a client that does not have it.

How a model is shown (`_interface_meta = InterfaceMeta(colour="rose")`, `Annotated[int, Slider()]`) is not data: a
client of the API has no use for it, and should not need the interface (and what it needs) to import the models. So
`pangloss sdk build` ships a model module with its `from pangloss_interface import ...` pointed here, and these take
what they are given and keep none of it. Where the interface is installed, they are the real ones.

Only the names a model is declared with are here: the rest of `pangloss_interface` (`InterfaceConfig`, the
navigation) is not for a model module, and the build says so.
"""

from typing import Any

from pangloss_models import FieldMarker, register_meta_slot

__all__ = ["Collapse", "Colour", "InterfaceMeta", "Slider"]

try:
    from pangloss_interface import Collapse, Colour, InterfaceMeta, Slider
except ImportError:

    class _Ignored:
        def __init__(self, *args: Any, **settings: Any) -> None:
            pass

        def __repr__(self) -> str:
            return f"{type(self).__name__}(not used by an SDK)"

    class InterfaceMeta(_Ignored):
        """Stands in for `pangloss_interface.InterfaceMeta`: whatever it is given, it holds nothing"""

    class Collapse(_Ignored):
        """Stands in for `pangloss_interface.Collapse`"""

    class Slider(FieldMarker):
        """Stands in for `pangloss_interface.Slider`: a marker that says nothing of its field"""

        def __init__(self, *args: Any, **settings: Any) -> None:
            pass

    # (an annotation only: any text will do)
    Colour = str

    # (as the interface does: `Person._interface_meta` is then the object, and a subclass has its parent's)
    register_meta_slot("_interface_meta", InterfaceMeta)
