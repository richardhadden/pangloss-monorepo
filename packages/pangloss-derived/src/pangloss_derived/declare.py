"""What a project declares in its `derived.py`: what can be derived (`DerivedEdge` classes), how (`@rule`), the types of
rules (`RuleType`), the constraints of a rule's body, and what a semantic space or other wrapper does to a derivation
(`DerivedMeta`). See implementation_docs/derived.md.

    family_ties = RuleType("family", "Ties of family")

    class SameFamily(DerivedEdge):
        '''Members of the same family'''
        _meta = DerivedEdge.Meta(symmetric=True)
        first: Annotated[Person, SymmetricLabel("member")]      # the two ends, in either order
        second: Annotated[Person, SymmetricLabel("member")]
        family: Group                                           # a qualifier: part of what the edge is

    class GaveTo(DerivedEdge):
        '''Gave something to'''
        giver: Annotated[Agent, Subject()]
        receiver: Annotated[Agent, Object(reverse_name="received_from")]

    @rule(types=[family_ties])
    def same_family(a: Var[Person], b: Var[Person], family: Var[Group]):
        return SameFamily.Derive(first=a, second=b, family=family).when(
            MemberOf.Where(member=a, group=family),
            MemberOf.Where(member=b, group=family),
        )

Nothing here touches the database, or runs a rule: `initialise()` (of the models) calls `pangloss_derived.initialise`,
which makes the classes of each `DerivedEdge` class, calls each rule's function with its variables and checks what it gives.
"""

import dataclasses
import inspect
from collections.abc import Callable, Iterable, Sequence
from typing import Any, ClassVar, Literal, overload

from pangloss_models import Cites, Var, register_meta_slot
from pangloss_models.search import VarComparison

from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError

__all__ = [
    "Constraint",
    "DerivedEdge",
    "DerivedFrom",
    "DerivedMeta",
    "Object",
    "PerJustification",
    "Rule",
    "RuleType",
    "Subject",
    "SymmetricLabel",
    "Var",
    "between",
    "distinct",
    "gt",
    "gte",
    "lt",
    "lte",
    "rule",
    "same",
    "same_document",
    "unordered",
]


# ---------------------------------------------------------------------------
# Types of rules
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RuleType:
    """A type of rule: a tag that any number of rules (of any `DerivedEdge` classes) can have, so that the facts they derive
    can be taken together as one graph (`pangloss derive graph family`). Declared once, and given to `@rule(types=...)`:

        social = RuleType("social", "Social ties between people")
    """

    name: str
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.isidentifier():
            raise ValueError(
                f"The name of a RuleType is a name (letters, digits and _): not {self.name!r}"
            )
        DerivedRegistry.add_type(self)


# ---------------------------------------------------------------------------
# What a semantic space or other wrapper does to a derivation
# ---------------------------------------------------------------------------

SLOT = "_derived_meta"

type Derivation = Literal["qualify", "block", "transparent"]


@dataclasses.dataclass(frozen=True)
class DerivedMeta:
    """On a semantic space, a conjunction or a reified relation (and inherited, as meta slots are): what a rule does
    with what it finds inside it, or reaches through it.

    - `qualify` (the default of a semantic space): derives, and the wrapper is in the context of the justification, so
      the fact is not plain on that account;
    - `block`: derives nothing from inside it (or through it);
    - `transparent` (the default of a reified relation and of a conjunction): derives as if it were not there (it is
      not in the context).

    Not given (`None`), it is the default of the kind of wrapper: so `DerivedMeta(exclusive=True)` on a conjunction
    leaves it transparent.

    `exclusive` (for a conjunction whose members are alternatives: "one of these, not known which"): one justification
    takes at most one of its members. Without it, two patterns could each take another member of the one alternative,
    and derive from "Smith, who is A or B" that A and B are of the same family.

    `exclusive="field"`: exclusive, and **together with** the wrappers of the same document that have the same value
    of that field (a literal of the class). One justification takes at most one member of all of them: for a class
    whose nodes can be several places of one alternative ("N. N. carried it, and N. N. was paid": two wrappers, one
    unknown person). A wrapper with no value of the field is exclusive alone."""

    derivation: Derivation | None = None
    exclusive: bool | str = False


register_meta_slot(SLOT, DerivedMeta)


def default_derivation(model: type) -> Derivation:
    """What a wrapper that says nothing does: a semantic space qualifies (what is inside a `Negative` is not said
    plainly); a reified relation or a conjunction is read through as if it were not there"""
    if getattr(model, "__metatype__", None) == "SemanticSpace":
        return "qualify"
    return "transparent"


def derivation_of(model: type) -> Derivation:
    meta = getattr(model, SLOT, None)
    if isinstance(meta, DerivedMeta) and meta.derivation is not None:
        return meta.derivation
    return default_derivation(model)


def is_exclusive(model: type) -> bool:
    meta = getattr(model, SLOT, None)
    return isinstance(meta, DerivedMeta) and bool(meta.exclusive)


def exclusive_with(model: type) -> str | None:
    """The field by which the wrappers of the class are exclusive together (`exclusive="field"`), if any"""
    meta = getattr(model, SLOT, None)
    if isinstance(meta, DerivedMeta) and isinstance(meta.exclusive, str):
        return meta.exclusive
    return None


# ---------------------------------------------------------------------------
# What a derived document rests on
# ---------------------------------------------------------------------------


class DerivedFrom[Target](Cites[Target]):
    """`sources: list[DerivedFrom[Factoid]]`: the documents that a derived document rests on. Read, shown and listed
    as a citation is (`Cites[T]`), but it **protects nothing and is never marked changed**: a derived document
    follows its evidence and must never hold it fast, so a source is changed and deleted freely, and the worker
    derives again. Its nodes are `PGUnprotectedCitation`s, which the checks made before every save of what is cited
    do not meet (`pangloss_models.citations`)"""

    protect = False


# ---------------------------------------------------------------------------
# Derived classes
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class DerivedConfig:
    """The `Meta` of a `DerivedEdge` class:

    - `symmetric`: the order of the two ends does not matter. The ends are the two fields with a `SymmetricLabel`, of
      one type. An edge is stored once, with the two in order of id, and never relates a thing to itself;
    - `max_per_seed`: the most justifications one written document may give for a rule of this class; past it, those
      of the document are not written, and it is logged (a safeguard against a rule, or data, that would fill the
      database);
    - `abstract`: a parent of other `DerivedEdge` classes, with no edges of its own;
    - `shortcut`: beside the node of each edge, the worker keeps an edge of the name of the class from the subject
      to the object (`(a)-[:SameGroup {key, derived: true}]->(b)`; of a symmetric class, from the one with the lower
      id), for paths and graph algorithms written in Cypher: `pangloss_derived.shortcuts`. Nothing of Pangloss reads
      it, and it takes no account of the reader."""

    symmetric: bool = False
    max_per_seed: int = 10_000
    abstract: bool = False
    shortcut: bool = False


@dataclasses.dataclass(frozen=True)
class Subject:
    """Marks the field an asymmetric edge starts at: `giver: Annotated[Agent, Subject()]`"""


@dataclasses.dataclass(frozen=True)
class Object:
    """Marks the field an asymmetric edge ends at: `receiver: Annotated[Agent, Object(reverse_name="received_from")]`.
    `reverse_name` names the edge as read from this end (a name in code: written as words, and translated, as a field's
    name is); without it, the class's own name is used from either end"""

    reverse_name: str | None = None

    def __post_init__(self) -> None:
        if self.reverse_name is not None and not self.reverse_name.isidentifier():
            raise ValueError(
                f"The reverse_name of an Object() is a name (letters, digits and _): not {self.reverse_name!r}"
            )


@dataclasses.dataclass(frozen=True)
class SymmetricLabel:
    """Marks the two ends of a symmetric `DerivedEdge` class, and gives the one name they have in the interface (their
    own names, `first` and `second`, mean nothing): `first: Annotated[Person, SymmetricLabel("member")]`. A name in
    code: it is written as words ("Member") and translated as a field's name is. On both fields, the same"""

    name: str


@dataclasses.dataclass(frozen=True)
class PerJustification:
    """Marks a literal field whose value does not define the edge: it is a value of each justification (a probability
    found on the way), kept with it and shown with it, and not part of the edge's key. So one edge between A and B can
    have a justification at 80 and one at 60: `likelihood: Annotated[int, PerJustification()]`"""


type Role = Literal["subject", "object", "qualifier", "per_justification"]


class DerivedEdge:
    """The base of what can be derived: an edge between two entities (its two **ends**), qualified by its other fields.

    - the ends: on an asymmetric edge, one field marked `Subject()` and one `Object()`; on a symmetric one
      (`Meta(symmetric=True)`), the two fields with a `SymmetricLabel`. Each is an entity class (or a trait of
      entities);
    - every other field is a **qualifier**, a relation to an entity (`group: Group`) or a literal (`year: int`), and
      part of what the edge is: two people in two groups have two `SameGroup` edges;
    - but for a literal marked `PerJustification()`, which is a value of each justification.

    No documents, embedded objects or lists. Nobody writes one: rules derive them. `initialise()` gives each its
    `Derive` (the head of a rule), `View` and `Where`."""

    Meta: ClassVar[type[DerivedConfig]] = DerivedConfig
    _meta: ClassVar[DerivedConfig] = DerivedConfig()

    # (made by `initialise`)
    Derive: ClassVar[Any]
    View: ClassVar[Any]
    Qualifiers: ClassVar[Any]
    Where: ClassVar[Any]
    _fields: ClassVar[dict[str, "DerivedField"]]
    _ends: ClassVar[tuple[str, str]]
    """The two fields that are the ends: the subject and the object (of a symmetric class, its two in the order
    declared)"""
    # (the `SymmetricLabel` of the ends of a symmetric class)
    _symmetric_label: ClassVar[str | None] = None
    # (the `reverse_name` of the `Object()` of an asymmetric class, if it has one)
    _reverse_name: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "_meta" not in cls.__dict__:
            # (a subclass is not abstract because its parent is)
            cls._meta = dataclasses.replace(cls._meta, abstract=False)
        if not isinstance(cls._meta, DerivedConfig):
            raise TypeError(
                f"{cls.__name__}._meta must be a DerivedEdge.Meta(...), not {cls._meta!r}"
            )
        DerivedRegistry.add_class(cls)

    @staticmethod
    def named(name: str) -> "type[DerivedEdge]":
        """The class of the name: for one that no module declares (an edge declared on a document class, with
        `DerivesEdge`). After `initialise()`"""
        model = DerivedRegistry.classes.get(name)
        if model is None:
            known = ", ".join(sorted(DerivedRegistry.classes)) or "(none)"
            raise PanglossDerivedError(
                f"There is no derived edge called {name!r} (there are: {known})"
            )
        return model

    @classmethod
    def qualifiers(cls) -> list["DerivedField"]:
        """The fields that define the edge beside its ends"""
        return [f for f in cls._fields.values() if f.role == "qualifier"]

    @classmethod
    def per_justification(cls) -> list["DerivedField"]:
        return [f for f in cls._fields.values() if f.role == "per_justification"]

    @classmethod
    def key_fields(cls) -> list[str]:
        """The fields whose values are the key of an edge: its ends and its qualifiers"""
        return [f.name for f in cls._fields.values() if f.role != "per_justification"]

    # (`list` and `get` are bound at `initialise`, as the storage in use has them: `pangloss_derived.access`)
    list: ClassVar[Any]
    """`await SameFamily.list(where=None, *, entity=None, page=1, page_size=25, evidence=None, at=None)`: a page of the
    edges the reader sees, about an entity (at an end or as a qualifier; `at=["first"]`: only at these fields) or that
    a head document is evidence of, fitting `where` (`SameFamily.Where(family=..., plain=True)`). Blocking with the
    blocking SDK"""
    get: ClassVar[Any]
    """`await SameFamily.get(id)`: an edge with its justifications ("why"); None if there is none the reader sees"""

    def __init__(self) -> None:
        raise TypeError(
            f"A {type(self).__name__} is derived, not made: rules derive it. Read them with "
            f"{type(self).__name__}.list(), .get() or .search()"
        )


@dataclasses.dataclass(frozen=True)
class DerivedField:
    """A field of a `DerivedEdge` class: a relation to entities of `model` (`relation`), or a literal of type `model`;
    and what it is of the edge (`role`: an end, a qualifier, or a value of each justification)"""

    name: str
    kind: Literal["relation", "literal"]
    model: Any
    role: Role = "qualifier"


# ---------------------------------------------------------------------------
# Constraints of a rule
# ---------------------------------------------------------------------------


class Constraint:
    """A condition on the variables of a rule, given after the patterns in `.when(...)`. An add-on can make its own (a
    subclass with `variables` and `cypher`): `pangloss_dates.overlaps(d1, d2)`"""

    def variables(self) -> list[Var]:
        """The variables it is about"""
        raise NotImplementedError

    def cypher(self, names: Callable[[Var], str], param: Callable[[Any], str]) -> str:
        """The condition in Cypher, given the expression of each variable (`names(var)`: a node, or a value) and a way to
        give a value as a parameter (`param(value)` is its name, with `$`)"""
        raise NotImplementedError

    def describe(self) -> str:
        return type(self).__name__

    def check(self) -> str | None:
        """What is wrong with the variables it was given (their classes), if anything: said by `check_rule`"""
        return None


@dataclasses.dataclass(frozen=True)
class Distinct(Constraint):
    items: tuple[Var, ...]

    def variables(self) -> list[Var]:
        return list(self.items)

    def cypher(self, names, param) -> str:
        pairs = [
            f"{names(a)} <> {names(b)}"
            for i, a in enumerate(self.items)
            for b in self.items[i + 1 :]
        ]
        return " AND ".join(pairs) or "true"

    def describe(self) -> str:
        return f"distinct({', '.join(v.name for v in self.items)})"


@dataclasses.dataclass(frozen=True)
class Same(Constraint):
    a: Var
    b: Var

    def variables(self) -> list[Var]:
        return [self.a, self.b]

    def cypher(self, names, param) -> str:
        return f"{names(self.a)} = {names(self.b)}"

    def describe(self) -> str:
        return f"same({self.a.name}, {self.b.name})"


@dataclasses.dataclass(frozen=True)
class SameDocument(Constraint):
    """The two nodes (variables of documents, or of the patterns' `is_`) are in one head document"""

    a: Var
    b: Var

    def variables(self) -> list[Var]:
        return [self.a, self.b]

    def cypher(self, names, param) -> str:
        a, b = names(self.a), names(self.b)
        return (
            f"coalesce({a}.head_node_id, {a}.id) = coalesce({b}.head_node_id, {b}.id)"
        )

    def describe(self) -> str:
        return f"same_document({self.a.name}, {self.b.name})"


COMPARISON_SIGNS = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">="}


@dataclasses.dataclass(frozen=True)
class Compared(Constraint):
    """A literal variable compared with another, or with a value"""

    operator: str
    left: Var
    right: Any

    def variables(self) -> list[Var]:
        return [self.left] + ([self.right] if isinstance(self.right, Var) else [])

    def cypher(self, names, param) -> str:
        right = names(self.right) if isinstance(self.right, Var) else param(self.right)
        return f"{names(self.left)} {COMPARISON_SIGNS[self.operator]} {right}"

    def describe(self) -> str:
        right = self.right.name if isinstance(self.right, Var) else repr(self.right)
        return f"{self.left.name} {COMPARISON_SIGNS[self.operator]} {right}"


@dataclasses.dataclass(frozen=True)
class Between(Constraint):
    value: Var
    low: Any
    high: Any

    def variables(self) -> list[Var]:
        return [v for v in (self.value, self.low, self.high) if isinstance(v, Var)]

    def cypher(self, names, param) -> str:
        def side(x: Any) -> str:
            return names(x) if isinstance(x, Var) else param(x)

        return f"({side(self.low)} <= {names(self.value)} AND {names(self.value)} <= {side(self.high)})"

    def describe(self) -> str:
        return f"between({self.value.name}, ...)"


@dataclasses.dataclass(frozen=True)
class Unordered(Constraint):
    """The two variables are interchangeable in the rule, and each pair is to be found once: in order of id (and so
    never a thing with itself)"""

    a: Var
    b: Var

    def variables(self) -> list[Var]:
        return [self.a, self.b]

    def cypher(self, names, param) -> str:
        return f"{names(self.a)}.id < {names(self.b)}.id"

    def describe(self) -> str:
        return f"unordered({self.a.name}, {self.b.name})"

    def check(self) -> str | None:
        from pangloss_models import Document, Embedded, Entity
        from pangloss_models.utils import model_is_trait

        for variable in (self.a, self.b):
            model = variable.model
            if not (
                isinstance(model, type)
                and (
                    issubclass(model, (Entity, Document, Embedded))
                    or model_is_trait(model)
                )
            ):
                return (
                    f"{variable.name} is a value ({getattr(model, '__name__', model)}): the two of an unordered "
                    "pair are entities or documents"
                )
        if self.a is self.b:
            return "the two are one variable"
        return None


def distinct(*items: Var) -> Constraint:
    """None of these is the same node (or value). (The two fields of a symmetric class are distinct without it)"""
    return Distinct(tuple(items))


def same(a: Var, b: Var) -> Constraint:
    return Same(a, b)


def unordered(a: Var, b: Var) -> Constraint:
    """The rule is the same with `a` and `b` swapped, and each pair is wanted once, not twice: `siblings` matches (A, B)
    and (B, A), which would be two derived documents that say one thing. The pair is taken in order of id (so the two
    are distinct as well). `initialise()` refuses it where the body is not the same with the two swapped: half the
    pairs would be lost. A symmetric `DerivedEdge` class needs none: its two ends are unordered already"""
    return Unordered(a, b)


def same_document(a: Var, b: Var) -> Constraint:
    return SameDocument(a, b)


def lt(a: Var, b: Any) -> Constraint:
    return Compared("lt", a, b)


def lte(a: Var, b: Any) -> Constraint:
    return Compared("lte", a, b)


def gt(a: Var, b: Any) -> Constraint:
    return Compared("gt", a, b)


def gte(a: Var, b: Any) -> Constraint:
    return Compared("gte", a, b)


def between(value: Var, low: Any, high: Any) -> Constraint:
    return Between(value, low, high)


def as_constraint(item: Any) -> Constraint:
    if isinstance(item, Constraint):
        return item
    if isinstance(item, VarComparison):
        return Compared(item.operator, item.left, item.right)
    raise TypeError(
        f"{item!r} is not a pattern (a Model.Where) or a constraint (distinct, lt, ...)"
    )


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Head:
    """`SameFamily.Derive(first=a, ...)`: what a rule derives, each field a variable (or, for a literal, a value); or, of
    a derived document class, its template (`DerivedFactoid.Derive(statements=[...])`)"""

    model: type
    """A `DerivedEdge` class, or a derived document class"""
    values: dict[str, Any]
    template: Any = None
    """Of a derived document: what the rule writes (its `Derive`)"""

    def when(
        self,
        *items: Any,
        block: Sequence[type] = (),
        allow: Sequence[type] = (),
    ) -> "Body":
        """The body of the rule: the patterns (each a `Model.Where`, with variables), then any constraints. `block`
        and `allow`: semantic spaces (and other wrappers) that this rule does not derive from, or does, whatever their
        `DerivedMeta` says. `block` also takes document classes: the rule reads nothing inside a document of the class
        (`block=[DerivedFactoid]`: only what people wrote). A rule that derives a document derives through a
        qualifying wrapper (a `Negative`) only if it is in `allow`"""
        from pangloss_models import Where

        patterns = [i for i in items if isinstance(i, Where)]
        constraints = [as_constraint(i) for i in items if not isinstance(i, Where)]
        return Body(self, patterns, constraints, tuple(block), tuple(allow))


@dataclasses.dataclass(frozen=True)
class Body:
    head: Head
    patterns: list[Any]
    constraints: list[Constraint]
    block: tuple[type, ...] = ()
    allow: tuple[type, ...] = ()


@dataclasses.dataclass
class Rule:
    """A rule as declared: its function (called by `initialise`), its name and types. What it compiles to is
    `pangloss_derived.check.CheckedRule`"""

    name: str
    function: Callable[..., Body]
    types: tuple[RuleType, ...] = ()
    description: str = ""

    def variables(self) -> dict[str, Var]:
        """The variables, made from the parameters of the function: `a: Var[Person]` is `Var("a", Person)`"""
        signature = inspect.signature(self.function, eval_str=True)
        variables: dict[str, Var] = {}
        for name, parameter in signature.parameters.items():
            annotation = parameter.annotation
            args = getattr(annotation, "__args__", None)
            if getattr(annotation, "__origin__", None) is not Var or not args:
                raise TypeError(
                    f"Rule {self.name}: the parameter {name!r} must be annotated as a variable, like Var[Person]"
                )
            variables[name] = Var(name, args[0])
        return variables


@overload
def rule(function: Callable[..., Body], /) -> Rule: ...


@overload
def rule(
    *, types: Iterable[RuleType] = (), name: str | None = None
) -> Callable[[Callable[..., Body]], Rule]: ...


def rule(
    function: Callable[..., Body] | None = None,
    /,
    *,
    types: Iterable[RuleType] = (),
    name: str | None = None,
) -> Any:
    """Declare a rule: a function whose parameters are its variables (`a: Var[Person]`), which gives
    `SomeDerived.Derive(...).when(...)`. It is not called now: `initialise()` calls it, once the models are made, and
    checks what it gives. `types`: the `RuleType`s of the rule"""

    def declare(function: Callable[..., Body]) -> Rule:
        made = Rule(
            name=name or getattr(function, "__name__", "rule"),
            function=function,
            types=tuple(types),
            description=inspect.getdoc(function) or "",
        )
        for rule_type in made.types:
            if not isinstance(rule_type, RuleType):
                raise TypeError(
                    f"Rule {made.name}: {rule_type!r} is not a RuleType (declare one: RuleType('social'))"
                )
        DerivedRegistry.add_rule(made)
        return made

    if function is not None:
        return declare(function)
    return declare
