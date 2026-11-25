"""Field markers: what a field is annotated with to say something of it that is not its type or a constraint
(`Annotated[int, Ge(1), Le(100), Slider()]`): exported with the field (`markers`), by the class's name and what
`export()` gives, for the interface to act on. Not part of the data, nor of the migration snapshot. On a relation a marker is kept on
the field's definition and exported (`markers`, by name and what `export()` gives), except `Attribution`, which is
exported as the field's `attribution`; on a list or an annotated value it is kept on the definition, not exported."""

from dataclasses import dataclass
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

    def export(self) -> dict[str, Any]:
        # (said for a subclass too, whatever its name: the interface asks this, not the name)
        return {"keepOnMerge": True}

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


class Computed(FieldMarker):
    """On a relation or a literal: the server keeps the field up to date, and nobody writes it. It is read (`View`,
    `HeadView`, `ReferenceView`, the class's `Where`) and not written: `Create` and `Update` do not have it, and a
    value sent back from a read is taken out before the check. It is written by `set_computed` of the backend's
    operations alone, which makes no new version. A computed relation is no reference: it does not keep its target
    from being deleted, counts for no usage, and a merge does not move it
    (implementation_docs/matches-criteria.md, "`Computed()`").

    `Annotated[list[T], Computed()] = []`, `Annotated[int, Computed()] = 0`"""

    def export(self) -> dict[str, Any]:
        return {"computed": True}


def is_computed(definition: Any) -> bool:
    """Whether a field (its definition) is marked `Computed()`, or with a subclass of it"""
    return any(isinstance(m, Computed) for m in getattr(definition, "markers", ()))


@dataclass(frozen=True, kw_only=True)
class Attribution(FieldMarker):
    """On a relation that holds a semantic space (directly, in a list, or among other things in a union): whose the
    space is, by the names of two other fields of the class. `by`: whose attitude or act it is (who orders, believes,
    doubts, reports). `to`: whom it is addressed to (who is ordered, asked); left out for a belief. Each is a relation
    of the class that reaches an entity, directly or through a wrapper. One of the two at least is given. Checked at
    `initialise()`; exported as the field's `attribution`; not data.

    `thing_ordered: Annotated[Ordered[Statement], Attribution(by="ordered_by", to="ordered_to")]`"""

    by: str | None = None
    to: str | None = None


def attribution_of(definition: Any) -> Attribution | None:
    """The `Attribution` a field (its definition) is marked with, or None"""
    return next(
        (m for m in getattr(definition, "markers", ()) if isinstance(m, Attribution)),
        None,
    )


def attributions(model: type) -> dict[str, Attribution]:
    """The fields of a class that have an `Attribution`, by name, those it inherits included"""
    fields = getattr(getattr(model, "_meta", None), "fields", None) or {}
    return {
        name: found
        for name, definition in fields.items()
        if (found := attribution_of(definition)) is not None
    }
