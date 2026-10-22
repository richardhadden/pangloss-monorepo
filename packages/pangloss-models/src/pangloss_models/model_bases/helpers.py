from typing import TYPE_CHECKING, Generic, TypeVarTuple

from pydantic import BaseModel

if TYPE_CHECKING:
    from pangloss_models.model_bases.edge_model import EdgeModel


Ts = TypeVarTuple("Ts")


class Fulfils(Generic[*Ts]):
    """`Fulfils[A, B]` as a base class: the class supplies what `A` and `B` require.

    Each `Fulfils[...]` is a class of its own, holding the classes it was given in its own
    `_fulfilling_types` (not on `Fulfils`, which every class that fulfils anything would share)."""

    _fulfilling_types: tuple = ()

    @classmethod
    def __class_getitem__(cls, typs):
        if not isinstance(typs, tuple):
            typs = (typs,)
        names = ", ".join(getattr(t, "__name__", str(t)) for t in typs)
        return type(f"Fulfils[{names}]", (cls,), {"_fulfilling_types": typs})


class ViaEdge[Target, Model: EdgeModel](BaseModel):
    """There is clearly a problem with this; in type checking, Model must be type[EdgeModel],
    but genericlaly subclassing with real EdgeModel subclass goes all wrong"""

    pass


class AnnotatedLiteral[LiteralType](BaseModel):
    value: LiteralType


class DBField:
    pass


class Description(str):
    pass
