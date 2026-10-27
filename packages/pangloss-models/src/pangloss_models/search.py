"""Structured search: finding documents and entities by a pattern written as JSON (see docs/structured-search.md).

    {"type": "Letter", "where": {"date": {"gt": "1500-01-01"}, "sender": {"is": "0194…"}}}

`Match` is the pattern, and `check_match` checks it against the models: every field has to exist, every
operator has to fit the type of its field, and every value is made the type of the field. What comes out
(`CheckedCondition`) is all a backend needs to build its query; nothing in it is text from the request.
"""

import datetime
import enum
import types as pytypes
import typing
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from pangloss_models.exceptions import PanglossSearchError, PanglossUnknownTypeError
from pangloss_models.field_definitions import (
    EmbeddedFieldDefinition,
    ListFieldDefinition,
    LiteralFieldDefinition,
    RelationFieldDefinition,
    RelationToConjunction,
    RelationToDocument,
    RelationToEntity,
    RelationToReifiedRelation,
    RelationToReifiedRelationDocument,
    RelationToSemanticSpace,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity

# The most that can be asked for in one search
MAX_SEARCH_PAGE_SIZE = 100
MAX_CONDITIONS = 20
MAX_VALUES = 100
# Nesting is not limited by what the data may hold (a document can be nested as deep as it likes, and an entity
# is reached through many relations): the size of a search is. What is limited is how deep the JSON is read (so
# that a hostile one cannot make the reading recurse without end), and how many patterns and expressions there
# are in all.
MAX_DEPTH = 50
MAX_PATTERNS = 50  # (patterns for what a relation points at, in one search)
MAX_EXPRESSIONS = 500


def parse_where(raw: Any, depth: int = 0) -> dict[str, Any]:
    """A `where`: a field's key to its `Condition`, and the combinators (`$all` and `$any_of`: lists of
    `where`s; `$not`: a `where`), each made into the same"""
    if not isinstance(raw, dict):
        raise ValueError("'where' must be an object")
    if depth > MAX_DEPTH:
        raise ValueError(f"patterns are nested more than {MAX_DEPTH} deep")
    parsed: dict[str, Any] = {}
    for key, value in raw.items():
        if key in ("$all", "$any_of"):
            if not isinstance(value, list) or not value or len(value) > MAX_VALUES:
                raise ValueError(f"{key} needs a list of conditions")
            parsed[key] = [parse_where(item, depth + 1) for item in value]
        elif key == "$not":
            parsed[key] = parse_where(value, depth + 1)
        elif key in ("$any", "$mentions"):
            parsed[key] = (
                value
                if isinstance(value, Condition)
                else Condition.model_validate(value)
            )
        elif key == "$somewhere":
            if not isinstance(value, list) or not value or len(value) > MAX_VALUES:
                raise ValueError("$somewhere needs a list of patterns")
            parsed[key] = [
                v if isinstance(v, Condition) else Condition.model_validate(v)
                for v in value
            ]
        elif key == "$incoming":
            items = value if isinstance(value, list) else [value]
            if not items or len(items) > MAX_VALUES:
                raise ValueError("$incoming needs a pattern, or a list of them")
            parsed[key] = [
                v if isinstance(v, Incoming) else Incoming.model_validate(v)
                for v in items
            ]
        elif key == "$spaces":
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(v, str) for v in value)
            ):
                raise ValueError("$spaces needs a list of the names of semantic spaces")
            parsed[key] = value
        elif key.startswith("$"):
            raise ValueError(f"'{key}' is not supported")
        elif isinstance(value, Condition):
            parsed[key] = value
        else:
            parsed[key] = Condition.model_validate(value)
    return parsed


class Condition(BaseModel):
    """What a field has to be. Several operators in one condition all have to hold (`gt` and `lt`).
    For a relation, `type` and `where` are a pattern for what it points at."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    eq: Any = None
    ne: Any = None
    gt: Any = None
    gte: Any = None
    lt: Any = None
    lte: Any = None
    between: list[Any] | None = None
    in_: list[Any] | None = Field(default=None, alias="in")
    contains: Any = None
    contains_any: list[Any] | None = None
    contains_all: list[Any] | None = None
    starts_with: str | None = None
    exists: StrictBool | None = None
    is_: UUID | None = Field(default=None, alias="is")
    is_any: list[UUID] | None = None
    through: list[str] | None = None
    type: str | None = None
    where: dict[str, Any] | None = None

    @field_validator("where", mode="before")
    @classmethod
    def _where(cls, raw: Any) -> Any:
        return None if raw is None else parse_where(raw, 1)

    def operators(self) -> list[str]:
        """The operators given, by the name they are written with. (`eq: null` is given, though it is `None`)"""
        names = {"in_": "in", "is_": "is"}
        return [
            names.get(name, name)
            for name in self.model_fields_set
            if name not in ("type", "where", "through")
        ]

    @property
    def is_pattern(self) -> bool:
        return "type" in self.model_fields_set or "where" in self.model_fields_set


class Incoming(BaseModel):
    """What refers to an entity: a node of class `type` that fits `where`, with a relation `field` (of that class;
    any relation that can point at the entity, if left out) that points at the entity, through `through`
    wrappers if given."""

    model_config = ConfigDict(extra="forbid")

    type: str
    field: str | None = None
    through: list[str] | None = None
    where: dict[str, Any] | None = None

    @field_validator("where", mode="before")
    @classmethod
    def _where(cls, raw: Any) -> Any:
        return None if raw is None else parse_where(raw, 1)


MAX_ORDER_BY = 3


class OrderBy(BaseModel):
    """What to order the results by: a field of the class (`label`, `year`), or a field of an embedded object
    in one, written with dots (`when.sort_day`). Nodes without a value come last, ascending or descending."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=200)
    direction: Literal["asc", "desc"] = "asc"


class Match(BaseModel):
    """A pattern for a node. `type` is the class searched (the one the search is called on, if it is left out).
    The results are ordered by `order_by` (by label if it is not given), and then by label."""

    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    where: dict[str, Any] = Field(default_factory=dict)
    order_by: list[OrderBy] = Field(default_factory=list, max_length=MAX_ORDER_BY)

    @field_validator("where", mode="before")
    @classmethod
    def _where(cls, raw: Any) -> Any:
        return parse_where(raw)


class SearchRequest(Match):
    """The body of `POST /api/search`: a pattern and the page wanted"""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=MAX_SEARCH_PAGE_SIZE)


Kind = Literal[
    "text",
    "number",
    "decimal",
    "temporal",
    "simple",
    "list",
    "relation",
    "spaces",
    "somewhere",
    "incoming",
]

# The labels of the nodes that stand between a node and what a relation is to: a field typed
# `list[Person | Negative[Person]]` points at a `Negative`, which points at the person
WRAPPER_LABELS = (
    "SemanticSpace",
    "Conjunction",
    "ReifiedRelation",
    "ReifiedRelationDocument",
)

# The fields that are not of one class: any relation of the node, or of any node of its document
ANY_RELATION = "$any"
ANY_IN_DOCUMENT = "$mentions"


@dataclass(frozen=True)
class CheckedCondition:
    """One operator of one field, checked. `kind` is how a backend compares the field: `text`, `number`
    (a `Decimal` too: it is `decimal`), `temporal`, `simple` (a `bool` or an enum), `list` or `relation`.
    `value` is a Python value (a list for `in`, `between`, `contains_any` and so on)."""

    field: str
    kind: Kind
    operator: str
    value: Any
    # (for a relation: it can pass through wrappers, and the names of those that it must pass through)
    wrapped: bool = False
    through: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckedPattern:
    """What a relation has to point at: a node of this class (or a subclass) fitting all of `items`"""

    model: type
    items: list[Expr]


@dataclass(frozen=True)
class CheckedIncoming:
    """A node of the pattern's class that points at an entity with one of the fields (of its class)"""

    pattern: CheckedPattern
    fields: tuple[str, ...]


@dataclass(frozen=True)
class AnyOf:
    """At least one of the branches holds (each branch is a list of expressions that all have to)"""

    branches: list[list[Expr]]


@dataclass(frozen=True)
class Not:
    """The expressions do not all hold"""

    items: list[Expr]


type Expr = CheckedCondition | AnyOf | Not

COMPARING = {"gt", "gte", "lt", "lte", "between"}
OPERATORS: dict[str, set[str]] = {
    "text": {"eq", "ne", "in", "exists", "contains", "starts_with"},
    "number": {"eq", "ne", "in", "exists"} | COMPARING,
    "decimal": {"eq", "ne", "in", "exists"} | COMPARING,
    "temporal": {"eq", "ne", "in", "exists"} | COMPARING,
    "simple": {"eq", "ne", "in", "exists"},
    "list": {"contains", "contains_any", "contains_all", "exists"},
    "relation": {"is", "is_any", "exists"},
    "spaces": set(),
    "somewhere": set(),
    "incoming": set(),
}


# What a head document has that is not one of its fields, and can be searched: whether it is published (a
# document with no property is), and the status of its review (`pangloss-review`)
HEAD_PROPERTIES: dict[str, tuple[Kind, Any]] = {
    "published": ("simple", bool),
    "review_status": ("text", str),
}


def resolve_search_type(name: str) -> type[Document | Entity]:
    """The document or entity class a search is for"""
    from pangloss_models.model_registry import ModelRegistry
    from pangloss_models.utils import model_is_trait

    model = ModelRegistry.all_models().get(name)
    if model is None:
        raise PanglossUnknownTypeError(f"There is no model called '{name}'")
    if (
        model_is_trait(model)
        or not isinstance(model, type)
        or not issubclass(model, (Document, Entity))
    ):
        raise PanglossUnknownTypeError(
            f"'{name}' is not a document or an entity type, so it cannot be searched"
        )
    return model


def without_none(annotation: Any) -> Any:
    """`X | None` is `X`"""
    if typing.get_origin(annotation) in (typing.Union, pytypes.UnionType):
        rest = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(rest) == 1:
            return rest[0]
    return annotation


def resolve_pattern_type(name: str, roots: list[type]) -> type:
    """The class a pattern is for: a document or entity, or (for an embedded field) an embedded class"""
    if roots and all(issubclass(root, Embedded) for root in roots):
        from pangloss_models.model_registry import ModelRegistry

        model = ModelRegistry.all_models().get(name)
        if not (isinstance(model, type) and issubclass(model, Embedded)):
            raise PanglossUnknownTypeError(
                f"There is no embedded model called '{name}'"
            )
        return model
    return resolve_search_type(name)


def kind_of(base: Any) -> Kind | None:
    if base is str:
        return "text"
    if base is bool:
        return "simple"
    if base in (int, float):
        return "number"
    if base is Decimal:
        return "decimal"
    if base in (datetime.date, datetime.datetime):
        return "temporal"
    if isinstance(base, type) and issubclass(base, enum.Enum):
        return "simple"
    return None


def checked_value(base: Any, kind: str, value: Any, where: str) -> Any:
    """The value as the Python value of the type of the field (a `Decimal` as a float, which is how it is compared)"""
    strict = base in (str, bool, int, float)
    try:
        converted = TypeAdapter(base).validate_python(value, strict=strict)
    except ValidationError:
        raise PanglossSearchError(
            f"{where}: {value!r} is not a valid {getattr(base, '__name__', base)}"
        )
    if kind == "decimal":
        return float(converted)
    if isinstance(converted, enum.Enum):
        return converted.value
    return converted


def many(values: list, label: str, where: str) -> list:
    if not values:
        raise PanglossSearchError(f"{where}: '{label}' needs at least one value")
    if len(values) > MAX_VALUES:
        raise PanglossSearchError(
            f"{where}: '{label}' has more than {MAX_VALUES} values"
        )
    return values


@dataclass(frozen=True)
class CheckedOrder:
    path: tuple[str, ...]
    """The embedded fields to go through, from the node (the names of the edges)"""
    field: str
    kind: Kind
    descending: bool


ORDERABLE: set[str] = {"text", "number", "decimal", "temporal"}


def check_order(model: type, order_by: list[OrderBy]) -> list[CheckedOrder]:
    """Whether each field to order by is a field with one value to compare: a text, a number or a date of the
    class, or of an embedded object in it (the class the field is typed with must have it)"""
    checked: list[CheckedOrder] = []
    for order in order_by:
        *through, leaf = order.field.split(".")
        current = model
        for step in through:
            definition = current._meta.fields.get(step)  # type: ignore
            declared = getattr(definition, "annotated_type", None)
            if not isinstance(definition, EmbeddedFieldDefinition) or not (
                isinstance(declared, type) and issubclass(declared, Embedded)
            ):
                raise PanglossSearchError(
                    f"order_by {order.field}: '{step}' is not an embedded object of {current.__name__}"
                )
            current = declared
        if leaf == "label" and not through:
            kind: Kind = "text"
        else:
            definition = current._meta.fields.get(leaf)  # type: ignore
            if not isinstance(definition, LiteralFieldDefinition):
                raise PanglossSearchError(
                    f"order_by {order.field}: {current.__name__} has no field '{leaf}' with a single value"
                )
            found = kind_of(without_none(definition.annotated_type))
            if found not in ORDERABLE:
                raise PanglossSearchError(
                    f"order_by {order.field}: a field of this type cannot be ordered by"
                )
            kind = found
        checked.append(
            CheckedOrder(tuple(through), leaf, kind, order.direction == "desc")
        )
    return checked


def check_match(model: type[Document | Entity], match: Match) -> list[Expr]:
    """The conditions of a pattern (all of which have to hold), checked against the model searched. Raises
    `PanglossSearchError` for anything that is wrong or not supported (yet), naming the field and the operator."""
    if match.type not in (None, model.__name__):
        raise PanglossSearchError(
            f"The pattern is for '{match.type}', but the search is of '{model.__name__}'"
        )
    return check_where(model, match.where, [0, 0], "", True)


def check_where(
    model: type,
    where: dict[str, Any],
    budget: list[int],
    path: str,
    top: bool = False,
) -> list[Expr]:
    """`budget` counts, in the whole search, the patterns for what relations point at and the expressions.
    `top` is the node the search is of (a head document or an entity), not one found by a relation"""
    if len(where) > MAX_CONDITIONS:
        raise PanglossSearchError(f"More than {MAX_CONDITIONS} fields in one pattern")
    fields = model._meta.fields  # type: ignore
    checked: list[Expr] = []
    for name, condition in where.items():
        budget[1] += 1
        if budget[1] > MAX_EXPRESSIONS:
            raise PanglossSearchError(
                f"More than {MAX_EXPRESSIONS} conditions in one search"
            )
        if name == "$all":
            for each in condition:
                checked.extend(check_where(model, each, budget, path, top))
            continue
        if name == "$any_of":
            checked.append(
                AnyOf(
                    [check_where(model, each, budget, path, top) for each in condition]
                )
            )
            continue
        if name == "$not":
            checked.append(Not(check_where(model, condition, budget, path, top)))
            continue
        if name == "$spaces":
            checked.append(check_spaces(model, condition, top, path))
            continue
        if name == "$incoming":
            for each in condition:
                checked.append(check_incoming(model, each, budget, path))
            continue
        if name == "$somewhere":
            for each in condition:
                checked.append(check_somewhere(model, each, budget, path, top))
            continue
        if name in (ANY_RELATION, ANY_IN_DOCUMENT):
            checked.extend(check_anywhere(model, name, condition, budget, path, top))
            continue
        field = f"{path}{name}"
        given = condition.operators()
        if not given and not condition.is_pattern and condition.through is None:
            raise PanglossSearchError(f"{field}: no condition is given")
        if (
            name == "label"
        ):  # (every document and entity has one; it is not one of the fields)
            kind, base = "text", str
        elif (
            top
            and name in HEAD_PROPERTIES
            and name not in fields
            and issubclass(model, Document)
        ):
            # (of a head document: whether it is published, and its review status; see docs/review.md)
            kind, base = HEAD_PROPERTIES[name]
        else:
            kind, base = kind_and_base(model, name, fields.get(name), field)
        if kind == "relation":
            checked.extend(
                check_relation(name, field, cast(Reach, base), condition, budget)
            )
            continue
        if condition.is_pattern or condition.through is not None:
            raise PanglossSearchError(
                f"{field}: 'type', 'where' and 'through' are for relations only"
            )
        for operator in given:
            checked.append(check_operator(name, field, kind, base, condition, operator))
    return checked


def check_operator(
    name: str, field: str, kind: Kind, base: Any, condition: Condition, operator: str
) -> CheckedCondition:
    where = f"{field}.{operator}"
    if operator not in OPERATORS[kind]:
        raise PanglossSearchError(
            f"{where}: not an operator for this field ({kind}); it takes "
            f"{', '.join(sorted(OPERATORS[kind]))}"
        )
    value = getattr(
        condition,
        "in_" if operator == "in" else "is_" if operator == "is" else operator,
    )
    return CheckedCondition(
        name, kind, operator, check_operand(kind, base, operator, value, where)
    )


@dataclass(frozen=True)
class Reach:
    """What a relation field can point at: the classes (of documents and entities) at the end of it, and
    whether it can go through wrappers (semantic spaces, conjunctions, reified relations) on the way"""

    options: list[type]
    wrapped: bool


def check_relation(
    name: str,
    field: str,
    reach: Reach | None,
    condition: Condition,
    budget: list[int],
) -> list[CheckedCondition]:
    """The conditions on a relation: by id, by a pattern for what it points at, whether it has any, and
    which wrappers it must pass through. `reach` is `None` for any relation of a node (`$any`)."""
    wrapped = True if reach is None else reach.wrapped
    through = check_through(field, condition.through, wrapped)
    checked: list[CheckedCondition] = []
    if condition.is_pattern:
        pattern = check_pattern(
            field, None if reach is None else reach.options, condition, budget
        )
        checked.append(
            CheckedCondition(name, "relation", "match", pattern, wrapped, through)
        )
    for operator in condition.operators():
        where = f"{field}.{operator}"
        if operator not in OPERATORS["relation"]:
            raise PanglossSearchError(
                f"{where}: not an operator for this field (relation); it takes "
                f"{', '.join(sorted(OPERATORS['relation']))}, and 'type', 'where' and 'through'"
            )
        value = getattr(condition, "is_" if operator == "is" else operator)
        checked.append(
            CheckedCondition(
                name,
                "relation",
                operator,
                check_operand("relation", None, operator, value, where),
                wrapped,
                through,
            )
        )
    if not checked:
        if not through:
            raise PanglossSearchError(f"{field}: no condition is given")
        # (`through` alone: there is a relation, and it passes through these)
        checked.append(
            CheckedCondition(name, "relation", "exists", True, wrapped, through)
        )
    return checked


def check_through(
    field: str, names: list[str] | None, wrapped: bool
) -> tuple[str, ...]:
    """The wrappers a relation must pass through: models that are semantic spaces, conjunctions or reified relations"""
    if names is None:
        return ()
    from pangloss_models.model_registry import ModelRegistry

    if not wrapped:
        raise PanglossSearchError(
            f"{field}.through: this relation does not pass through semantic spaces, conjunctions or reified relations"
        )
    if not names or len(names) > MAX_VALUES:
        raise PanglossSearchError(f"{field}.through: needs the names of wrappers")
    models = ModelRegistry.all_models()
    for name in names:
        model = models.get(name)
        if getattr(model, "__metatype__", None) not in WRAPPER_LABELS:
            raise PanglossSearchError(
                f"{field}.through: '{name}' is not a semantic space, conjunction or reified relation"
            )
    return tuple(names)


def check_anywhere(
    model: type,
    name: str,
    condition: Condition,
    budget: list[int],
    path: str,
    top: bool,
) -> list[CheckedCondition]:
    """`$any`: any relation of this node. `$mentions`: any relation of any node of this document (a head document
    only). Both take what a relation does (`is`, `is_any`, a pattern, `through`). `$any` also takes `contains` and
    `starts_with`, which are of the label (there is no text index over the other fields yet)."""
    field = f"{path}{name}"
    if name == ANY_IN_DOCUMENT and not (top and issubclass(model, Document)):
        raise PanglossSearchError(
            f"{field}: only for a search of documents, and not inside a pattern for what a relation points at"
        )
    if name == ANY_IN_DOCUMENT and "exists" in condition.model_fields_set:
        raise PanglossSearchError(f"{field}.exists: not an operator here")
    text = [o for o in condition.operators() if o in ("contains", "starts_with")]
    if text and name == ANY_IN_DOCUMENT:
        raise PanglossSearchError(f"{field}.{text[0]}: not an operator here")
    if "exists" in condition.model_fields_set:
        raise PanglossSearchError(f"{field}.exists: not an operator here")
    checked = [
        check_operator("label", f"{path}label", "text", str, condition, operator)
        for operator in text
    ]
    rest = condition.model_copy()
    for operator in text:
        rest.model_fields_set.discard(operator)
    if rest.operators() or rest.is_pattern or rest.through is not None:
        checked.extend(check_relation(name, field, None, rest, budget))
    if not checked:
        raise PanglossSearchError(f"{field}: no condition is given")
    return checked


def check_incoming(
    model: type, item: Incoming, budget: list[int], path: str
) -> CheckedCondition:
    """`$incoming`: the entity is pointed at by a node of a class (and pattern), by one of its relations"""
    field = f"{path}$incoming"
    if not issubclass(model, Entity):
        raise PanglossSearchError(f"{field}: only an entity is referred to")
    budget[0] += 1
    if budget[0] > MAX_PATTERNS:
        raise PanglossSearchError(
            f"More than {MAX_PATTERNS} patterns for what a relation points at"
        )
    try:
        source = resolve_search_type(item.type)
    except PanglossUnknownTypeError as error:
        raise PanglossSearchError(f"{field}: {error}")
    # (the relations of the source that can point at this entity, and whether through wrappers)
    reaching: dict[str, bool] = {}
    for name, definition in source._meta.fields.relation_fields.items():
        found: list[type] = []
        wrapped = [False]
        try:
            for option in definition.type_options:
                leaf_classes(name, option, found, wrapped)
        except PanglossSearchError:
            continue
        if any(issubclass(model, o) or issubclass(o, model) for o in found):
            reaching[name] = wrapped[0]
    if item.field is not None:
        if item.field not in reaching:
            raise PanglossSearchError(
                f"{field}: {item.type} has no relation '{item.field}' that can point at a {model.__name__}"
                + (f" (it has {', '.join(sorted(reaching))})" if reaching else "")
            )
        reaching = {item.field: reaching[item.field]}
    elif not reaching:
        raise PanglossSearchError(
            f"{field}: {item.type} has no relation that can point at a {model.__name__}"
        )
    through = check_through(field, item.through, any(reaching.values()))
    pattern = CheckedPattern(
        source, check_where(source, item.where or {}, budget, f"{field}.")
    )
    return CheckedCondition(
        "$incoming",
        "incoming",
        "match",
        CheckedIncoming(pattern, tuple(sorted(reaching))),
        any(reaching.values()),
        through,
    )


def check_spaces(
    model: type, names: list[str], top: bool, path: str
) -> CheckedCondition:
    """`$spaces`: the node is inside all of these semantic spaces. (Only the nodes inside a space know it: a head
    document is never inside one, and an entity is not part of a document.)"""
    from pangloss_models.model_registry import ModelRegistry

    field = f"{path}$spaces"
    if top or not issubclass(model, Document):
        raise PanglossSearchError(
            f"{field}: only for a pattern for a document that a relation points at (a head document, "
            "and an entity, are not inside a semantic space)"
        )
    models = ModelRegistry.all_models()
    for name in names:
        space = models.get(name)
        if getattr(space, "__metatype__", None) != "SemanticSpace":
            raise PanglossSearchError(f"{field}: '{name}' is not a semantic space")
    return CheckedCondition("$spaces", "spaces", "in", list(names))


def check_somewhere(
    model: type,
    condition: Condition,
    budget: list[int],
    path: str,
    top: bool,
) -> CheckedCondition:
    """`$somewhere`: a document of this type and pattern is anywhere in this document, at any depth"""
    field = f"{path}$somewhere"
    if not (top and issubclass(model, Document)):
        raise PanglossSearchError(
            f"{field}: only for a search of documents, and not inside a pattern for what a relation points at"
        )
    if condition.operators() or condition.through is not None or condition.type is None:
        raise PanglossSearchError(
            f"{field}: each is a pattern ('type', and 'where' if wanted); to ask what a document refers to, use '$mentions'"
        )
    pattern = check_pattern(field, None, condition, budget)
    if not issubclass(pattern.model, Document):
        raise PanglossSearchError(
            f"{field}: '{condition.type}' is not a document type (an entity is not part of a document: "
            "use '$mentions' with its id, or a pattern)"
        )
    return CheckedCondition("$somewhere", "somewhere", "match", pattern)


def check_pattern(
    field: str,
    options: list[type] | None,
    condition: Condition,
    budget: list[int],
) -> CheckedPattern:
    """The pattern for what a relation points at. Its `type` has to be one the relation allows (or a subclass of
    one); it can be left out if the relation allows only one. Without `options` (any relation) it is needed."""
    budget[0] += 1
    if budget[0] > MAX_PATTERNS:
        raise PanglossSearchError(
            f"More than {MAX_PATTERNS} patterns for what a relation points at"
        )
    # (the options include the subclasses of each: the classes that none of the others is a parent of)
    roots = [
        o
        for o in options or []
        if not any(o is not p and issubclass(o, p) for p in options or [])
    ]
    allowed = ", ".join(sorted(o.__name__ for o in roots))
    if condition.type is None:
        if len(roots) != 1:
            raise PanglossSearchError(
                f"{field}: 'type' is needed"
                + (f" (the relation allows {allowed})" if roots else "")
            )
        target = roots[0]
    else:
        try:
            target = resolve_pattern_type(condition.type, roots)
        except PanglossUnknownTypeError as error:
            raise PanglossSearchError(f"{field}: {error}")
        if options is not None and not any(issubclass(target, o) for o in roots):
            raise PanglossSearchError(
                f"{field}: '{condition.type}' is not one of the types the relation allows ({allowed})"
            )
    return CheckedPattern(
        target,
        check_where(target, condition.where or {}, budget, f"{field}."),
    )


def kind_and_base(
    model: type, name: str, definition: Any, field: str
) -> tuple[Kind, Any]:
    if definition is None:
        raise PanglossSearchError(f"{field}: {model.__name__} has no field '{name}'")
    if isinstance(definition, LiteralFieldDefinition):
        base = without_none(definition.annotated_type)
        kind = kind_of(base)
        if kind is None:
            raise PanglossSearchError(
                f"{field}: a field of type {base} cannot be searched yet"
            )
        return kind, base
    if isinstance(definition, ListFieldDefinition):
        base = without_none(definition.inner_type)
        if kind_of(base) is None:
            raise PanglossSearchError(
                f"{field}: a list of {base} cannot be searched yet"
            )
        return "list", base
    if isinstance(definition, EmbeddedFieldDefinition):
        # (an embedded object is searched like what a relation points at: a pattern for it, by `type` and `where`)
        # (and also the class the field is typed with, which is not among its options if it is never used on its own)
        options = [o.annotated_type for o in definition.type_options]
        declared = definition.annotated_type
        if isinstance(declared, type) and issubclass(declared, Embedded):
            options.insert(0, declared)
        return "relation", Reach(list(dict.fromkeys(options)), False)
    if isinstance(definition, RelationFieldDefinition):
        found: list[type] = []
        wrapped = [False]
        for option in definition.type_options:
            leaf_classes(field, option, found, wrapped)
        if not found:
            raise PanglossSearchError(f"{field}: this relation cannot be searched yet")
        return "relation", Reach(list(dict.fromkeys(found)), wrapped[0])
    raise PanglossSearchError(f"{field}: this kind of field cannot be searched yet")


def leaf_classes(
    field: str, option: Any, found: list[type], wrapped: list[bool]
) -> None:
    """The classes at the end of a relation, through the wrappers on the way (`Negative[Person]` is a `Person`)"""
    if isinstance(option, (RelationToEntity, RelationToDocument)):
        found.append(option.annotated_type)
    elif isinstance(
        option,
        (
            RelationToSemanticSpace,
            RelationToConjunction,
            RelationToReifiedRelation,
            RelationToReifiedRelationDocument,
        ),
    ):
        wrapped[0] = True
        for parameter in option.parameter_type_options.values():
            for inner in parameter.type_options:
                leaf_classes(field, inner, found, wrapped)
    else:
        raise PanglossSearchError(f"{field}: this relation cannot be searched yet")


def check_operand(kind: str, base: Any, operator: str, value: Any, where: str) -> Any:
    if operator == "exists":
        if not isinstance(value, bool):
            raise PanglossSearchError(f"{where}: needs true or false")
        return value
    if kind == "relation":
        return many(value, operator, where) if operator == "is_any" else value
    if operator == "starts_with":
        return value.lower()
    if kind == "list":
        if operator in ("contains_any", "contains_all"):
            return [
                checked_value(base, kind_of(base) or "", item, where)
                for item in many(value, operator, where)
            ]
        return checked_value(base, kind_of(base) or "", value, where)
    if operator == "contains":  # (text)
        if not isinstance(value, str) or not value:
            raise PanglossSearchError(f"{where}: needs some text")
        return value.lower()
    if operator == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise PanglossSearchError(f"{where}: needs a list of two values")
        return [checked_value(base, kind, item, where) for item in value]
    if operator == "in":
        return [
            checked_value(base, kind, item, where)
            for item in many(value, operator, where)
        ]
    return checked_value(base, kind, value, where)
