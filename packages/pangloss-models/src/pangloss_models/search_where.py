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
from dataclasses import dataclass
from decimal import Decimal
import operator
from collections.abc import Iterable
from functools import reduce
from typing import Annotated, Any, ClassVar, Literal, Self, cast
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    create_model,
)
from pydantic.fields import FieldInfo

from pangloss_models.exceptions import PanglossModelError
from pangloss_models.model_bases.model_tools import forget_schema, rebuild, set_field
from pangloss_models.search import (
    OrderBy,
    Reach,
    RuleKey,
    SearchKey,
    Var,
    field_kind,
    orderable_fields,
)


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
    if isinstance(value, (Written, Var)):
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

    is_: Identified | Var | None = aliased("is_", "is")
    is_any: list[Identified] | None = None
    exists: StrictBool | None = None
    through: list[Named] | None = None
    match: "Where | None" = None

    def to_json(self) -> Any:
        written = super().to_json()
        if "match" in written:
            del written["match"]
            if self.match is not None:
                written.update(self.match.to_pattern())
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
    as what a relation points at (or one of `$somewhere`, `$incoming`) it is also its `type` (`to_pattern()`)."""

    _model: ClassVar[type | None] = None

    # (the node itself, as a variable: only in the body of a rule. Each model's `Where` has it typed as a
    # variable of the model)
    is_: Var | None = aliased("is_", RuleKey.IS)

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

    def __or__(self, other: Self) -> Self:
        """`a | b`: either holds (`any_of_`)"""
        return self.combined(other, "any_of_")

    def __and__(self, other: Self) -> Self:
        """`a & b`: both hold (`all_`)"""
        return self.combined(other, "all_")

    def __invert__(self) -> Self:
        """`~a`: it does not hold (`not_`)"""
        return type(self)(not_=self)

    def combined(self, other: Self, name: str) -> Self:
        """The two in one combinator. One that is only that combinator already gives its items (`a | b | c` is
        one `any_of_` of three)."""
        if type(other) is not type(self):
            raise TypeError(
                f"A {type(self).__name__} can only be combined with another, not a {type(other).__name__}"
            )
        items: list[Self] = []
        for where in (self, other):
            if where.model_fields_set == {name}:
                items.extend(getattr(where, name))
            else:
                items.append(where)
        given: dict[str, Any] = {name: items}
        return type(self)(**given)

    def to_pattern(self) -> dict[str, Any]:
        """The pattern of a node this is for: its `type` and its `where`"""
        if self._model is None:
            raise TypeError(
                f"{type(self).__name__} is not the Where of a model (use Letter.Where and the like)"
            )
        written: dict[str, Any] = {"type": self._model.__name__}
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
        return value.to_pattern()
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
        written = self.where.to_pattern()
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


# ---------------------------------------------------------------------------
# The `Where` of each model
# ---------------------------------------------------------------------------

WHERE_KINDS = ("Document", "Entity", "Embedded")


@dataclass(frozen=True)
class WhereExtension:
    """A field that an optional package adds to the `Where` of every model of some kinds (`pangloss-derived` adds
    `derived_`, `$derived`, to the `Where` of entities): the models' `Where` classes are made at `initialise`, so it is
    given before, and put on each as they are made"""

    name: str
    alias: str
    annotation: Any
    kinds: tuple[str, ...] = ("Entity",)


where_extensions: list[WhereExtension] = []


def where_base(model: type) -> type[Where]:
    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_bases.entity import Entity

    if issubclass(model, Document):
        return DocumentWhere
    if issubclass(model, Entity):
        return EntityWhere
    return EmbeddedWhere


def can_have_where(model: Any) -> bool:
    from pangloss_models.utils import model_is_trait

    return (
        getattr(model, "__metatype__", None) in WHERE_KINDS
        and not model_is_trait(model)
        # (`Negative[Person]` and the like: the model is `Negative`)
        and not (getattr(model, "__pydantic_generic_metadata__", None) or {}).get(
            "origin"
        )
        and hasattr(getattr(model, "_meta", None), "fields")
    )


def operators_for(kind: str, base: Any, made: dict[type, type[Where]]) -> Any:
    """The annotation of a field of a `Where` (without `None`). A field of one value, and a relation, also take a
    variable (`Var`) of what they hold, for the body of a rule (see `with_variables`)"""
    if kind == "text":
        return Text
    if kind in ("number", "decimal", "temporal"):
        return Compare[base]
    if kind == "simple":
        return Choice[base]
    if kind == "list":
        return Items[base]
    # (a relation, or an embedded field: what it points at, each with its own `Where`)
    reach: Reach = base
    targets = [made[option] for option in reach.options if option in made]
    return reduce(operator.or_, [Rel, *(targets or [Where])])


@dataclass(frozen=True)
class StubAnnotation:
    """What a type checker is to see of a field (`pangloss make-stubs`), where it is finer than what is validated"""

    annotation: Any


def variables_for(kind: str, base: Any) -> list[Any]:
    """The variables a field takes, as the stubs say them: `Var[str]` for a text, `Var[Person]` for a relation to a
    person, and for a list a variable of one of its items. (When the fields are validated, any `Var` is taken:
    `check_rule` checks its class, and says where. A `Var[Person]` in each place it can go, for every field of every
    model, made pydantic's schemas of the demo's models a third larger)"""
    if kind == "relation":
        return [var_of(model) for model in variable_classes(base.options)]
    return [var_of(base)]


def variable_classes(options: list[type]) -> list[type]:
    """The classes a variable of a relation is written with: what the relation can hold, and a declared class above
    them (a trait they have, an abstract parent) if everything of that class is something the relation can hold
    (`Var[Agent]` where the field is an `Agent`, or a reified relation of one; not where it is a `Person`, as a group
    is an agent too). Of these, the topmost: a `Var` is covariant, so `Var[Agent]` takes a `Var[Person]`. (The classes
    the relation holds alone would refuse the `Var[Agent]` of a rule about any agent.)"""
    from pangloss_models.model_registry import ModelRegistry
    from pangloss_models.utils import model_is_trait

    declared = ModelRegistry._models

    def holds_all_of(cls: type) -> bool:
        return all(
            any(issubclass(model, option) for option in options)
            for model in declared
            if issubclass(model, cls)
            and not model_is_trait(model)
            and not getattr(getattr(model, "_meta", None), "abstract", False)
        )

    above = dict.fromkeys(options)
    for option in options:
        for cls in option.__mro__:
            if cls in ModelRegistry._model_set and cls not in above:
                if holds_all_of(cls):
                    above[cls] = None
    return [
        cls
        for cls in above
        if not any(cls is not other and issubclass(cls, other) for other in above)
    ]


def with_variables(kind: str, base: Any, made: dict[type, type[Where]]) -> FieldInfo:
    """The field of a `Where`: its operators, or a variable"""
    annotation = operators_for(kind, base, made)
    variables = variables_for(kind, base)
    if variables:
        field = FieldInfo(annotation=annotation | Var | None, default=None)
        field.metadata.append(
            StubAnnotation(reduce(operator.or_, [annotation, *variables, type(None)]))
        )
        return field
    return FieldInfo(annotation=annotation | None, default=None)


def var_of(model: Any) -> Any:
    return Var[model]  # (made at runtime: the class is one of the models)


def initialise_where_models(models: Iterable[Any]) -> None:
    """Give each document, entity and embedded model its `Where`, with a field for each of its fields that can be
    searched (`field_kind`). The classes refer to each other (what a relation points at), so all are made before
    any is given its fields."""
    made: dict[Any, Any] = {}
    for model in models:
        if not can_have_where(model):
            continue
        where = create_model(
            f"{model.__name__}Where",
            __base__=where_base(model),
            __module__=model.__module__,
            __doc__=f"A search pattern for a {model.__name__} (see `pangloss_models.search_where`)",
        )
        where._model = model
        model.Where = where
        made[model] = where

    for model, where in made.items():
        # (the fields of the base classes, and the methods of a pattern)
        reserved = set(where.model_fields) | {"to_json", "to_pattern", "is_"}
        for name, definition in model._meta.fields.items():
            found = field_kind(definition)
            # (`label` is searched as text whether it is declared or not: the base class has it)
            if isinstance(found, str) or name == "label":
                continue
            if name in reserved:
                raise PanglossModelError(
                    f"{model.__name__} has a field named '{name}', which is a name of its search pattern "
                    f"({where.__name__}): call it something else"
                )
            kind, base = found
            set_field(where, name, with_variables(kind, base, made))
        for extension in where_extensions:
            if model.__metatype__ in extension.kinds:
                set_field(
                    where,
                    extension.name,
                    combinator(extension.name, extension.alias, extension.annotation),
                )
        # (the node itself, as a variable of a rule)
        is_ = combinator("is_", RuleKey.IS, Var)
        is_.metadata.append(StubAnnotation(var_of(model) | None))
        set_field(where, "is_", is_)
        # (the combinators are patterns of the same class)
        set_field(where, "all_", combinator("all_", SearchKey.ALL, list_of(where)))
        set_field(
            where, "any_of_", combinator("any_of_", SearchKey.ANY_OF, list_of(where))
        )
        set_field(where, "not_", combinator("not_", SearchKey.NOT, where))

    # (what a search of each can be ordered by: `Letter.Order(field="title")`)
    for model in made:
        if where_base(model) is not EmbeddedWhere:
            model.Order = create_model(
                f"{model.__name__}Order",
                __base__=OrderBy,
                __module__=model.__module__,
                __doc__=f"What a search of {model.__name__} is ordered by",
                field=(literal_of(orderable_fields(model)), ...),
            )

    # (as for the other models made: forget the schemas made while the fields were not all there)
    for where in made.values():
        forget_schema(where)
    for where in made.values():
        rebuild(where)


def literal_of(values: list[str]) -> Any:
    return cast(Any, Literal)[
        tuple(values)
    ]  # (made at runtime, from the fields of a model)


def list_of(item: Any) -> Any:
    return list[item]  # (made at runtime: the item is a class made at runtime)


def combinator(name: str, alias: str, annotation: Any) -> FieldInfo:
    alias = str(alias)
    return FieldInfo(
        annotation=annotation | None,
        default=None,
        validation_alias=AliasChoices(alias, name),
        serialization_alias=alias,
    )


Rel.model_rebuild()
AnyRel.model_rebuild()
Where.model_rebuild()
DocumentWhere.model_rebuild()
EntityWhere.model_rebuild()


# ---------------------------------------------------------------------------
# The patterns as data, for the interface's TypeScript
# ---------------------------------------------------------------------------

OPERATORS_OF_KIND = {
    "text": "text",
    "number": "compare",
    "decimal": "compare",
    "temporal": "compare",
    "simple": "choice",
    "list": "items",
    "relation": "relation",
}


def value_type(base: Any) -> dict[str, Any]:
    """The type of the values of a condition, as `export_models` writes types (`{"type": "date"}`,
    `{"type": "enum", "enum": "Status"}`)"""
    import enum

    if isinstance(base, type) and issubclass(base, enum.Enum):
        return {"type": "enum", "enum": base.__name__}
    names = {
        str: "str",
        int: "int",
        float: "float",
        bool: "bool",
        Decimal: "decimal",
        datetime.datetime: "datetime",
        datetime.date: "date",
    }
    if base in names:
        return {"type": names[base]}
    return {"type": "unknown", "repr": repr(base)}


def export_search_patterns(models: Iterable[Any]) -> dict[str, Any]:
    """For each model with a `Where`: its kind (`document`, `entity`, `embedded`), the fields of its `Where` (the
    operators each takes, the type of its values, and for a relation the classes it can point at), and what a
    search of it can be ordered by. (What the interface makes its TypeScript types of patterns from.)"""
    patterns: dict[str, Any] = {}
    for model in sorted(models, key=lambda m: m.__name__):
        where = vars(model).get("Where")
        if where is None:
            continue
        base = where_base(model)
        fields: dict[str, Any] = {}
        for name, definition in model._meta.fields.items():
            if name not in where.model_fields or name == "label":
                continue
            found = field_kind(definition)
            if isinstance(found, str):
                continue
            kind, of = found
            entry: dict[str, Any] = {"operators": OPERATORS_OF_KIND[kind]}
            if kind == "relation":
                entry["targets"] = sorted(
                    option.__name__ for option in of.options if can_have_where(option)
                )
            else:
                entry["value"] = value_type(of)
            fields[name] = entry
        patterns[model.__name__] = {
            "kind": {DocumentWhere: "document", EntityWhere: "entity"}.get(
                base, "embedded"
            ),
            "fields": fields,
            "orderBy": orderable_fields(model) if base is not EmbeddedWhere else [],
        }
    return patterns
