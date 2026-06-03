from typing import TYPE_CHECKING, Generic, TypeVarTuple

from pydantic import BaseModel

if TYPE_CHECKING:
    from pangloss_models.model_bases.edge_model import EdgeModel


Ts = TypeVarTuple("Ts")


class Fulfils(Generic[*Ts]):
    _fulfiling_types: tuple

    @classmethod
    def __class_getitem__(cls, typs):
        if not isinstance(typs, tuple):
            typs = (typs,)
        cls._fulfiling_types = typs
        return cls


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
