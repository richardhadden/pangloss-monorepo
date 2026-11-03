"""Field markers: what a field is annotated with to say something of it that is not its type or a constraint
(`Annotated[int, Ge(1), Le(100), Slider()]`): exported with the field (`markers`), by the class's name and what
`export()` gives, for the interface to act on. Not part of the data, nor of the migration snapshot."""

from typing import Any


class FieldMarker:
    """A marker of a literal field (an embedded field's markers are those with `apply_to_embedded`). A subclass
    may check the field it is on (`check`, at export) and say more of itself (`export`)."""

    def check(self, owner: str, field: dict[str, Any]) -> None:
        """Raise if the field (as exported) is not one this marker can be on"""

    def export(self) -> dict[str, Any]:
        return {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and vars(other) == vars(self)

    def __hash__(self) -> int:
        return hash((type(self), tuple(sorted(vars(self).items()))))
