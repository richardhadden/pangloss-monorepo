"""The ground of a head class (implementation_docs/semantic-spaces.md, "The ground"): what a document or an entity
says of everything it holds outside any semantic space. The walk (`pangloss_models.spaces`) starts from it.

`Ground` is given to a class's meta (`Document.Meta(ground=Ground(by="source"))`), inherited, and counts only where
an item of the class is the head: a nested document has its head's ground. It is not data: a change of it changes
nothing stored and makes no migration. Checked at `initialise()` (`initialise_models.check_grounds`)."""

from typing import Any, Literal

from pydantic.dataclasses import dataclass

from pangloss_models.model_bases.semantic_space import DegreeStep

Standing = Literal["claim", "record"]
CLAIM: Standing = "claim"
RECORD: Standing = "record"


@dataclass(frozen=True, kw_only=True)
class Ground:
    """What a head class says of what it holds itself, outside any space.

    `veridical`: `1`, it is asserted; `0`, neither asserted nor denied (a rumour). A ground does not deny. `fit`
    and `degree` (only with `0`) are as a semantic space's. `by`: the field of the class that says whose commitment
    it is (a factoid's source), a relation that reaches an entity. `standing`: `"claim"`, it can be contradicted
    by another claim, or `"record"`, what claims are held against; left out, a document's is a claim and an
    entity's the record. A record has no `by`.

    `_meta = Document.Meta(ground=Ground(by="source"))`"""

    veridical: Literal[1, 0, -1] = 1
    """(`-1` is refused at `initialise()`, with what to write in its place)"""
    fit: Literal["describes", "prescribes"] = "describes"
    degree: DegreeStep | None = None
    by: str | None = None
    standing: Standing | None = None


def default_standing(model: type) -> Standing:
    """The standing of a class that says none: the record for an entity, a claim for a document"""
    return RECORD if getattr(model, "__metatype__", None) == "Entity" else CLAIM


def has_ground(model: Any) -> bool:
    """Whether items of the class can be heads, and so have a ground: documents and entities"""
    return getattr(model, "__metatype__", None) in ("Document", "Entity")


def ground_of(model: type) -> Ground:
    """The ground of a head class as it holds: the one it sets or inherits, else asserted, with the standing of
    its kind where it gives none. Never None"""
    ground = getattr(getattr(model, "_meta", None), "ground", None) or Ground()
    if ground.standing is not None:
        return ground
    return Ground(
        veridical=ground.veridical,
        fit=ground.fit,
        degree=ground.degree,
        by=ground.by,
        standing=default_standing(model),
    )
