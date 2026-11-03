"""Constraints a field can be annotated with, beside those of `annotated_types` (`Ge`, `MaxLen`, ...): checked
when a model is written, and exported with the field's other validators for the interface to check (and act on)"""

from dataclasses import dataclass

from annotated_types import BaseMetadata


@dataclass(frozen=True, slots=True)
class SumsTo(BaseMetadata):
    """The items of a list relation share `total` between them: their edge property `field` (an `int`) adds up
    to it. `Annotated[list[ViaEdge[T, Probability]], SumsTo("percent")]`: the alternatives' percentages add
    up to 100. Written only if it does (an empty list has nothing to share); the interface keeps them to it,
    one giving way as another is changed."""

    field: str
    total: int = 100
