"""Structured search patterns written as Python objects (see docs/search-where-implementation.md).

    Letter.search(Letter.Where(
        title=Text(contains="plague"),
        sender=Rel(is_=smith),
        addressee=Person.Where(label=Text(contains="venice")),
    ))

Each class here is a way of writing the JSON of a pattern (`docs/structured-search.md`), and `to_json()` gives
it: `parse_where` takes them where it takes the dicts, and `check_match` checks what they make, as it checks the
JSON. The classes catch what types can (a field that is not there, an operator that does not fit the kind of a
field, a value of the wrong type); `check_match` catches the rest.

A field is written by its Python name (`in_`, `is_`, `any_of_`), and its alias is the key of the JSON (`in`, `is`,
`$any_of`). The alias is a `validation_alias`, not an `alias`, so that a type checker takes the Python name for the
name of the parameter.
"""

import datetime
from decimal import Decimal
from typing import Annotated, Any, ClassVar
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
)

from pangloss_models.search import SearchKey


def aliased(name: str, alias: str) -> Any:
    """A field (left out unless it is given) whose key in the JSON is `alias`"""
    alias = str(alias)  # (a `SearchKey` is written as its string)
    return Field(
        default=None,
        validation_alias=AliasChoices(alias, name),
        serialization_alias=alias,
    )


def id_of(value: Any) -> Any:
    """An entity, a view of one or anything else with an `id` is its id"""
    if isinstance(value, (UUID, str)) or not hasattr(value, "id"):
        return value
    return value.id


def name_of(value: Any) -> Any:
    """A model class is its name"""
    return value.__name__ if isinstance(value, type) else value


type Identified = Annotated[UUID | BaseModel, BeforeValidator(id_of)]
type Named = Annotated[str | type, BeforeValidator(name_of)]


class Written(BaseModel):
    """The base of the classes that write a pattern"""

    model_config = ConfigDict(
        extra="forbid", validate_by_name=True, validate_by_alias=True
    )

    def to_json(self) -> Any:
        """The JSON of the pattern (Python values in it: a date, a UUID, an enum member)"""
        return {
            (field.serialization_alias or name): plain(getattr(self, name))
            for name, field in type(self).model_fields.items()
            if name in self.model_fields_set
        }


def plain(value: Any) -> Any:
    if isinstance(value, Written):
        return value.to_json()
    if isinstance(value, list):
        return [plain(item) for item in value]
    if isinstance(value, tuple):
        return [plain(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# The operators of a field, one class for each kind
# ---------------------------------------------------------------------------


class Text(Written):
    """A `str` field, and `label`"""

    eq: str | None = None
    ne: str | None = None
    in_: list[str] | None = aliased("in_", "in")
    exists: StrictBool | None = None
    contains: str | None = None
    starts_with: str | None = None


class Compare[T: (int, float, Decimal, datetime.date, datetime.datetime)](Written):
    """A number, a `Decimal`, a date or a datetime: `Compare[datetime.date](lt=...)`"""

    eq: T | None = None
    ne: T | None = None
    in_: list[T] | None = aliased("in_", "in")
    exists: StrictBool | None = None
    gt: T | None = None
    gte: T | None = None
    lt: T | None = None
    lte: T | None = None
    between: tuple[T, T] | None = None


class Choice[T](Written):
    """A `bool`, or an enum"""

    eq: T | None = None
    ne: T | None = None
    in_: list[T] | None = aliased("in_", "in")
    exists: StrictBool | None = None


class Items[T](Written):
    """A list of any of the kinds above (`contains` is one of its items)"""

    contains: T | None = None
    contains_any: list[T] | None = None
    contains_all: list[T] | None = None
    exists: StrictBool | None = None


class Rel(Written):
    """A relation, or an embedded field: by what it points at (`is_`, `is_any`: ids, or anything with an `id`),
    whether it has any (`exists`), the wrappers it has to pass through (`through`: the classes, or their names), and
    a pattern for what it points at (`match`; a `Where` can also be given for the field itself, without `Rel`)"""

    is_: Identified | None = aliased("is_", "is")
    is_any: list[Identified] | None = None
    exists: StrictBool | None = None
    through: list[Named] | None = None
    match: "Where | None" = None

    def to_json(self) -> Any:
        written = super().to_json()
        if "match" in written:
            del written["match"]
            if self.match is not None:
                written.update(self.match.pattern())
        return written


class AnyRel(Rel):
    """`$any` (any relation of the node; `contains` and `starts_with` are of its label) and `$mentions` (any
    relation of any node of the document)"""

    contains: str | None = None
    starts_with: str | None = None


# ---------------------------------------------------------------------------
# Patterns for a node
# ---------------------------------------------------------------------------


class Where(Written):
    """The base of the `Where` of each model (`Letter.Where`), which `initialise` makes with a field for each
    field of the model that can be searched. A pattern for the node, written as the `where` of the JSON;
    as what a relation points at (or one of `$somewhere`, `$incoming`) it is also its `type` (`pattern()`)."""

    model: ClassVar[type | None] = None

    # (combinators: patterns for the same node)
    all_: "list[Where] | None" = aliased("all_", SearchKey.ALL)
    any_of_: "list[Where] | None" = aliased("any_of_", SearchKey.ANY_OF)
    not_: "Where | None" = aliased("not_", SearchKey.NOT)
    any_: AnyRel | None = aliased("any_", SearchKey.ANY)

    def to_json(self) -> Any:
        given = {
            (field.serialization_alias or name): getattr(self, name)
            for name, field in type(self).model_fields.items()
            if name in self.model_fields_set
        }
        # (the fields of the model, then the `$` keys)
        return where_json(
            dict(sorted(given.items(), key=lambda kv: kv[0].startswith("$")))
        )

    def pattern(self) -> dict[str, Any]:
        """The pattern of a node this is for: its `type` and its `where`"""
        if self.model is None:
            raise TypeError(
                f"{type(self).__name__} is not the Where of a model (use Letter.Where and the like)"
            )
        written: dict[str, Any] = {"type": self.model.__name__}
        where = self.to_json()
        if where:
            written["where"] = where
        return written


def where_json(where: dict[str, Any]) -> dict[str, Any]:
    """A `where` with these objects in it as JSON. A `Where` is the `where` of the same node in a combinator,
    and the pattern of another node (its `type` and `where`) anywhere else: as what a relation points at, and in
    `$somewhere` and `$incoming`."""
    return {
        key: plain(value)
        if key in (SearchKey.ALL, SearchKey.ANY_OF, SearchKey.NOT)
        else as_pattern(value)
        for key, value in where.items()
    }


def as_pattern(value: Any) -> Any:
    if isinstance(value, Where):
        return value.pattern()
    if isinstance(value, list):
        return [as_pattern(item) for item in value]
    return plain(value)


class DocumentWhere(Where):
    """The base of the `Where` of a document: what the head document of a search has (`published`,
    `review_status`, `somewhere_`, `mentions_`), and what a document inside one has (`spaces_`)"""

    label: Text | None = None
    published: Choice[bool] | None = None
    review_status: Text | None = None
    mentions_: AnyRel | None = aliased("mentions_", SearchKey.MENTIONS)
    somewhere_: "list[DocumentWhere] | None" = aliased(
        "somewhere_", SearchKey.SOMEWHERE
    )
    spaces_: list[Named] | None = aliased("spaces_", SearchKey.SPACES)


class IncomingFrom(Written):
    """A node that points at an entity (`$incoming`): one of the class of `where` and fitting it, by a relation
    `field` (any that can point at the entity, if left out), through `through` wrappers if given. (A `Where` can be
    given in place of one, for any field and no wrappers.)"""

    where: Where
    field: str | None = None
    through: list[Named] | None = None

    def to_json(self) -> Any:
        written = self.where.pattern()
        if self.field is not None:
            written["field"] = self.field
        if self.through is not None:
            written["through"] = list(self.through)
        return written


class EntityWhere(Where):
    """The base of the `Where` of an entity"""

    label: Text | None = None

    incoming_: list[IncomingFrom | Where] | None = aliased(
        "incoming_", SearchKey.INCOMING
    )


class EmbeddedWhere(Where):
    """The base of the `Where` of an embedded model"""


Rel.model_rebuild()
AnyRel.model_rebuild()
Where.model_rebuild()
DocumentWhere.model_rebuild()
EntityWhere.model_rebuild()
