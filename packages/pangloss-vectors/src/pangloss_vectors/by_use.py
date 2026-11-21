"""Classes an item is only *by use* (step 7a.5 of implementation_docs/similarity-build-plan.md): a class that leaves
labels to the data (`__labels_unmanaged__`) is given, in a search narrowed to a class those labels come from, only
where the data uses it as one.

    class Role(Entity): ...
    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType", also=Role)      # RoleType, below Role, leaves `Role` to the data

A `RoleType` ("Banker") is a `RoleType` by class, and a `Role` only by use: it is a result of a search narrowed to
`Role` (`type=Role`, the group `Role`, a field that holds roles) only if a relation that takes a `Role` points at it
from something the reader may look through. That it could be (its class, or the label `Role` its switch gives it) is
not enough, and a relation that takes a `RoleType` (having it as a type, `has_type`; the hierarchy) does not count. A
search narrowed to `RoleType`, or to both, or not narrowed, gives every type.

Nothing is stored: the search's query asks, for a hit of such a class only, whether a counting relation points at it
(`search._used`). What counts is worked out once from the models (`rules`), as plain data: for each class with the
rule, the pairs `(the stored type of the node the edge comes from, the edge's name)` of the relations that count.
Pairs, not names: the edge of a wrapper onto its entity is called `target` whatever it wraps, and its node is stored
with the wrapper's class (`InRole`, not `InRole[Role]`), so a use through a wrapper is `("InRole", "target")`.

Two uses of one generic wrapper can give the same pair, one that counts and one that does not (`InRole[Role]` and an
`InRole[RoleType]` in the same models; a typology's type cannot be in a wrapper, whose relation would have to be called
`has_type`, but another class with unmanaged labels might be): the pair cannot tell them apart, so it counts, and the
models are warned about at the first search that needs the rules (`ByUse.ambiguous`).

The package names no package: the rule is by `__labels_unmanaged__`, which `pangloss_models` reads when it writes labels.
"""

import dataclasses
import logging
from collections.abc import Collection, Iterator
from typing import Any

from pangloss_models import Entity, ModelRegistry

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True, slots=True)
class ByUse:
    """The rule of one class: `classes`, the registered classes above it that it is only by use (`Role`, and what is
    above `Role`), and `uses`, the pairs `(source type, edge name)` of the relations that count as a use of it as one
    of them; `ambiguous`, those of the pairs that a relation that does not count gives too"""

    classes: frozenset[str]
    uses: frozenset[tuple[str, str]]
    ambiguous: frozenset[tuple[str, str]] = frozenset()


def _registered_above(model: type) -> list[str]:
    """The names of the class and of each registered class above it, nearest first"""
    return [
        cls.__name__
        for cls in model.__mro__
        if ModelRegistry._model_dict.get(cls.__name__) is cls
    ]


def by_use_classes(model: type) -> frozenset[str]:
    """The registered classes above `model` that it is only by use: those whose names are among its
    `__labels_unmanaged__`. None for a class without unmanaged labels"""
    unmanaged = set(getattr(model, "__labels_unmanaged__", None) or ())
    if not unmanaged:
        return frozenset()
    return frozenset(name for name in _registered_above(model)[1:] if name in unmanaged)


def by_class(model: type) -> frozenset[str]:
    """The class's name and the registered classes above it that it is by class (every one it is not by use)"""
    return frozenset(_registered_above(model)) - by_use_classes(model)


@dataclasses.dataclass(frozen=True, slots=True)
class _Leaf:
    """An edge onto an entity some node of the models can have: from a node stored as `source`, called `edge`, of
    the fields of `owner` (the class, or the wrapper as it is used, `InRole[Role]`), to an entity of one of `targets`"""

    source: str
    edge: str
    owner: str
    targets: frozenset[str]


def _is_specialisation(model: type) -> bool:
    """A use of a generic class (`InRole[Role]`), registered beside it: its nodes are stored as the generic's"""
    metadata = getattr(model, "__pydantic_generic_metadata__", None) or {}
    return metadata.get("origin") is not None


def _relation_fields(model: type) -> dict[str, Any]:
    meta = getattr(model, "_meta", None)
    fields = getattr(meta, "fields", None)
    return dict(getattr(fields, "relation_fields", None) or {})


def _leaves() -> Iterator[_Leaf]:
    """Every edge onto an entity the registered models can make: the relation fields of each class (a document, an
    entity, an embedded object, a wrapper's own fields), and through each wrapper a field holds, from the wrapper's
    node (stored as its base class: `write_plan.resolve_type_var_options`) by the wrapper's fields, as it is used"""
    from pangloss_models.initialise_models.initialise_incoming_relation_definitions import (
        RELATIONS_TO_WRAPPERS,
    )
    from pangloss_models.field_definitions import RelationToEntity

    seen: set[tuple[str, type]] = set()

    def walk(source: str, model: type) -> Iterator[_Leaf]:
        if (source, model) in seen:
            return
        seen.add((source, model))
        for edge, definition in _relation_fields(model).items():
            targets = frozenset(
                option.annotated_type.__name__
                for option in definition.type_options
                if isinstance(option, RelationToEntity)
            )
            if targets:
                yield _Leaf(source, edge, model.__name__, targets)
            for option in definition.type_options:
                if isinstance(option, RELATIONS_TO_WRAPPERS):
                    yield from walk(option.base_type.__name__, option.annotated_type)

    for name, model in list(ModelRegistry._model_dict.items()):
        if isinstance(model, type) and not _is_specialisation(model):
            yield from walk(name, model)


_RULES: dict[str, ByUse] | None = None


def forget() -> None:
    """(`ModelRegistry.on_reset`, `after_finalise`) the rules are worked out again from the models when next asked"""
    global _RULES
    _RULES = None


def rules() -> dict[str, ByUse]:
    """The rule of each registered class of entities that is by use of another: by its name. Worked out from the
    models when first asked after `initialise()`"""
    global _RULES
    if _RULES is not None:
        return _RULES
    leaves = list(_leaves())
    found: dict[str, ByUse] = {}
    for name, model in ModelRegistry._model_dict.items():
        if not (isinstance(model, type) and issubclass(model, Entity)):
            continue
        classes = by_use_classes(model)
        if not classes:
            continue
        counting = {
            (leaf.source, leaf.edge) for leaf in leaves if leaf.targets & classes
        }
        # (a relation that can hold the class, and none it is by use: the class itself, or one it is by class)
        others = {
            (leaf.source, leaf.edge)
            for leaf in leaves
            if name in leaf.targets and not leaf.targets & classes
        }
        found[name] = ByUse(
            frozenset(classes), frozenset(counting), frozenset(counting & others)
        )
        if counting & others:
            logger.warning(
                "%s is given as %s only where a relation that takes one points at it, but the relations %s are of "
                "fields that do and of fields that do not (one generic wrapper used for both): they count",
                name,
                " or ".join(sorted(classes)),
                ", ".join(
                    f"{source}.{edge}" for source, edge in sorted(counting & others)
                ),
            )
    _RULES = found
    return found


def _field_reaches(spec: str) -> frozenset[str]:
    """The entity classes the field `Model.field` can hold (every one, as `entities_reached` gives them)"""
    from pangloss_models.initialise_models.initialise_incoming_relation_definitions import (
        entities_reached,
    )

    from pangloss_vectors.fields import relation_field

    return frozenset(
        reached.__name__ for reached, _wrapper in entities_reached(relation_field(spec))
    )


def given_by_use(searched: Collection[str], asked: Collection[str]) -> list[str]:
    """Of the classes `searched` (concrete classes, by name), those a hit of which is a result only where something
    uses it as a class it is by use, in the order of their names: a class with the rule that none of the names
    `asked` asks as itself. A name asks a class as itself if it is the class, or a class above it that it is by
    class (`RoleType` asks every type); a field (`Model.field`) if it can hold the class and no class it is by use
    (a field that takes `RoleType`; one that takes `Role` gives a type only where something uses it as one)"""
    found = rules()
    given = []
    for name in searched:
        rule = found.get(name)
        if rule is None:
            continue
        model = ModelRegistry._model_dict[name]
        itself = by_class(model)
        as_itself = False
        for asked_name in asked:
            if "." in asked_name:
                reaches = _field_reaches(asked_name)
                as_itself = name in reaches and not reaches & rule.classes
            else:
                as_itself = asked_name in itself
            if as_itself:
                break
        if not as_itself:
            given.append(name)
    return sorted(given)


def parameters(classes: Collection[str]) -> dict[str, Any]:
    """What the search's query is given for the classes `classes` (`given_by_use`): `by_use_types`, their names, and
    `by_use`, a map for each pair that counts for each, `{type, source, edge}`"""
    found = rules()
    return {
        "by_use_types": sorted(classes),
        "by_use": [
            {"type": name, "source": source, "edge": edge}
            for name in sorted(classes)
            for source, edge in sorted(found[name].uses)
        ],
    }


def install() -> None:
    if forget not in ModelRegistry.on_reset:
        ModelRegistry.on_reset.append(forget)
    if forget not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(forget)


install()
