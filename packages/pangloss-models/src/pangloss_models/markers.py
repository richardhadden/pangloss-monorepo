"""Field markers: what a field is annotated with to say something of it that is not its type or a constraint
(`Annotated[int, Ge(1), Le(100), Slider()]`): exported with the field (`markers`), by the class's name and what
`export()` gives, for the interface to act on. Not part of the data, nor of the migration snapshot. On a relation, a list or an annotated value a marker is kept on the field's definition, not exported."""

from typing import Any


class FieldMarker:
    """A marker of a field: a literal, a list of them, a relation or an annotated value (an embedded field's markers are those with `apply_to_embedded`). A subclass
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


class KeepOnMerge(FieldMarker):
    """On a relation to entities: a merge of two entities (`Entity.merge`) leaves this relation where it is. What it
    points at still names the absorbed entity afterwards (shown as "merged into ..."), and a later write of the
    document does not resolve it to the survivor. For a relation whose meaning is the entity as it was named: a record
    of what something was once called, or a claim that two entities are one (`pangloss_library.IdentityClaim`), which
    would otherwise come to say that an entity is itself.

    `Annotated[list[Person], KeepOnMerge()]`"""

    def check(self, owner: str, field: dict[str, Any]) -> None:
        # (only a literal field's markers are checked at export: on one, this marker means nothing)
        if field.get("kind") == "literal":
            from pangloss_models.exceptions import PanglossModelError

            raise PanglossModelError(
                f"{owner}.{field.get('name')}: KeepOnMerge() is for a relation to entities"
            )


def keeps_on_merge(definition: Any) -> bool:
    """Whether a field (its definition) is marked `KeepOnMerge()`, or with a subclass of it"""
    return any(isinstance(m, KeepOnMerge) for m in getattr(definition, "markers", ()))
