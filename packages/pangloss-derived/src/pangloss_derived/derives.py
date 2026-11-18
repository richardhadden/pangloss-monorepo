"""An edge declared on a document class: "the entities in this field relate to the entities in that one", with no class
or rule written out.

    class Transfer(Statement):
        _derives = [
            DerivesEdge("GaveTo", subject="given_by", object="given_to", reverse_name="received_from",
                        types=[exchange]),
        ]
        given_by: Agent
        given_to: Agent

    class Activity(Statement):
        _derives = [DerivesEdge("CoParticipants", subject="participants", object="participants", symmetric=True)]
        participants: list[Agent]

When the models are initialised each becomes **an ordinary `DerivedEdge` class and an ordinary rule**, so everything
that holds of those holds of it: the worker, justifications, contexts, the graph, the API, the interface. For
`Transfer` it is the same as writing, in `derived.py`:

    class GaveTo(DerivedEdge):
        given_by: Annotated[Agent, Subject()]
        given_to: Annotated[Agent, Object(reverse_name="received_from")]

    @rule(types=[exchange])
    def Transfer__GaveTo(a: Var[Agent], b: Var[Agent]):
        return GaveTo.Derive(given_by=a, given_to=b).when(Transfer.Where(given_by=a, given_to=b))

See implementation_docs/derived.md, "An edge declared on a document class".
"""

import dataclasses
import inspect
import sys
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, cast

from pangloss_models import Document, Entity, ModelRegistry, Var, register_meta_slot
from pangloss_models.meta_slots import declared_slots

from pangloss_derived.declare import (
    DerivedEdge,
    Object,
    Rule,
    RuleType,
    Subject,
    SymmetricLabel,
)
from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError

SLOT = "_derives"


@dataclasses.dataclass(frozen=True)
class DerivesEdge:
    """One edge that a document class gives, in the list `_derives` of the class:

    - `name`: the name of the `DerivedEdge` class it makes (`DerivedEdge.named(name)`);
    - `subject`, `object`: the fields of the document whose entities are the two ends. A field through a reified
      relation, a conjunction or a semantic space is seen through as a rule sees through it; a list field gives each
      of its items, and two list fields every pair;
    - `symmetric`: the order of the two does not matter. The same field as both (`participants` and `participants`:
      everyone who took part, with everyone else) has to be symmetric, and never pairs a thing with itself;
    - `reverse_name`: of an asymmetric edge, its name as read from its object (`received_from`);
    - `label`: of a symmetric edge, the one name of its two ends in the interface (by default the subject field's);
    - `ends`: the names of the two ends on the edge (by default those of the two fields; `first` and `second` when
      they are one field). To be given when several document classes give one edge, from fields of different names:
      `Transfer` and `Sale` both `DerivesEdge("GaveTo", ..., ends=("giver", "receiver"))`;
    - `qualifiers`: what else defines the edge, each a name on the edge and the field of the document it is read
      from (a literal, or a relation to an entity): `{"year": "year", "at": "place"}`. A document without a value
      for one gives no edge;
    - `types`: the `RuleType`s of its rule (declared in the models' module, or one it imports);
    - `max_per_seed`, `description`: as the `Meta` and the docstring of a `DerivedEdge` class.

    A subclass of the document class gives the edge too (the rule's pattern matches it), and gets no rule of its own;
    it may declare its own, more particular edges. Several document classes may declare one name: they must agree on
    everything but the fields (and the types of rule), and the class of each end is the nearest that all their fields
    share."""

    name: str
    subject: str
    object: str
    symmetric: bool = False
    reverse_name: str | None = None
    label: str | None = None
    ends: tuple[str, str] | None = None
    qualifiers: Mapping[str, str] = dataclasses.field(default_factory=dict)
    types: Sequence[RuleType] = ()
    max_per_seed: int | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        def wrong(message: str) -> None:
            raise PanglossDerivedError(f"DerivesEdge({self.name!r}): {message}")

        if not isinstance(self.name, str) or not self.name.isidentifier():
            wrong("the name of the edge is the name of a class (letters, digits and _)")
        for which in ("subject", "object"):
            if not isinstance(getattr(self, which), str):
                wrong(f"`{which}` is the name of a field of the document class")
        if self.subject == self.object and not self.symmetric:
            wrong(
                f"the field {self.subject!r} is both ends: that needs symmetric=True (each with each other, and "
                "never a thing with itself)"
            )
        if self.symmetric and self.reverse_name is not None:
            wrong(
                "a symmetric edge reads the same from both ends: it has no reverse_name"
            )
        if not self.symmetric and self.label is not None:
            wrong(
                "`label` is the one name of the two ends of a symmetric edge; the ends of this one are named "
                "by `ends`"
            )
        # (checked as it is for a class that is written out)
        Object(reverse_name=self.reverse_name)
        if self.ends is not None:
            ends = tuple(self.ends)
            if (
                len(ends) != 2
                or ends[0] == ends[1]
                or not all(isinstance(e, str) and e.isidentifier() for e in ends)
            ):
                wrong(
                    f'`ends` is the names of the two ends, like ("giver", "receiver"): not {self.ends!r}'
                )
            object.__setattr__(self, "ends", ends)
        for name, field in dict(self.qualifiers).items():
            if not (
                isinstance(name, str) and name.isidentifier() and isinstance(field, str)
            ):
                wrong(
                    "`qualifiers` gives each qualifier's name on the edge and the field it is read from: "
                    '{"year": "year"}'
                )
            if name in self.end_names:
                wrong(f"the qualifier {name!r} has the name of an end")
        object.__setattr__(self, "qualifiers", dict(self.qualifiers))
        types = tuple(self.types)
        for rule_type in types:
            if not isinstance(rule_type, RuleType):
                wrong(
                    f"{rule_type!r} is not a RuleType (declare one: RuleType('social'))"
                )
        object.__setattr__(self, "types", types)

    @property
    def end_names(self) -> tuple[str, str]:
        if self.ends is not None:
            return self.ends[0], self.ends[1]
        if self.subject == self.object:
            return "first", "second"
        return self.subject, self.object

    @property
    def symmetric_label(self) -> str | None:
        if not self.symmetric:
            return None
        return self.label or self.subject

    def shape(self) -> tuple:
        """What every declaration of one name has to agree on"""
        return (
            self.end_names,
            self.symmetric,
            self.reverse_name,
            self.symmetric_label,
            tuple(sorted(self.qualifiers)),
            self.max_per_seed,
        )


register_meta_slot(SLOT, list, plain_name=True)


# ---------------------------------------------------------------------------
# What a field of a document reaches
# ---------------------------------------------------------------------------


def declared_on(model: type) -> list[DerivesEdge]:
    """The edges the class declares itself (not those of its parents, which have their own rules)"""
    if SLOT not in declared_slots(model):
        return []
    declared = getattr(model, SLOT, None) or []
    for item in declared:
        if not isinstance(item, DerivesEdge):
            raise PanglossDerivedError(
                f"{model.__name__}._derives is a list of DerivesEdge(...): not {item!r}"
            )
    return list(declared)


def is_declared(candidate: type) -> bool:
    """A class or trait of the project (not the library's own `Entity`, `Trait`, or what they are made of)"""
    from pangloss_models import Trait
    from pangloss_models.utils import model_is_trait

    if candidate is Entity or candidate is Trait:
        return False
    if isinstance(candidate, type) and issubclass(candidate, Entity):
        return candidate.__module__.split(".")[0] != "pangloss_models"
    try:
        return model_is_trait(cast(Any, candidate))
    except TypeError:
        return False


def nearest_common(options: Sequence[type]) -> type:
    """The most particular class or trait that every one of the classes is: `Person` and `Group` are `Agent`s. `Entity`
    if they share nothing of the project's"""
    first, *rest = options
    for candidate in first.__mro__:
        if is_declared(candidate) and all(issubclass(o, candidate) for o in rest):
            return candidate
    return Entity


def reach_of(model: Any, field: str, where: str) -> tuple[str, Any]:
    """What a field of the document class is, for an edge: `("relation", [the entity classes it can reach])` or
    `("literal", its type)`. Anything else is refused"""
    from pangloss_models.search import field_kind

    definition = getattr(model._meta, "fields", {}).get(field)
    if definition is None:
        known = ", ".join(getattr(model._meta, "fields", {}))
        raise PanglossDerivedError(
            f"{where}: {model.__name__} has no field {field!r} (it has: {known})"
        )
    found = field_kind(definition)
    if isinstance(found, str):
        raise PanglossDerivedError(f"{where}: {model.__name__}.{field}: {found}")
    kind, base = found
    if kind == "relation":
        # (what else the field can hold gives no edge: a mention that has not been reconciled with an entity yet,
        # which is a document, is not at an end of one)
        entities = [
            o for o in base.options if isinstance(o, type) and issubclass(o, Entity)
        ]
        if not entities:
            others = ", ".join(sorted(o.__name__ for o in base.options))
            raise PanglossDerivedError(
                f"{where}: {model.__name__}.{field} is not a relation to entities (it holds: {others or 'nothing'})"
            )
        return "relation", entities
    return "literal", base


# ---------------------------------------------------------------------------
# Making the classes and the rules
# ---------------------------------------------------------------------------


def where_of(model: type, declaration: DerivesEdge) -> str:
    return f"{model.__name__}._derives, {declaration.name}"


def gather() -> dict[str, list[tuple[type, DerivesEdge]]]:
    """Every declaration, by the name of its edge, in the order the classes were declared"""
    found: dict[str, list[tuple[type, DerivesEdge]]] = {}
    seen: set[type] = set()
    for model in ModelRegistry.all_models().values():
        if not isinstance(model, type) or model in seen:
            continue
        seen.add(model)
        if (getattr(model, "__pydantic_generic_metadata__", None) or {}).get("origin"):
            continue
        declarations = declared_on(model)
        if declarations and not issubclass(model, Document):
            raise PanglossDerivedError(
                f"{model.__name__}._derives: an edge is declared on a document class (what says that the two are "
                f"related), not on {'an entity' if issubclass(model, Entity) else 'this'}"
            )
        names = [d.name for d in declarations]
        for name in names:
            if names.count(name) > 1:
                raise PanglossDerivedError(
                    f"{model.__name__}._derives declares {name} twice: one document gives an edge once (two "
                    "pairs of fields are two edges, of two names)"
                )
        for declaration in declarations:
            found.setdefault(declaration.name, []).append((model, declaration))
    return found


def module_of(model: type) -> str:
    return model.__module__


def make_class(
    name: str, declarations: list[tuple[type, DerivesEdge]]
) -> type[DerivedEdge]:
    """The `DerivedEdge` class of the declarations of one name"""
    known = DerivedRegistry.classes.get(name)
    if known is not None and not getattr(known, "_declared_on", None):
        model, _ = declarations[0]
        raise PanglossDerivedError(
            f"{model.__name__}._derives, {name}: there is a DerivedEdge class {name} already (in "
            f"{known.__module__}). Give this one another name, or write a rule for that class"
        )
    first_model, first = declarations[0]
    for model, declaration in declarations[1:]:
        if declaration.shape() != first.shape():
            raise PanglossDerivedError(
                f"{name} is declared on {first_model.__name__} and on {model.__name__}, which do not agree: every "
                "declaration of one edge has the same `ends` (give them, where the fields' names differ), "
                "`symmetric`, `reverse_name`, `label`, `max_per_seed` and the same names of `qualifiers`"
            )
    subject_name, object_name = first.end_names
    subjects: list[type] = []
    objects: list[type] = []
    qualifiers: dict[str, list[tuple[str, Any, str]]] = {
        q: [] for q in first.qualifiers
    }
    for model, declaration in declarations:
        where = where_of(model, declaration)
        for field, found in (
            (declaration.subject, subjects),
            (declaration.object, objects),
        ):
            kind, reach = reach_of(model, field, where)
            if kind != "relation":
                raise PanglossDerivedError(
                    f"{where}: {model.__name__}.{field} is not a relation to entities: an end of an edge is an "
                    "entity"
                )
            found += reach
        for qualifier, field in declaration.qualifiers.items():
            kind, reach = reach_of(model, field, where)
            qualifiers[qualifier].append((kind, reach, where))
    if first.symmetric:
        # (either end may be either field's: one class for both)
        subjects = objects = [*subjects, *objects]
    annotations: dict[str, Any] = {}
    subject_class, object_class = nearest_common(subjects), nearest_common(objects)
    if first.symmetric:
        label = SymmetricLabel(first.symmetric_label or first.subject)
        annotations[subject_name] = cast(Any, Annotated)[subject_class, label]
        annotations[object_name] = cast(Any, Annotated)[object_class, label]
    else:
        annotations[subject_name] = cast(Any, Annotated)[subject_class, Subject()]
        annotations[object_name] = cast(Any, Annotated)[
            object_class, Object(reverse_name=first.reverse_name)
        ]
    for qualifier, found in qualifiers.items():
        kinds = {kind for kind, _, _ in found}
        if len(kinds) > 1:
            raise PanglossDerivedError(
                f"{name}: the qualifier {qualifier!r} is an entity in one declaration and a value in another "
                f"({'; '.join(where for _, _, where in found)})"
            )
        if kinds == {"relation"}:
            annotations[qualifier] = nearest_common(
                [o for _, reach, _ in found for o in reach]
            )
        else:
            types = {reach for _, reach, _ in found}
            if len(types) > 1:
                raise PanglossDerivedError(
                    f"{name}: the qualifier {qualifier!r} is of different types in its declarations: "
                    + ", ".join(sorted(getattr(t, "__name__", str(t)) for t in types))
                )
            annotations[qualifier] = types.pop()
    meta = DerivedEdge.Meta(
        symmetric=first.symmetric,
        max_per_seed=first.max_per_seed or DerivedEdge.Meta().max_per_seed,
    )
    description = next((d.description for _, d in declarations if d.description), None)
    module = module_of(first_model)
    made = type(
        name,
        (DerivedEdge,),
        {
            "__annotations__": annotations,
            "__module__": module,
            "__qualname__": name,
            "__doc__": description
            or f"From {' and '.join(m.__name__ for m, _ in declarations)}",
            "_meta": meta,
            "_declared_on": tuple(m for m, _ in declarations),
        },
    )
    # (so that it can be imported from where its document class is, once the models are initialised, and so that
    # `pangloss make-stubs` writes it there: only where the document class itself can be)
    home = sys.modules.get(module)
    if (
        home is not None
        and getattr(home, first_model.__qualname__, None) is first_model
    ):
        if getattr(home, name, made) is made or getattr(
            getattr(home, name, None), "_declared_on", None
        ):
            setattr(home, name, made)
    return made


def make_rule(model: Any, declaration: DerivesEdge, edge: type[DerivedEdge]) -> Rule:
    """The rule of one declaration: the document, with an entity of each field"""
    where = where_of(model, declaration)
    subject_name, object_name = declaration.end_names
    same_field = declaration.subject == declaration.object
    variables: dict[str, type] = {
        "a": nearest_common(reach_of(model, declaration.subject, where)[1]),
        "b": nearest_common(reach_of(model, declaration.object, where)[1]),
    }
    for qualifier, field in declaration.qualifiers.items():
        kind, reach = reach_of(model, field, where)
        variables[f"q_{qualifier}"] = (
            nearest_common(reach) if kind == "relation" else reach
        )
    if same_field:
        variables = {"doc": model, **variables}

    def body(**v: Var) -> Any:
        head = edge.Derive(
            **{subject_name: v["a"], object_name: v["b"]},
            **{q: v[f"q_{q}"] for q in declaration.qualifiers},
        )
        values = {field: v[f"q_{q}"] for q, field in declaration.qualifiers.items()}
        if same_field:
            # (two of the items of one field of one document)
            return head.when(
                model.Where(is_=v["doc"], **{declaration.subject: v["a"]}, **values),
                model.Where(is_=v["doc"], **{declaration.object: v["b"]}),
            )
        return head.when(
            model.Where(
                **{declaration.subject: v["a"], declaration.object: v["b"]}, **values
            )
        )

    name = f"{model.__name__}__{declaration.name}"
    body.__name__ = body.__qualname__ = name
    body.__module__ = model.__module__
    cast(Any, body).__signature__ = inspect.Signature(
        [
            inspect.Parameter(
                variable,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=cast(Any, Var)[kind],
            )
            for variable, kind in variables.items()
        ]
    )
    fields = (
        f"two of `{declaration.subject}`"
        if same_field
        else f"`{declaration.subject}` and `{declaration.object}`"
    )
    return Rule(
        name=name,
        function=body,
        types=tuple(declaration.types),
        description=declaration.description or f"{fields} of one {model.__name__}",
    )


def make_declared_edges() -> None:
    """(At `initialise`, before the apps' `derived.py` are read) the class and the rules of every `DerivesEdge`"""
    for name, declarations in gather().items():
        edge = make_class(name, declarations)
        for model, declaration in declarations:
            DerivedRegistry.add_rule(make_rule(model, declaration, edge))
