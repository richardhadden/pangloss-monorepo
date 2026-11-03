"""What `initialise` makes of the declarations: the classes of each `Derived` class, and each rule checked against the
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
from typing import Any, Literal

from pangloss_models.field_definitions import (
    EmbeddedFieldDefinition,
    RelationFieldDefinition,
    RelationToConjunction,
    RelationToDocument,
    RelationToReifiedRelation,
    RelationToReifiedRelationDocument,
    RelationToSemanticSpace,
)
from pangloss_models.exceptions import PanglossSearchError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry
from pangloss_models.search import (
    WRAPPER_LABELS,
    AnyOf,
    CheckedCondition,
    CheckedPattern,
    Expr,
    Not,
    RuleKey,
    Var,
    check_where,
    checking_rule,
    kind_of,
    parse_where,
    without_none,
)
from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from pangloss_derived.declare import (
    Body,
    Constraint,
    Derived,
    DerivedField,
    Head,
    Rule,
    RuleType,
    derivation_of,
    is_exclusive,
)
from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError

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
class Edge:
    """A relation from the node `source`, by its field, to the node `target` (directly, or through wrappers if the field
    can have them; through the wrappers named in `through`, if any are)"""

    index: int
    source: str
    field: str
    target: str
    wrapped: bool
    through: tuple[str, ...] = ()


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
    model: type[Derived]
    head: dict[str, tuple[Literal["var", "value"], Any]]
    """Each field of the class: a variable (by name), or a value"""
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
    symmetric_body: bool = False
    """Whether the body is the same with the two symmetric variables swapped (`same_group`: then each pair is matched once,
    in order of id; otherwise, as with `before(d1, d2)`, both orders are matched and the ends are put in order when the
    fact is written)"""
    hash: str = ""

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
        head = ", ".join(
            value if kind == "var" else repr(value)
            for kind, value in self.head.values()
        )
        parts = []
        for node in self.nodes.values():
            if node.pattern:
                parts.append(f"{node.model.__name__}({node.name})")
        for edge in self.edges:
            via = " via " + "|".join(edge.through) if edge.through else ""
            parts.append(f"{edge.field}({edge.source}, {edge.target}){via}")
        for value in self.values:
            parts.append(f"{value.field}({value.node}, {value.var})")
        parts += [c.describe() for c in self.constraints]
        return f"{self.model.__name__}({head}) :-\n    " + ",\n    ".join(parts) + "."


# ---------------------------------------------------------------------------
# Derived classes
# ---------------------------------------------------------------------------

LITERALS = {"text", "number", "decimal", "temporal", "simple"}


def derived_fields(model: type[Derived]) -> dict[str, DerivedField]:
    """The fields of a `Derived` class, from its annotations (and its parents')"""
    try:
        hints = typing.get_type_hints(model)
    except NameError as error:
        raise PanglossDerivedError(
            f"{model.__name__}: a field's type cannot be found ({error})"
        ) from None
    fields: dict[str, DerivedField] = {}
    for name, annotation in hints.items():
        if name.startswith("_") or typing.get_origin(annotation) is typing.ClassVar:
            continue
        if annotation in (typing.ClassVar,) or name in (
            "Meta",
            "Derive",
            "View",
            "Where",
        ):
            continue
        base = without_none(annotation)
        if isinstance(base, type) and issubclass(base, Entity):
            fields[name] = DerivedField(name, "relation", base)
        elif is_trait(base):
            fields[name] = DerivedField(name, "relation", base)
        elif kind_of(base) in LITERALS:
            fields[name] = DerivedField(name, "literal", base)
        else:
            raise PanglossDerivedError(
                f"{model.__name__}.{name}: a field of a Derived class is an entity (or a trait of entities) or a "
                f"literal (str, int, a date, an enum...), not {annotation!r}"
            )
    if not fields:
        raise PanglossDerivedError(f"{model.__name__} has no fields")
    return fields


def is_trait(model: Any) -> bool:
    from pangloss_models.utils import model_is_trait

    return isinstance(model, type) and model_is_trait(model)


def symmetric_fields(model: type[Derived]) -> tuple[str, str] | None:
    symmetric = model._meta.symmetric
    if not symmetric:
        return None
    fields = model._fields
    if symmetric is True:
        relations = [f for f in fields.values() if f.kind == "relation"]
        if len(relations) < 2:
            raise PanglossDerivedError(
                f"{model.__name__} is symmetric, but has fewer than two relation fields"
            )
        pair = (relations[0].name, relations[1].name)
    else:
        pair = tuple(symmetric)  # type: ignore[assignment]
    a, b = (fields.get(n) for n in pair)
    if a is None or b is None or a.model is not b.model:
        raise PanglossDerivedError(
            f"{model.__name__}: the symmetric fields {pair} must be two fields of the same type"
        )
    return pair  # type: ignore[return-value]


def ends_of(model: type[Derived]) -> tuple[str, str]:
    """The two fields that are an edge, when the facts are made a graph"""
    if model._meta.ends:
        return model._meta.ends
    pair = symmetric_fields(model)
    if pair:
        return pair
    relations = [f.name for f in model._fields.values() if f.kind == "relation"]
    if len(relations) < 2:
        raise PanglossDerivedError(
            f"{model.__name__} has fewer than two relation fields: give its Meta `ends`"
        )
    return relations[0], relations[1]


class DeriveBase(BaseModel):
    """The head of a rule: `SameFamily.Derive(first=a, second=b, family=f)`, then `.when(...)`"""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    _derived: typing.ClassVar[type[Derived]]
    # (its stub has its `__init__` written out, so that a type checker checks the variables: `pangloss_models.typestubs`)
    _stub_init: typing.ClassVar[bool] = True

    def when(self, *items: Any, block: Any = (), allow: Any = ()) -> Body:
        head = Head(
            type(self)._derived,
            {name: getattr(self, name) for name in type(self).model_fields},
        )
        return head.when(*items, block=block, allow=allow)


def make_derive(model: type[Derived]) -> None:
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
        symmetric_fields(model)
        if not model._meta.abstract:
            ends_of(model)
        make_derive(model)
        make_views(model)


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


def wrapper_settings(body: Body) -> tuple[frozenset[str], frozenset[str]]:
    """The names of the wrappers that this rule does not derive through (`block`) and those it does not record
    (`transparent`): what their `DerivedMeta` says, but for the rule's own `block` and `allow`"""
    blocked: set[str] = set()
    transparent: set[str] = set()
    for model in wrapper_models():
        if any(issubclass(model, b) for b in body.block):
            blocked.add(model.__name__)
            continue
        derivation = derivation_of(model)
        if any(issubclass(model, a) for a in body.allow) and derivation == "block":
            derivation = "qualify"
        if derivation == "block":
            blocked.add(model.__name__)
        elif derivation == "transparent":
            transparent.add(model.__name__)
    return frozenset(blocked), frozenset(transparent)


def has_variable(exprs: list[Expr]) -> bool:
    for e in exprs:
        if isinstance(e, CheckedCondition):
            if e.operator == "var":
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
                and has_variable(e.value.items)
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
                    )
                )
                continue
            node.filters.append(e)


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
    model = body.head.model
    if model._meta.abstract:
        fail(rule.name, f"{model.__name__} is abstract: nothing is derived as it")
    if not body.patterns:
        fail(rule.name, "the body has no pattern")

    # (the head)
    head: dict[str, tuple[Literal["var", "value"], Any]] = {}
    for name, field in model._fields.items():
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
            if field.kind == "relation":
                fail(rule.name, f"{model.__name__}.{name}: needs a variable")
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
        node = builder.pattern(pattern_model, checked, top=True)
        patterns.append(node.name)

    # (the variables: each bound by a pattern, each of the head among them)
    bound_nodes = {n.var.name for n in builder.nodes.values() if n.var is not None}
    bound_values = {v.var for v in builder.values}
    bound = bound_nodes | bound_values
    for name, (kind, value) in head.items():
        if kind == "var" and value not in bound:
            fail(
                rule.name,
                f"the variable {value!r} (of {model.__name__}.{name}) is in no pattern of the body",
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
    pair = symmetric_fields(model)
    if pair:
        a, b = (head[f] for f in pair)
        if a[1] == b[1]:
            fail(
                rule.name,
                f"the two symmetric fields of {model.__name__} are the one variable {a[1]!r}",
            )
        symmetric = (a[1], b[1])

    blocked, transparent = wrapper_settings(body)
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
        types=rule.types,
        exclusive=frozenset(m.__name__ for m in wrapper_models() if is_exclusive(m)),
    )
    checked_rule.symmetric_body = body_is_symmetric(checked_rule)
    checked_rule.hash = rule_hash(checked_rule)
    return checked_rule


def swapped_names(data: Any, swap: dict[str, str]) -> Any:
    """`plain` data with the variables renamed"""
    if isinstance(data, dict):
        if set(data) == {"var"}:
            return {"var": swap.get(data["var"], data["var"])}
        return {k: swapped_names(v, swap) for k, v in data.items()}
    if isinstance(data, list):
        return [swapped_names(v, swap) for v in data]
    return data


def body_is_symmetric(rule: CheckedRule) -> bool:
    """Whether swapping the two symmetric variables leaves the body as it was: the same patterns (by class, relations,
    values and conditions, whichever node they are of) and the same constraints"""
    if rule.symmetric is None:
        return False
    a, b = rule.symmetric
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
                (e.field, rename(e.target), e.wrapped, e.through)
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
        constraints = []
        for c in rule.constraints:
            data = plain(c)
            constraints.append(repr(swapped_names(data, swap) if swapped else data))
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
            "fields": [
                [f.name, f.kind, getattr(f.model, "__name__", str(f.model))]
                for f in rule.model._fields.values()
            ],
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
            "exclusive": sorted(rule.exclusive),
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


def initialise_rules() -> None:
    checked: dict[str, CheckedRule] = {}
    for rule in DerivedRegistry.rules.values():
        checked[rule.name] = check_rule(rule)
    DerivedRegistry.checked = checked
    DerivedRegistry.triggers = trigger_table(list(checked.values()))
