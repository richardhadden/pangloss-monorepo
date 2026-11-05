"""What a project declares in its `derived.py`: what can be derived (`Derived` classes), how (`@rule`), the types of rules
(`RuleType`), the constraints of a rule's body, and what a semantic space or other wrapper does to a derivation
(`DerivedMeta`). See docs/derived.md.

    family_ties = RuleType("family", "Ties of family")

    class SameFamily(Derived):
        '''Members of the same family'''
        _meta = Derived.Meta(symmetric=True)
        first: Person
        second: Person
        family: Group

    @rule(types=[family_ties])
    def same_family(a: Var[Person], b: Var[Person], family: Var[Group]):
        return SameFamily.Derive(first=a, second=b, family=family).when(
            MemberOf.Where(member=a, group=family),
            MemberOf.Where(member=b, group=family),
        )

Nothing here touches the database, or runs a rule: `initialise()` (of the models) calls `pangloss_derived.initialise`,
which makes the classes of each `Derived` class, calls each rule's function with its variables and checks what it gives.
"""

import dataclasses
import inspect
from collections.abc import Callable, Iterable, Sequence
from typing import Any, ClassVar, Literal, overload

from pangloss_models import Var, register_meta_slot
from pangloss_models.search import VarComparison

from pangloss_derived.registry import DerivedRegistry

__all__ = [
    "Constraint",
    "Derived",
    "DerivedMeta",
    "Rule",
    "RuleType",
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
]


# ---------------------------------------------------------------------------
# Types of rules
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RuleType:
    """A type of rule: a tag that any number of rules (of any `Derived` classes) can have, so that the facts they derive
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

    - `qualify` (the default): derives, and the wrapper is in the context of the justification, so the fact is not
      plain on that account;
    - `block`: derives nothing from inside it (or through it);
    - `transparent`: derives as if it were not there (it is not in the context).

    `exclusive` (for a conjunction whose members are alternatives: "one of these, not known which"): one justification
    takes at most one of its members. Without it, two patterns could each take another member of the one alternative,
    and derive from "Smith, who is A or B" that A and B are of the same family."""

    derivation: Derivation = "qualify"
    exclusive: bool = False


register_meta_slot(SLOT, DerivedMeta)


def derivation_of(model: type) -> Derivation:
    meta = getattr(model, SLOT, None)
    return meta.derivation if isinstance(meta, DerivedMeta) else "qualify"


def is_exclusive(model: type) -> bool:
    meta = getattr(model, SLOT, None)
    return isinstance(meta, DerivedMeta) and meta.exclusive


# ---------------------------------------------------------------------------
# Derived classes
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class DerivedConfig:
    """The `Meta` of a `Derived` class:

    - `symmetric`: two fields of one type whose order does not matter (`True`: the first two relation fields, or
      give them: `("first", "second")`). A fact is stored once, with the two in order of id, and never relates a thing
      to itself;
    - `ends`: the two fields that are the edge when the facts are made a graph (by default the symmetric two, or the
      first two relation fields);
    - `max_per_seed`: the most justifications one written document may give for a rule of this class; past it, those
      of the document are not written, and it is logged (a safeguard against a rule, or data, that would fill the
      database);
    - `abstract`: a parent of other `Derived` classes, with no facts of its own;
    - `reverse_names`: the key under `_derived` of an entity's view for a field (`{"giver": "gave_to"}`), by default
      the name of the class."""

    symmetric: bool | tuple[str, str] = False
    ends: tuple[str, str] | None = None
    max_per_seed: int = 10_000
    abstract: bool = False
    reverse_names: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class SymmetricLabel:
    """The one name, in the interface, of the two symmetric fields of a `Derived` class, whose own names (`first`,
    `second`) mean nothing: `first: Annotated[Person, SymmetricLabel("member")]`. A name in code: it is written as words
    ("Member") and translated as a field's name is. On either field, or on both (the same)"""

    name: str


class Derived:
    """The base of what can be derived: a relation between entities, with values. Its fields are relations to entities
    (`first: Person`) and literals (`year: int`); no documents, embedded objects or lists. Nobody writes one: rules
    derive them. `initialise()` gives each its `Derive` (the head of a rule), `View`, `ReferenceView` and `Where`."""

    Meta: ClassVar[type[DerivedConfig]] = DerivedConfig
    _meta: ClassVar[DerivedConfig] = DerivedConfig()

    # (made by `initialise`)
    Derive: ClassVar[Any]
    View: ClassVar[Any]
    Where: ClassVar[Any]
    _fields: ClassVar[dict[str, "DerivedField"]]
    # (the `SymmetricLabel` of its symmetric fields, if it has one)
    _symmetric_label: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "_meta" not in cls.__dict__:
            # (a subclass is not abstract because its parent is)
            cls._meta = dataclasses.replace(cls._meta, abstract=False)
        DerivedRegistry.add_class(cls)

    # (`list` and `get` are bound at `initialise`, as the storage in use has them: `pangloss_derived.access`)
    list: ClassVar[Any]
    """`await SameFamily.list(where=None, *, entity=None, page=1, page_size=25, evidence=None)`: a page of the facts the
    reader sees, about an entity (at any of its fields) or that a head document is evidence of, fitting `where`
    (`SameFamily.Where(family=..., plain=True)`). Blocking with the blocking SDK"""
    get: ClassVar[Any]
    """`await SameFamily.get(id)`: a fact with its justifications ("why"); None if there is none the reader sees"""

    def __init__(self) -> None:
        raise TypeError(
            f"A {type(self).__name__} is derived, not made: rules derive it. Read them with "
            f"{type(self).__name__}.list(), .get() or .search()"
        )


@dataclasses.dataclass(frozen=True)
class DerivedField:
    """A field of a `Derived` class: a relation to entities of `model` (`relation`), or a literal of type `model`"""

    name: str
    kind: Literal["relation", "literal"]
    model: Any


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


def distinct(*items: Var) -> Constraint:
    """None of these is the same node (or value). (The two fields of a symmetric class are distinct without it)"""
    return Distinct(tuple(items))


def same(a: Var, b: Var) -> Constraint:
    return Same(a, b)


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
    """`SameFamily.Derive(first=a, ...)`: what a rule derives, each field a variable (or, for a literal, a value)"""

    model: type[Derived]
    values: dict[str, Any]

    def when(
        self,
        *items: Any,
        block: Sequence[type] = (),
        allow: Sequence[type] = (),
    ) -> "Body":
        """The body of the rule: the patterns (each a `Model.Where`, with variables), then any constraints. `block`
        and `allow`: semantic spaces (and other wrappers) that this rule does not derive from, or does, whatever their
        `DerivedMeta` says"""
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
