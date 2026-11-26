"""What `initialise` makes of the declarations: the classes of each `DerivedEdge` class, and each rule checked against the
models and made into the parts its queries are made of (`CheckedRule`), with the table of what can trigger it.

A rule's body is a set of **nodes** (one for each pattern, one for each variable of an entity or a document, one for a
pattern nested in another that has a variable in it), the **relations** between them that bind a variable (`Edge`), the
**values** that bind a literal variable, and the conditions of each node that bind nothing (compiled as a search's are).
"""

import dataclasses
import hashlib
import json
import logging
import typing
from collections.abc import Sequence
from typing import Any, Literal

from pangloss_models.field_definitions import (
    EmbeddedFieldDefinition,
    LiteralFieldDefinition,
    RelationFieldDefinition,
    RelationToConjunction,
    RelationToDocument,
    RelationToReifiedRelation,
    RelationToReifiedRelationDocument,
    RelationToSemanticSpace,
)
from pangloss_models import (
    AnyOf,
    Document,
    Embedded,
    Entity,
    ModelRegistry,
    Not,
    PanglossSearchError,
    Var,
)
from pangloss_models.exceptions import did_you_mean
from pangloss_models.spaces import registered_grounds, registered_spaces
from pangloss_models.search import (
    WRAPPER_LABELS,
    CheckedCondition,
    CheckedEdge,
    CheckedPattern,
    CheckedStep,
    Expr,
    RuleKey,
    check_where,
    checking_rule,
    conditions_of,
    kind_of,
    parse_where,
    without_none,
)
from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from pangloss_derived.declare import (
    SLOT,
    Body,
    Constraint,
    DerivedEdge,
    DerivedField,
    DerivedMeta,
    Distinct,
    Head,
    Object,
    PerJustification,
    Rule,
    RuleType,
    Same,
    Subject,
    SymmetricLabel,
    Unordered,
    derivation_of,
    exclusive_with,
    is_exclusive,
)
from pangloss_derived.documents import (
    is_derived_document,
    settings_of,
    source_field,
)
from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError
from pangloss_derived.status import DERIVES, STATUSES, walked_spaces

logger = logging.getLogger("pangloss.derived")


# ---------------------------------------------------------------------------
# What a rule is made of
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Node:
    """A node of the body: `name` is its variable in the query"""

    name: str
    model: type
    filters: list[Expr] = dataclasses.field(default_factory=list)
    pattern: bool = False
    """Of a pattern of the body (not only of a variable): it is a place a rule can be seeded at"""
    top: bool = False
    """Of a pattern of the body itself (not nested in one): its head node is evidence"""
    var: Var | None = None

    @property
    def kind(self) -> Literal["document", "entity", "embedded"]:
        if issubclass(self.model, Entity):
            return "entity"
        if issubclass(self.model, Embedded):
            return "embedded"
        return "document"


@dataclasses.dataclass(frozen=True)
class PathValue:
    """The literal variable `var` is a value met on the way of a relation: the `field` of the wrapper of the step `step`
    (`on` is `node`), of the edge that leaves that wrapper (`edge`), or, with no step, of the edge that reaches what the
    relation is to"""

    step: int | None
    on: Literal["node", "edge"]
    field: str
    var: str


@dataclasses.dataclass(frozen=True)
class Edge:
    """A relation from the node `source`, by its field, to the node `target` (directly, or through wrappers if the field
    can have them; through the wrappers named in `through`, if any are). `steps`: the wrappers of which more is asked
    (`Through`), and `last`: what is asked of the edge that reaches the target; both without the variables, which are
    in `values`"""

    index: int
    source: str
    field: str
    target: str
    wrapped: bool
    through: tuple[str, ...] = ()
    steps: tuple[CheckedStep, ...] = ()
    last: CheckedEdge | None = None
    values: tuple[PathValue, ...] = ()


@dataclasses.dataclass(frozen=True)
class ValueBinding:
    """The value of a field of a node is the literal variable `var` (`many`: the field is a list, and the variable is
    one of its items)"""

    node: str
    field: str
    var: str
    many: bool = False


@dataclasses.dataclass(frozen=True)
class Seed:
    """A place a rule can be seeded at: the node `node`, of the class `model`"""

    rule: str
    node: str
    model: type


@dataclasses.dataclass
class CheckedRule:
    name: str
    rule: Rule
    model: Any
    """What it derives: a `DerivedEdge` class, or (with a `template`) a derived document class"""
    head: dict[str, tuple[Literal["var", "value"], Any]]
    """Each field of the class: a variable (by name), or a value. Of a rule that derives a document: each variable
    of its template, by its own name (what a justification keeps, and its document is filled with)"""
    variables: dict[str, Var]
    nodes: dict[str, Node]
    edges: list[Edge]
    values: list[ValueBinding]
    constraints: list[Constraint]
    patterns: list[str]
    """The node of each pattern, in order: what a justification's `nodes` are"""
    symmetric: tuple[str, str] | None
    """The two variables of the symmetric fields"""
    blocked: frozenset[str]
    transparent: frozenset[str]
    types: tuple[RuleType, ...]
    exclusive: frozenset[str] = frozenset()
    """The wrappers of which one justification takes one member at most"""
    exclusive_with: tuple[tuple[str, str], ...] = ()
    """Of those, the ones that are exclusive together with the others of their document that have the same value of
    a field (`DerivedMeta(exclusive="field")`): the wrapper's name and the field's"""
    symmetric_body: bool = False
    """Whether the body is the same with the two symmetric variables swapped (`same_group`: then each pair is matched once,
    in order of id; otherwise, as with `before(d1, d2)`, both orders are matched and the ends are put in order when the
    fact is written)"""
    hash: str = ""
    template: Any = None
    """Of a rule that derives a document: what it writes (`pangloss_derived.templates.TNode`)"""
    blocked_heads: frozenset[str] = frozenset()
    """The document classes the rule reads nothing inside (`block=[DerivedFactoid]`): a condition on the head of the
    node of each pattern"""
    unordered: tuple[tuple[str, str], ...] = ()
    """The pairs of variables the rule says are interchangeable (`unordered(a, b)`)"""
    forced: frozenset[str] = frozenset()
    """The semantic spaces the rule reads as plain spaces that neither assert nor deny, whatever they say of their
    contents: those whose `DerivedMeta` says `qualify`, and those the rule allows"""
    spaces: dict[str, Any] = dataclasses.field(default_factory=dict)
    """What each space class says of its contents, as this rule's walk reads it (`pangloss_derived.status`)"""
    grounds: dict[str, Any] = dataclasses.field(default_factory=dict)
    """The ground of each head class (`pangloss_models.spaces.registered_grounds`): what the walk of each part starts
    from, and its standing"""
    statuses: frozenset[str] = DERIVES
    """The statuses of the justifications the rule takes"""

    @property
    def document(self) -> bool:
        """Whether it derives documents (not edges)"""
        return self.template is not None

    @property
    def max_per_seed(self) -> int:
        if self.document:
            return settings_of(self.model).max_per_seed
        return self.model._meta.max_per_seed

    @property
    def tops(self) -> list[Node]:
        """The nodes of the patterns of the body that are documents (or parts of them): what its evidence is in"""
        return [
            self.nodes[name]
            for name in dict.fromkeys(self.patterns)
            if self.nodes[name].kind != "entity"
        ]

    @property
    def seeds(self) -> list[Seed]:
        return [
            Seed(self.name, node.name, node.model)
            for node in self.nodes.values()
            if node.pattern
        ]

    @property
    def type_names(self) -> list[str]:
        return [t.name for t in self.types]

    def describe(self) -> str:
        """The rule as Datalog (`explain`)"""
        if self.document:
            from pangloss_derived.templates import describe

            written = describe(self.template)
        else:
            head = ", ".join(
                value if kind == "var" else repr(value)
                for kind, value in self.head.values()
            )
            written = f"{self.model.__name__}({head})"
        parts = []
        for node in self.nodes.values():
            if node.pattern:
                parts.append(f"{node.model.__name__}({node.name})")
        for edge in self.edges:
            via = " via " + "|".join(edge.through) if edge.through else ""
            asked = sum(
                len(s.items) + len(s.edge.items if s.edge else []) for s in edge.steps
            ) + len(edge.last.items if edge.last else [])
            if asked:
                via += f" [{asked} condition{'s' if asked != 1 else ''} on the way]"
            parts.append(f"{edge.field}({edge.source}, {edge.target}){via}")
            for value in edge.values:
                where = (
                    "edge"
                    if value.step is None
                    else edge.steps[value.step].model.__name__
                    + (" edge" if value.on == "edge" else "")
                )
                parts.append(
                    f"{value.field}({edge.field}({edge.source}, {edge.target}) {where}, {value.var})"
                )
        for value in self.values:
            parts.append(f"{value.field}({value.node}, {value.var})")
        parts += [c.describe() for c in self.constraints]
        if self.blocked_heads:
            parts.append(f"not in({', '.join(sorted(self.blocked_heads))})")
        return f"{written} :-\n    " + ",\n    ".join(parts) + "."


# ---------------------------------------------------------------------------
# Derived classes
# ---------------------------------------------------------------------------

LITERALS = {"text", "number", "decimal", "temporal", "simple"}


MARKERS = (Subject, Object, SymmetricLabel, PerJustification)


def wrong(model: type, message: str) -> typing.NoReturn:
    raise PanglossDerivedError(f"{model.__name__}: {message}")


def derived_fields(model: type[DerivedEdge]) -> dict[str, DerivedField]:
    """The fields of a `DerivedEdge` class, from its annotations (and its parents'), each with what it is of the edge:
    an end (`Subject()`, `Object()`; of a symmetric class, the two with a `SymmetricLabel`), a value of each
    justification (`PerJustification()`), or a qualifier"""
    try:
        hints = typing.get_type_hints(model, include_extras=True)
    except NameError as error:
        raise PanglossDerivedError(
            f"{model.__name__}: a field's type cannot be found ({error})"
        ) from None
    symmetric = bool(model._meta.symmetric)
    fields: dict[str, DerivedField] = {}
    labelled = 0
    for name, annotation in hints.items():
        if name.startswith("_") or typing.get_origin(annotation) is typing.ClassVar:
            continue
        if annotation in (typing.ClassVar,) or name in (
            "Meta",
            "Derive",
            "View",
            "Qualifiers",
            "Where",
        ):
            continue
        if name.startswith("pg_") or name in RESERVED:
            wrong(
                model,
                f"a field cannot be called {name!r} (a name of the stored edge, or of its view)",
            )
        markers = [
            m for m in getattr(annotation, "__metadata__", ()) if isinstance(m, MARKERS)
        ]
        for m in getattr(annotation, "__metadata__", ()):
            if m in MARKERS:
                wrong(model, f"{name}: write {m.__name__}(), with the brackets")
        if len(markers) > 1:
            wrong(
                model,
                f"{name}: a field is one thing of the edge, not {' and '.join(type(m).__name__ for m in markers)}",
            )
        marker = markers[0] if markers else None
        bare = (
            typing.get_args(annotation)[0]
            if markers or hasattr(annotation, "__metadata__")
            else annotation
        )
        base = without_none(bare)
        if isinstance(base, type) and issubclass(base, Entity) or is_trait(base):
            kind: Literal["relation", "literal"] = "relation"
        elif kind_of(base) in LITERALS:
            kind = "literal"
        else:
            wrong(
                model,
                f"{name}: a field of a DerivedEdge class is an entity (or a trait of entities) or a "
                f"literal (str, int, a date, an enum...), not {bare!r}",
            )
        role: Any = "qualifier"
        if isinstance(marker, (Subject, Object)):
            if symmetric:
                wrong(
                    model,
                    f'{name}: the ends of a symmetric class are marked with a SymmetricLabel ("member"), not '
                    f"{type(marker).__name__}(): the two are not told apart",
                )
            role = "subject" if isinstance(marker, Subject) else "object"
        elif isinstance(marker, SymmetricLabel):
            if not symmetric:
                wrong(
                    model,
                    f"{name}: a SymmetricLabel is for the two ends of a symmetric class "
                    "(_meta = DerivedEdge.Meta(symmetric=True)); mark the ends of this one Subject() and Object()",
                )
            # (the first is stored as the subject: but which is which means nothing)
            role = "subject" if labelled == 0 else "object"
            labelled += 1
            if labelled > 2:
                wrong(
                    model,
                    "an edge has two ends: three fields have a SymmetricLabel",
                )
        elif isinstance(marker, PerJustification):
            role = "per_justification"
        if role in ("subject", "object") and kind != "relation":
            wrong(
                model,
                f"{name}: an end of an edge is an entity (or a trait of entities), not {bare!r}",
            )
        if role == "per_justification" and kind != "literal":
            wrong(
                model,
                f"{name}: a PerJustification() field is a literal (a value found on the way), not {bare!r}",
            )
        fields[name] = DerivedField(name, kind, base, role)
    if not fields:
        raise PanglossDerivedError(f"{model.__name__} has no fields")
    return fields


# (names of the stored node and of the view, which a field cannot have)
RESERVED = frozenset(
    {
        "id",
        "key",
        "type",
        "ends",
        "qualifiers",
        "symmetric",
        "plain",
        "status",
        "statuses",
        "standing",
        "context_label",
        "context_labels",
        "qualified_only",
        "types",
        "rule_type",
        "justification_count",
        "justifications",
        "derived",
        "derived_at",
        "entity",
        "evidence",
        "page",
        "page_size",
    }
)


def is_trait(model: Any) -> bool:
    from pangloss_models.utils import model_is_trait

    return isinstance(model, type) and model_is_trait(model)


def find_ends(model: type[DerivedEdge]) -> tuple[str, str]:
    """The two ends of the class (the subject and the object), refusing a class without exactly two"""
    fields = model._fields
    subjects = [f for f in fields.values() if f.role == "subject"]
    objects = [f for f in fields.values() if f.role == "object"]
    if model._meta.symmetric:
        if len(subjects) != 1 or len(objects) != 1:
            wrong(
                model,
                "a symmetric class needs its two ends marked, each with the same SymmetricLabel: "
                'first: Annotated[Person, SymmetricLabel("member")]',
            )
        a, b = subjects[0], objects[0]
        if a.model is not b.model:
            wrong(
                model,
                f"the two ends of a symmetric class ({a.name}, {b.name}) must be of the same type",
            )
        return a.name, b.name
    if len(subjects) != 1 or len(objects) != 1:
        found = (
            f"{len(subjects)} Subject() and {len(objects)} Object()"
            if subjects or objects
            else "none"
        )
        wrong(
            model,
            "an edge has two ends: one field marked Subject() and one Object() "
            f"(giver: Annotated[Agent, Subject()]); this has {found}. Any other field qualifies the edge",
        )
    return subjects[0].name, objects[0].name


def symmetric_fields(model: type[DerivedEdge]) -> tuple[str, str] | None:
    """The two ends of a symmetric class"""
    return model._ends if model._meta.symmetric else None


def end_markers(model: type[DerivedEdge]) -> tuple[str | None, str | None]:
    """The `SymmetricLabel` of a symmetric class's ends (one name: both must say the same), and the `reverse_name` of an
    asymmetric class's object"""
    hints = typing.get_type_hints(model, include_extras=True)

    def marker(name: str, kind: type) -> Any:
        return next(
            (
                m
                for m in getattr(hints[name], "__metadata__", ())
                if isinstance(m, kind)
            ),
            None,
        )

    subject, object_ = model._ends
    if model._meta.symmetric:
        found = {marker(name, SymmetricLabel).name for name in (subject, object_)}
        if len(found) > 1:
            wrong(
                model,
                f"the two ends ({subject}, {object_}) have different SymmetricLabels: {sorted(found)}",
            )
        label = found.pop()
        if not label.isidentifier():
            wrong(
                model,
                f"a SymmetricLabel is a name (letters, digits and _): not {label!r}",
            )
        return label, None
    return None, marker(object_, Object).reverse_name


def ends_of(model: type[DerivedEdge]) -> tuple[str, str]:
    """The two fields that are the edge: the subject and the object"""
    return model._ends


class DeriveBase(BaseModel):
    """The head of a rule: `SameFamily.Derive(first=a, second=b, family=f)`, then `.when(...)`"""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    _derived: typing.ClassVar[type[DerivedEdge]]
    # (its stub has its `__init__` written out, so that a type checker checks the variables: `pangloss_models.typestubs`)
    _stub_init: typing.ClassVar[bool] = True

    def when(
        self,
        *items: Any,
        block: Any = (),
        allow: Any = (),
        status: Sequence[str] | None = None,
    ) -> Body:
        head = Head(
            type(self)._derived,
            {name: getattr(self, name) for name in type(self).model_fields},
        )
        return head.when(*items, block=block, allow=allow, status=status)


def make_derive(model: type[DerivedEdge]) -> None:
    fields: dict[str, Any] = {}
    for field in model._fields.values():
        variable = Var[field.model]  # (made at runtime: the type is the field's)
        fields[field.name] = (
            (variable, ...)
            if field.kind == "relation"
            else (variable | field.model, ...)
        )
    derive = create_model(
        f"{model.__name__}Derive",
        __base__=DeriveBase,
        __module__=model.__module__,
        __doc__=f"The head of a rule that derives a {model.__name__}",
        **fields,
    )
    derive._derived = model
    model.Derive = derive


def initialise_classes() -> None:
    from pangloss_derived.views import make_views

    for model in DerivedRegistry.classes.values():
        model._fields = derived_fields(model)
    for model in DerivedRegistry.classes.values():
        if model._meta.abstract and not any(
            f.role in ("subject", "object") for f in model._fields.values()
        ):
            # (an abstract parent may leave the ends to its subclasses: nothing is derived as it)
            continue
        try:
            model._ends = find_ends(model)
        except PanglossDerivedError:
            if model._meta.abstract:
                # (with one end only: its subclasses give the other)
                continue
            raise
        model._symmetric_label, model._reverse_name = end_markers(model)
        make_derive(model)
        make_views(model)
    # (a reverse name is a key of an entity's `_derived`, beside the names of the classes)
    names: dict[str, str] = {name: name for name in DerivedRegistry.classes}
    for model in DerivedRegistry.concrete_classes().values():
        reverse = model._reverse_name
        if reverse is None:
            continue
        if reverse in names and names[reverse] != model.__name__:
            wrong(
                model,
                f"the reverse_name {reverse!r} is also "
                + (
                    "the name of a derived class"
                    if names[reverse] == reverse
                    else f"the reverse_name of {names[reverse]}"
                ),
            )
        names[reverse] = model.__name__
    check_shortcut_names()


# The edges the core and this package write that are of no field
INTERNAL_EDGES = {
    "has_url",
    "is_creation_of",
    "is_update_of",
    "is_deletion_of",
    "is_undeletion_of",
    "created_by",
    "updated_by",
    "justifies",
    "evidence",
}


def check_shortcut_names() -> None:
    """A class with `Meta(shortcut=True)` has an edge of its name between two entities. The core tells the edges of
    the fields of the models by their names (a migration that renames a field, a merge that moves it), so the name of
    the class must be none of them"""
    shortcuts = [
        model
        for model in DerivedRegistry.concrete_classes().values()
        if model._meta.shortcut
    ]
    if not shortcuts:
        return
    taken: dict[str, str] = {name: "an edge Pangloss keeps" for name in INTERNAL_EDGES}
    for model in ModelRegistry.all_models().values():
        fields = getattr(getattr(model, "_meta", None), "fields", None)
        for name, definition in getattr(fields, "relation_fields", {}).items():
            taken.setdefault(name, f"the field {model.__name__}.{name}")
            reverse = getattr(definition, "reverse_name", None)
            if reverse:
                taken.setdefault(
                    reverse, f"the reverse name of {model.__name__}.{name}"
                )
    for model in shortcuts:
        if model.__name__ in taken:
            wrong(
                model,
                f"it has shortcut=True, and its name is also {taken[model.__name__]}: a shortcut edge is stored "
                "under the name of its class, which has to be the name of no relation",
            )


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def fail(rule: str, message: str) -> typing.NoReturn:
    raise PanglossDerivedError(f"Rule {rule}: {message}")


def wrapper_models() -> list[type]:
    """The semantic spaces, conjunctions and reified relations (not their forms with a type: `Negative`, not
    `Negative[Statement]`, which is stored as a `Negative`)"""
    return [
        model
        for model in ModelRegistry.all_models().values()
        if getattr(model, "__metatype__", None) in WRAPPER_LABELS
        and not (getattr(model, "__pydantic_generic_metadata__", None) or {}).get(
            "origin"
        )
    ]


def exclusive_together() -> tuple[tuple[str, str], ...]:
    """The wrappers that are exclusive together by a field (`DerivedMeta(exclusive="field")`), each with the field,
    which must be a literal of the class"""
    found = []
    for model in wrapper_models():
        field = exclusive_with(model)
        if field is None:
            continue
        definition = (getattr(getattr(model, "_meta", None), "fields", None) or {}).get(
            field
        )
        if not isinstance(definition, LiteralFieldDefinition):
            raise PanglossDerivedError(
                f"{model.__name__}: DerivedMeta(exclusive={field!r}) names a field by which its wrappers are"
                f" exclusive together, and {model.__name__} has no literal field `{field}`"
            )
        found.append((model.__name__, field))
    return tuple(sorted(found))


def wrapper_settings(
    body: Body, document: bool = False
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """The names of the wrappers that this rule does not derive through (`block`), those it does not record
    (`transparent`), and the semantic spaces it reads as plain spaces that neither assert nor deny, whatever they
    say of their contents (`forced`): what their `DerivedMeta` says, but for the rule's own `block` and `allow`.

    A semantic space whose `DerivedMeta` says nothing is read by the walk (`pangloss_derived.status`): what it says
    of its contents decides. One whose `DerivedMeta` says `qualify`, or that the rule allows, is forced.

    A rule that derives a document (`document`) derives through a qualifying wrapper only if the rule allows it: a
    fact from a `Negative` statement has a context label, which its reader sees, but a document made from it would
    plainly say what the source denied. A space that says something of its contents (that they are so, that they
    are not, a modality) is not blocked on that account: the walk decides, and only what is asserted makes a
    document"""
    blocked: set[str] = set()
    transparent: set[str] = set()
    forced: set[str] = set()
    said = registered_spaces()
    for model in wrapper_models():
        name = model.__name__
        if any(issubclass(model, b) for b in body.block):
            blocked.add(name)
            continue
        meta = getattr(model, SLOT, None)
        explicit = isinstance(meta, DerivedMeta) and meta.derivation is not None
        derivation = derivation_of(model)
        allowed = any(issubclass(model, a) for a in body.allow)
        # (a space that neither asserts nor denies and is no operator: what every space was before the walk)
        plain_space = name in said and (
            said[name]["veridical"] == 0 and said[name]["logical"] is None
        )
        walked = name in said and not explicit and not allowed and not plain_space
        if allowed and derivation == "block":
            derivation = "qualify"
        elif document and derivation == "qualify" and not allowed and not walked:
            derivation = "block"
        if derivation == "block":
            blocked.add(name)
        elif derivation == "transparent":
            transparent.add(name)
        elif name in said and (explicit or allowed):
            forced.add(name)
    return frozenset(blocked), frozenset(transparent), frozenset(forced)


def blocked_head_classes(rule: str, body: Body) -> list[type]:
    """The document classes of `block=[...]` (the others are wrappers): the rule reads nothing inside a document of
    one. And what `block` and `allow` cannot name is refused"""
    heads: list[type] = []
    for item in body.block:
        kind = getattr(item, "__metatype__", None)
        if kind in WRAPPER_LABELS:
            continue
        if kind == "Document" and isinstance(item, type) and issubclass(item, Document):
            heads.append(item)
            continue
        fail(
            rule,
            f"block=[{getattr(item, '__name__', item)!s}]: block names a semantic space or other wrapper (derive "
            "nothing through it), or a document class (read nothing inside a document of it)",
        )
    for item in body.allow:
        if getattr(item, "__metatype__", None) not in WRAPPER_LABELS:
            fail(
                rule,
                f"allow=[{getattr(item, '__name__', item)!s}]: allow names a semantic space or other wrapper",
            )
    return heads


def statuses_of(rule: str, body: Body) -> frozenset[str]:
    """The statuses of the justifications the rule takes: those of `.when(..., status=[...])`, or by default
    `DERIVES`. A name that is no status, and an empty list, are refused"""
    given = body.status
    if given is None:
        return DERIVES
    names = ", ".join(STATUSES)
    if isinstance(given, str):
        fail(
            rule,
            f"status={given!r}: status takes a list of the statuses of the justifications the rule takes "
            f"(status=[{given!r}]), of: {names}",
        )
    if not given:
        fail(
            rule,
            f"status=[] takes no justification at all: leave it out for the default "
            f"({', '.join(s for s in STATUSES if s in DERIVES)}), or name some of: {names}",
        )
    for name in given:
        if name not in STATUSES:
            fail(
                rule,
                f"status=[{name!r}]: {name!r} is not a status of a justification (they are: {names})."
                + did_you_mean(str(name), STATUSES),
            )
    return frozenset(given)


def path_has_variable(e: CheckedCondition) -> bool:
    """Whether a variable is on the way of the relation: in a `Through`, or in what is asked of its last edge"""
    return any(
        has_variable(step.items)
        or (step.edge is not None and has_variable(step.edge.items))
        for step in e.steps
    ) or (e.edge is not None and has_variable(e.edge.items))


def has_variable(exprs: list[Expr]) -> bool:
    for e in exprs:
        if isinstance(e, CheckedCondition):
            if e.operator == "var":
                return True
            if e.kind == "relation" and path_has_variable(e):
                return True
            if isinstance(e.value, CheckedPattern) and has_variable(e.value.items):
                return True
        elif isinstance(e, AnyOf):
            if any(has_variable(b) for b in e.branches):
                return True
        elif isinstance(e, Not) and has_variable(e.items):
            return True
    return False


def own_variable(exprs: list[Expr]) -> Var | None:
    """The variable of `$is`, if the pattern has one"""
    for e in exprs:
        if (
            isinstance(e, CheckedCondition)
            and e.field == RuleKey.IS
            and e.operator == "var"
        ):
            return e.value
    return None


class Builder:
    """Makes the nodes, edges and values of a rule from its checked patterns"""

    def __init__(self, name: str, variables: dict[str, Var]):
        self.name = name
        self.variables = variables
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.values: list[ValueBinding] = []
        self.anonymous = 0
        self.own: dict[str, int] = {}
        """How many patterns each variable is the node of (`is_`)"""

    def node_of(self, variable: Var, model: type) -> Node:
        """The node of a variable of an entity or a document (made when first met). Its class is the narrower of what
        it is declared as and what a place it is at holds"""
        name = f"v_{variable.name}"
        node = self.nodes.get(name)
        if node is None:
            node = Node(name, variable.model, var=variable)
            self.nodes[name] = node
        if isinstance(model, type) and issubclass(model, node.model):
            node.model = model
        return node

    def pattern(self, model: type, exprs: list[Expr], top: bool) -> Node:
        variable = own_variable(exprs)
        if variable is not None:
            node = self.node_of(variable, model)
            self.own[variable.name] = self.own.get(variable.name, 0) + 1
        else:
            name = f"n_{self.anonymous}"
            self.anonymous += 1
            node = Node(name, model)
            self.nodes[name] = node
        node.pattern = True
        node.top = node.top or top
        self.absorb(node, exprs)
        return node

    def absorb(self, node: Node, exprs: list[Expr]) -> None:
        for e in exprs:
            if not isinstance(e, CheckedCondition):
                node.filters.append(e)
                continue
            if e.operator == "var":
                if e.kind == "self":
                    continue
                if e.kind == "relation":
                    variable: Var = e.value
                    target = self.node_of(variable, variable.model)
                    self.edges.append(
                        Edge(
                            len(self.edges),
                            node.name,
                            e.field,
                            target.name,
                            e.wrapped,
                            e.through,
                            *self.way(e),
                        )
                    )
                else:
                    self.values.append(
                        ValueBinding(node.name, e.field, e.value.name, e.kind == "list")
                    )
                continue
            if (
                e.kind == "relation"
                and e.operator == "match"
                and (has_variable(e.value.items) or path_has_variable(e))
            ):
                pattern: CheckedPattern = e.value
                inner = self.pattern(pattern.model, pattern.items, top=False)
                # (a nested document is part of the one it is in; an entity with conditions of its own can be seeded)
                inner.pattern = inner.kind == "entity" and bool(inner.filters)
                self.edges.append(
                    Edge(
                        len(self.edges),
                        node.name,
                        e.field,
                        inner.name,
                        e.wrapped,
                        e.through,
                        *self.way(e),
                    )
                )
                continue
            if e.kind == "relation" and path_has_variable(e):
                fail(
                    self.name,
                    f"{e.field}: a variable on the way of a relation (in a Through, or in edge=) needs the relation to "
                    "say what it is to with a variable or a pattern (is_=a, or a Where), and nothing else: "
                    f"not '{e.operator}'",
                )
            node.filters.append(e)

    def way(
        self, e: CheckedCondition
    ) -> tuple[tuple[CheckedStep, ...], CheckedEdge | None, tuple[PathValue, ...]]:
        """What is asked on the way of a relation, with the variables taken out as the values they bind"""
        values: list[PathValue] = []

        def without_variables(
            items: list[Expr], step: int | None, on: Literal["node", "edge"]
        ) -> list[Expr]:
            kept: list[Expr] = []
            for item in items:
                if isinstance(item, CheckedCondition) and item.operator == "var":
                    if item.kind == "list":
                        fail(
                            self.name,
                            f"{e.field}: {item.field} is a list: a variable on the way of a relation is of a field "
                            "of one value",
                        )
                    values.append(PathValue(step, on, item.field, item.value.name))
                else:
                    kept.append(item)
            return kept

        steps = tuple(
            CheckedStep(
                step.model,
                without_variables(step.items, index, "node"),
                None
                if step.edge is None
                else CheckedEdge(
                    step.edge.model, without_variables(step.edge.items, index, "edge")
                ),
            )
            for index, step in enumerate(e.steps)
        )
        last = (
            None
            if e.edge is None
            else CheckedEdge(
                e.edge.model, without_variables(e.edge.items, None, "edge")
            )
        )
        return steps, last, tuple(values)


def check_rule(rule: Rule) -> CheckedRule:
    """Call the rule's function with its variables, and check what it gives against the models"""
    try:
        variables = rule.variables()
    except TypeError as error:
        raise PanglossDerivedError(str(error)) from None
    try:
        body = rule.function(**variables)
    except ValidationError as error:
        fail(rule.name, f"the head is not right: {error}")
    except PanglossDerivedError:
        raise
    if not isinstance(body, Body):
        fail(
            rule.name,
            "the function must give the head and body of the rule: SomeDerived.Derive(...).when(...)",
        )
    model: Any = body.head.model
    document = is_derived_document(model)
    if model._meta.abstract:
        fail(rule.name, f"{model.__name__} is abstract: nothing is derived as it")
    if not body.patterns:
        fail(rule.name, "the body has no pattern")
    heads_blocked = blocked_head_classes(rule.name, body)

    # (the head)
    head: dict[str, tuple[Literal["var", "value"], Any]] = {}
    for name, field in ({} if document else model._fields).items():
        value = body.head.values.get(name)
        if isinstance(value, Var):
            if value.name not in variables or variables[value.name] is not value:
                fail(
                    rule.name,
                    f"{model.__name__}.{name}: {value!r} is not a variable of the rule",
                )
            if field.kind == "relation":
                if not isinstance(value.model, type) or not (
                    issubclass(value.model, field.model)
                    or issubclass(field.model, value.model)
                ):
                    fail(
                        rule.name,
                        f"{model.__name__}.{name}: a Var[{value.model.__name__}] cannot be a {field.model.__name__}",
                    )
            elif value.model is not field.model:
                fail(
                    rule.name,
                    f"{model.__name__}.{name}: a Var[{getattr(value.model, '__name__', value.model)}] cannot be a "
                    f"{field.model.__name__}",
                )
            head[name] = ("var", value.name)
        else:
            # (a relation is a variable: `Derive` refuses anything else)
            head[name] = ("value", value)

    # (the patterns)
    builder = Builder(rule.name, variables)
    patterns: list[str] = []
    for index, where in enumerate(body.patterns):
        pattern_model = type(where)._model
        if pattern_model is None:
            fail(rule.name, f"pattern {index + 1} is not the Where of a model")
        try:
            with checking_rule(variables):
                checked = check_where(
                    pattern_model, parse_where(where), [0, 0], "", False
                )
        except PanglossSearchError as error:
            fail(rule.name, f"pattern {index + 1}, {pattern_model.__name__}: {error}")
        except ValueError as error:
            fail(rule.name, f"pattern {index + 1}, {pattern_model.__name__}: {error}")
        # (`via` has no variables yet, and a rule's own compiler does not read it: refused, not left out)
        if any(condition.via for condition in conditions_of(checked)):
            fail(
                rule.name,
                f"pattern {index + 1}, {pattern_model.__name__}: `via` is not for the body of a rule yet "
                "(use `through` and `edge`)",
            )
        # (a rule's own compiler names a wrapper of the way in a list predicate, from which a pattern is not tested of
        # it on Memgraph: `InRole.role` asked in a step is refused, not left out)
        asked = [
            (condition, step, inner)
            for condition in conditions_of(checked)
            for step in condition.steps
            for inner in conditions_of(step.items)
            if inner.kind == "relation"
        ]
        if asked:
            condition, step, inner = asked[0]
            fail(
                rule.name,
                f"pattern {index + 1}, {pattern_model.__name__}: "
                f"{condition.field}.through.{step.model.__name__}.{inner.field}: a relation of a wrapper is not "
                "tested in the body of a rule yet",
            )
        node = builder.pattern(pattern_model, checked, top=True)
        patterns.append(node.name)

    # (of a derived document: its template, checked now that the class of each variable is known)
    template = None
    if document:
        from pangloss_derived.templates import TemplateCheck

        checker = TemplateCheck(
            rule.name,
            variables,
            {n.var.name: n.model for n in builder.nodes.values() if n.var is not None},
        )
        template = checker.head(body.head.template, model)
        head = {name: ("var", name) for name in checker.used}
        if not any(builder.nodes[name].kind != "entity" for name in patterns):
            fail(
                rule.name,
                f"no pattern of the body is of a document: a {model.__name__} rests on the documents its patterns "
                "are found in, and would have no source",
            )

    # (the variables: each bound by a pattern, each of the head among them)
    bound_nodes = {n.var.name for n in builder.nodes.values() if n.var is not None}
    bound_values = {v.var for v in builder.values} | {
        v.var for e in builder.edges for v in e.values
    }
    bound = bound_nodes | bound_values
    for name, (kind, value) in head.items():
        if kind == "var" and value not in bound:
            fail(
                rule.name,
                f"the variable {value!r} (of "
                + (
                    f"the template of {model.__name__}"
                    if document
                    else f"{model.__name__}.{name}"
                )
                + ") is in no pattern of the body",
            )
    constraints = list(body.constraints)
    for constraint in constraints:
        for variable in constraint.variables():
            if variable.name not in bound:
                fail(
                    rule.name,
                    f"the variable {variable.name!r} of {constraint.describe()} is in no pattern of the body",
                )
        problem = constraint.check()
        if problem:
            fail(rule.name, f"{constraint.describe()}: {problem}")
    for name in variables:
        if name not in bound:
            fail(rule.name, f"the variable {name!r} is in no pattern of the body")
    used = count_uses(builder)
    in_head = {value for kind, value in head.values() if kind == "var"}
    in_constraints = {v.name for c in constraints for v in c.variables()}
    for name, uses in used.items():
        if uses == 1 and name not in in_head and name not in in_constraints:
            logger.warning(
                "Rule %s: the variable %r is used once (it joins nothing: is it a mistake?)",
                rule.name,
                name,
            )

    # (the two of a symmetric class are in order of id, and so never the same: see `compile`)
    symmetric = None
    pair = None if document else symmetric_fields(model)
    if pair:
        a, b = (head[f] for f in pair)
        if a[1] == b[1]:
            fail(
                rule.name,
                f"the two symmetric fields of {model.__name__} are the one variable {a[1]!r}",
            )
        symmetric = (a[1], b[1])

    blocked, transparent, forced = wrapper_settings(body, document)
    checked_rule = CheckedRule(
        name=rule.name,
        rule=rule,
        model=model,
        head=head,
        variables=variables,
        nodes=builder.nodes,
        edges=builder.edges,
        values=builder.values,
        constraints=constraints,
        patterns=patterns,
        symmetric=symmetric,
        blocked=blocked,
        transparent=transparent,
        forced=forced,
        spaces=walked_spaces(forced),
        grounds=dict(registered_grounds()),
        statuses=statuses_of(rule.name, body),
        types=rule.types,
        exclusive=frozenset(m.__name__ for m in wrapper_models() if is_exclusive(m)),
        exclusive_with=exclusive_together(),
        template=template,
        blocked_heads=frozenset(m.__name__ for m in heads_blocked),
        unordered=tuple(
            (c.a.name, c.b.name) for c in constraints if isinstance(c, Unordered)
        ),
    )
    if symmetric is not None:
        checked_rule.symmetric_body = body_is_symmetric(checked_rule, *symmetric)
    check_unordered(checked_rule)
    checked_rule.hash = rule_hash(checked_rule)
    return checked_rule


def check_unordered(rule: CheckedRule) -> None:
    """`unordered(a, b)` is refused where the body is not the same with the two swapped (half the pairs would be
    lost: (B, A) is not found as (A, B)); and a rule that derives documents, whose body is the same with two of its
    template's variables swapped, is told that it derives each document twice"""
    for a, b in rule.unordered:
        if not body_is_symmetric(rule, a, b):
            fail(
                rule.name,
                f"unordered({a}, {b}): the body is not the same with {a} and {b} swapped, so one order of a pair "
                "would be found and the other lost. It is for two variables the patterns and constraints treat "
                "alike",
            )
    if not rule.document:
        return
    said = {frozenset(pair) for pair in rule.unordered}
    names = [name for name in rule.head if f"v_{name}" in rule.nodes]
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if frozenset((a, b)) in said:
                continue
            if rule.nodes[f"v_{a}"].model is not rule.nodes[f"v_{b}"].model:
                continue
            if body_is_symmetric(rule, a, b):
                logger.warning(
                    "Rule %s: the body is the same with %s and %s swapped, so each pair is found in both orders "
                    "and gives two documents that say one thing: add unordered(%s, %s)",
                    rule.name,
                    a,
                    b,
                    a,
                    b,
                )


def swapped_names(data: Any, swap: dict[str, str]) -> Any:
    """`plain` data with the variables renamed"""
    if isinstance(data, dict):
        if set(data) == {"var"}:
            return {"var": swap.get(data["var"], data["var"])}
        return {k: swapped_names(v, swap) for k, v in data.items()}
    if isinstance(data, list):
        return [swapped_names(v, swap) for v in data]
    return data


def constraint_shape(constraint: Constraint, swap: dict[str, str]) -> str:
    """A constraint as text, with the variables renamed; one that is of its variables in any order (`distinct`, `same`,
    `unordered`, which is of the pair) has them in order of name"""
    if isinstance(constraint, (Distinct, Same, Unordered)):
        names = sorted(swap.get(v.name, v.name) for v in constraint.variables())
        return f"{type(constraint).__name__}({', '.join(names)})"
    return repr(swapped_names(plain(constraint), swap))


def body_is_symmetric(rule: CheckedRule, a: str, b: str) -> bool:
    """Whether swapping the two variables leaves the body as it was: the same patterns (by class, relations, values
    and conditions, whichever node they are of) and the same constraints"""
    swap = {a: b, b: a}

    def renamed(name: str) -> str:
        if name.startswith("v_"):
            return "v_" + swap.get(name[2:], name[2:])
        return "?"  # (a node of a pattern alone: which one does not matter)

    def shape(swapped: bool) -> tuple:
        rename = renamed if swapped else (lambda n: n if n.startswith("v_") else "?")
        patterns = []
        for node in rule.nodes.values():
            edges = sorted(
                (
                    e.field,
                    rename(e.target),
                    e.wrapped,
                    e.through,
                    repr(plain((e.steps, e.last, e.values))),
                )
                for e in rule.edges
                if e.source == node.name
            )
            values = sorted(
                (v.field, swap.get(v.var, v.var) if swapped else v.var, v.many)
                for v in rule.values
                if v.node == node.name
            )
            patterns.append(
                (
                    rename(node.name),
                    node.model.__name__,
                    tuple(edges),
                    tuple(values),
                    repr(plain(node.filters)),
                )
            )
        constraints = [
            constraint_shape(c, swap if swapped else {}) for c in rule.constraints
        ]
        return tuple(sorted(patterns)), tuple(sorted(constraints))

    return shape(False) == shape(True)


def count_uses(builder: Builder) -> dict[str, int]:
    uses: dict[str, int] = {}
    for node in builder.nodes.values():
        if node.var is not None:
            uses[node.var.name] = sum(
                1 for e in builder.edges if e.target == node.name
            ) + builder.own.get(node.var.name, 0)
    for value in builder.values:
        uses[value.var] = uses.get(value.var, 0) + 1
    for edge in builder.edges:
        for value in edge.values:
            uses[value.var] = uses.get(value.var, 0) + 1
    return uses


def plain(value: Any) -> Any:
    """A part of a rule as data, for its hash: classes by name, variables by name"""
    if isinstance(value, type):
        return value.__name__
    if isinstance(value, Var):
        return {"var": value.name}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "kind": type(value).__name__,
            **{
                f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)
            },
        }
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(str(plain(v)) for v in value)
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    return value


def rule_hash(rule: CheckedRule) -> str:
    """What the stored facts of the rule were made with: its body, the fields of its class, its types, and what the
    wrappers do. A change to any is a change of the rule (it is built again)"""
    text = json.dumps(
        {
            "class": rule.model.__name__,
            "fields": []
            if rule.document
            else [
                [f.name, f.kind, getattr(f.model, "__name__", str(f.model)), f.role]
                for f in rule.model._fields.values()
            ],
            # (only where there is one: the hash of a rule of edges is what it was before documents were derived)
            **({"template": plain(rule.template)} if rule.document else {}),
            **(
                {"blocked_heads": sorted(rule.blocked_heads)}
                if rule.blocked_heads
                else {}
            ),
            "head": plain(rule.head),
            "nodes": {
                name: [n.model.__name__, plain(n.filters), n.pattern, n.top]
                for name, n in rule.nodes.items()
            },
            "edges": plain(rule.edges),
            "values": plain(rule.values),
            "constraints": [c.describe() + repr(plain(c)) for c in rule.constraints],
            "patterns": rule.patterns,
            "symmetric": rule.symmetric,
            "types": rule.type_names,
            "blocked": sorted(rule.blocked),
            "transparent": sorted(rule.transparent),
            # (what the walk reads: a change of what a space says of its contents makes the rule's facts due again)
            "spaces": rule.spaces,
            # (and what each head class says of what it holds: a change of a ground makes them due again too)
            "grounds": rule.grounds,
            "statuses": sorted(rule.statuses),
            "exclusive": sorted(rule.exclusive),
            # (only where there are any: the hash of every other rule stays what it was)
            **({"exclusive_with": rule.exclusive_with} if rule.exclusive_with else {}),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# What can trigger a rule
# ---------------------------------------------------------------------------


def subclasses_of(model: type) -> list[type]:
    return [
        m
        for m in ModelRegistry.all_models().values()
        if isinstance(m, type) and issubclass(m, model)
    ]


def contained(model: type, seen: set[type] | None = None) -> set[type]:
    """The classes of the nodes that a document of the class can have in its tree (itself among them)"""
    seen = set() if seen is None else seen
    if model in seen:
        return seen
    seen.add(model)
    fields = getattr(getattr(model, "_meta", None), "fields", None)
    if fields is None:
        return seen
    for definition in fields.values():
        if isinstance(definition, EmbeddedFieldDefinition):
            for option in definition.type_options:
                for sub in subclasses_of(option.annotated_type):
                    contained(sub, seen)
        elif isinstance(definition, RelationFieldDefinition):
            for option in definition.type_options:
                options_contained(option, seen)
    return seen


def options_contained(option: Any, seen: set[type]) -> None:
    if isinstance(option, RelationToDocument):
        for sub in subclasses_of(option.annotated_type):
            contained(sub, seen)
    elif isinstance(
        option,
        (
            RelationToSemanticSpace,
            RelationToConjunction,
            RelationToReifiedRelation,
            RelationToReifiedRelationDocument,
        ),
    ):
        origin = typing.get_origin(option.annotated_type) or option.annotated_type
        if isinstance(origin, type):
            contained(origin, seen)
        for parameter in option.parameter_type_options.values():
            for inner in parameter.type_options:
                options_contained(inner, seen)


def trigger_table(rules: list[CheckedRule]) -> dict[str, list[Seed]]:
    """For each class of head node: the places of the rules that a node of its tree can be at"""
    from pangloss_models.utils import model_is_trait

    heads = [
        m
        for m in ModelRegistry.all_models().values()
        if isinstance(m, type)
        and issubclass(m, (Document, Entity))
        and not model_is_trait(m)
        and getattr(m, "__metatype__", None) in ("Document", "Entity")
    ]
    table: dict[str, list[Seed]] = {}
    for head in heads:
        inside = contained(head) if issubclass(head, Document) else {head}
        found = [
            seed
            for rule in rules
            for seed in rule.seeds
            if any(isinstance(c, type) and (issubclass(c, seed.model)) for c in inside)
        ]
        if found:
            table[head.__name__] = found
    return table


# ---------------------------------------------------------------------------
# All of it
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Rules that read what rules write
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Feed:
    """A pattern of the rule `reader` can match a node that the rule `writer` writes: a `written` (in a document of
    the writer's class), where the pattern is of a `read`"""

    writer: str
    reader: str
    written: type
    read: type


def feeds(writer: CheckedRule, reader: CheckedRule) -> list[Feed]:
    """How the reader can read what the writer writes. Worked out from the template, which says exactly which
    classes of nodes a rule writes: not from the class of its document, whose fields could hold anything
    (`statements: list[Statement]`). A reader that blocks the writer's document class reads none of it"""
    from pangloss_derived.templates import written_classes

    if not writer.document:
        return []
    models = ModelRegistry.all_models()
    if any(
        issubclass(writer.model, models[name])
        for name in reader.blocked_heads
        if name in models
    ):
        return []
    return [
        Feed(writer.name, reader.name, written, node.model)
        for node in reader.tops
        for written in written_classes(writer.template)
        if isinstance(written, type) and issubclass(written, node.model)
    ]


def rule_graph(rules: dict[str, CheckedRule]) -> dict[str, dict[str, list[Feed]]]:
    """For each rule that derives documents: the rules that read what it writes, each with how"""
    graph: dict[str, dict[str, list[Feed]]] = {}
    for writer in rules.values():
        if not writer.document:
            continue
        graph[writer.name] = {}
        for reader in rules.values():
            found = feeds(writer, reader)
            if found:
                graph[writer.name][reader.name] = found
    return graph


def find_cycle(graph: dict[str, dict[str, list[Feed]]]) -> list[str] | None:
    """A loop of rules, each reading what the one before writes (the first is given again at the end); None if there
    is none"""
    done: set[str] = set()

    def visit(name: str, path: list[str]) -> list[str] | None:
        if name in path:
            return path[path.index(name) :] + [name]
        if name in done:
            return None
        for reader in graph.get(name, {}):
            found = visit(reader, path + [name])
            if found:
                return found
        done.add(name)
        return None

    for name in graph:
        found = visit(name, [])
        if found:
            return found
    return None


def refuse_cycles(
    rules: dict[str, CheckedRule], graph: dict[str, dict[str, list[Feed]]]
) -> None:
    """Rules read derived documents, but never in a loop: a document that (through any number of rules) is derived
    from itself would need a fixpoint, which the worker does not work out"""
    cycle = find_cycle(graph)
    if cycle is None:
        return
    steps = []
    for writer, reader in zip(cycle, cycle[1:], strict=False):
        feed = graph[writer][reader][0]
        of_class = rules[writer].model.__name__
        steps.append(
            f"{writer} writes a {feed.written.__name__} (in a {of_class}), which a pattern of {reader} "
            f"({feed.read.__name__}) can match"
        )
    blocked = sorted({rules[name].model.__name__ for name in cycle[:-1]})
    if len(cycle) == 2:
        said = f"Rule {cycle[0]} reads what it writes"
    else:
        said = "Rules " + " -> ".join(cycle) + " read what they write, in a loop"
    raise PanglossDerivedError(
        f"{said}: {'; '.join(steps)}. A derived document is not derived from itself. Give the rule that is to read "
        f"only what people wrote block=[{', '.join(blocked)}] in its .when(...), or make its pattern of a narrower "
        "class"
    )


def build_order(
    rules: dict[str, CheckedRule], graph: dict[str, dict[str, list[Feed]]]
) -> list[str]:
    """Every rule, one that reads derived documents after the rules that write them (and otherwise as declared). The
    graph has no loop"""
    writers: dict[str, list[str]] = {name: [] for name in rules}
    for writer, readers in graph.items():
        for reader in readers:
            writers[reader].append(writer)
    order: list[str] = []

    def place(name: str) -> None:
        if name in order:
            return
        for writer in writers[name]:
            place(writer)
        order.append(name)

    for name in rules:
        place(name)
    return order


def people_heads() -> list[type]:
    """The classes of the head documents that people write"""
    return [
        m
        for m in ModelRegistry.all_models().values()
        if isinstance(m, type)
        and getattr(m, "__metatype__", None) == "Document"
        and issubclass(m, Document)
        and not is_derived_document(m)
        and m.__module__ != "pangloss_models.citations"
        and not m._meta.abstract
        and m._meta.create_directly
    ]


def refuse_source(
    rule: CheckedRule, node: Node, head: type, how: str, own: bool = False
) -> typing.NoReturn:
    field, option = source_field(rule.model)
    names = " | ".join(
        c.__name__ for c in sorted(option.cited, key=lambda c: c.__name__)
    )
    fail(
        rule.name,
        f"a pattern of {node.model.__name__} can be found in a {head.__name__} ({how}), which "
        f"{rule.model.__name__}.{field} (DerivedFrom[{names}]) does not take as a source. Let the field take "
        f"it (DerivedFrom[{names} | {head.__name__}]), or keep the rule from reading there "
        f"(block=[{head.__name__}] in its .when(...))"
        + (
            f". If a {head.__name__} is only ever part of another document, say so on its class "
            "(_meta = Document.Meta(create_directly=False)), and it is no head at all"
            if own
            else ""
        ),
    )


def check_sources(
    rules: dict[str, CheckedRule], graph: dict[str, dict[str, list[Feed]]]
) -> None:
    """A rule that derives a document is refused if its evidence could be in a head document that the `DerivedFrom`
    field of its class does not take. The heads a pattern can be found in: the classes people write that can hold a
    node of its class; and the derived classes that a rule which feeds this one writes"""
    models = ModelRegistry.all_models()
    holds: dict[type, set[type]] = {}
    for rule in rules.values():
        if not rule.document:
            continue
        _, option = source_field(rule.model)
        taken = list(option.cited)
        blocked = [models[name] for name in rule.blocked_heads if name in models]

        for node in rule.tops:
            for head in people_heads():
                if any(issubclass(head, b) for b in blocked):
                    continue
                if head not in holds:
                    holds[head] = contained(head)
                if not any(
                    isinstance(c, type) and issubclass(c, node.model)
                    for c in holds[head]
                ):
                    continue
                if not any(issubclass(head, c) for c in taken):
                    own = issubclass(head, node.model)
                    refuse_source(
                        rule,
                        node,
                        head,
                        "a document of its own"
                        if own
                        else f"which can hold a {node.model.__name__}",
                        own,
                    )
            for writer, readers in graph.items():
                for feed in readers.get(rule.name, []):
                    head = rules[writer].model
                    if feed.read is node.model and not any(
                        issubclass(head, c) for c in taken
                    ):
                        refuse_source(
                            rule,
                            node,
                            head,
                            f"the rule {writer} writes a {feed.written.__name__} in one",
                        )


# ---------------------------------------------------------------------------
# All of it
# ---------------------------------------------------------------------------


def initialise_rules() -> None:
    every: dict[str, CheckedRule] = {}
    for rule in DerivedRegistry.rules.values():
        # (a type declared with the models is not declared again when the registry is emptied and they are not
        # imported again: a rule that has it says it is one)
        for rule_type in rule.types:
            DerivedRegistry.add_type(rule_type)
        every[rule.name] = check_rule(rule)
    graph = rule_graph(every)
    refuse_cycles(every, graph)
    check_sources(every, graph)
    checked = {name: rule for name, rule in every.items() if not rule.document}
    DerivedRegistry.checked = checked
    DerivedRegistry.documents = {
        name: rule for name, rule in every.items() if rule.document
    }
    DerivedRegistry.order = build_order(every, graph)
    DerivedRegistry.readers = {
        writer: list(readers) for writer, readers in graph.items()
    }
    DerivedRegistry.triggers = trigger_table(list(every.values()))
