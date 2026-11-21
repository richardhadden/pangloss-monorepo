"""`_fastrp_meta`: how a class counts in the joined graph of the graph part (implementation_docs/graph-embeddings.md,
"The joined graph, as now proposed"; implementation_docs/similarity-build-plan.md, step 3.1).

    class Mention(Statement):
        _fastrp_meta = FastRPMeta(weight=0.2, weights={"bystanders": 0.5})

    class Hypothetical[T](SemanticSpace[T]):
        _fastrp_meta = FastRPMeta(stop=True)

    class InRole[T](ReifiedRelation[T]):
        _fastrp_meta = FastRPMeta(own=False)

A subclass has its parent's setting unless it sets its own (a trait's counts for the classes that have it); a class
with none anywhere is `FastRPMeta()`.

- `weight` (0 or more, 1): of a class of documents or entities, the weight of every join that starts from one of its
  items; of a wrapper class, of every chain that passes through one of its nodes.
- `weights` (`{field: weight}`): the weight of the joins made through a field of the class.
- `stop=True` (a wrapper class only): a chain that reaches one of its nodes ends there, with no join (a `Negative`).
- `own=False` (a wrapper class only): the wrapper's own relations (`InRole.at`, beside the `target` it holds) are not
  joined to the document the chain started from.
- `include=False` (a class of documents or entities only): its items are out of the joined graph and have no graph
  vector.

Refused at `initialise()`, by the name of the class that says it: a field the class has not (or one that is no
relation nor embedded object), a weight below 0, `stop` or `own` on a class that is not a wrapper, `include=False` on
a wrapper, the slot on an edge model.
"""

import dataclasses
from collections.abc import Mapping
from typing import Any

from pangloss_models import ModelRegistry, PanglossMetaError, register_meta_slot
from pangloss_models.meta_slots import declared_slots

SLOT = "_fastrp_meta"

# The kinds of node a chain passes through (`pangloss_models.search.WRAPPER_LABELS`, and embedded objects, which are
# nodes joined like a relation)
WRAPPER_KINDS = (
    "ReifiedRelation",
    "ReifiedRelationDocument",
    "Conjunction",
    "SemanticSpace",
    "Embedded",
)
ITEM_KINDS = ("Document", "Entity")


@dataclasses.dataclass(frozen=True)
class FastRPMeta:
    weight: float = 1.0
    """Of a class of documents or entities, every join that starts from it; of a wrapper class, every chain through
    it"""

    weights: Mapping[str, float] = dataclasses.field(default_factory=dict)
    """A weight for each field of the class that is not 1"""

    stop: bool = False
    """(A wrapper class) a chain ends here with no join"""

    own: bool = True
    """(A wrapper class) whether its own relations are joined to the document the chain started from"""

    include: bool = True
    """(A class of documents or entities) whether its items are in the joined graph"""


register_meta_slot(SLOT, FastRPMeta)

DEFAULT = FastRPMeta()


def fastrp_meta(model: type) -> FastRPMeta:
    """The class's setting, its parent's, or the default"""
    meta = getattr(model, SLOT, None)
    return meta if isinstance(meta, FastRPMeta) else DEFAULT


def declarer(model: type) -> str:
    """The name of the class that sets the setting `model` has (itself, a parent or a trait)"""
    for cls in model.__mro__:
        if SLOT in declared_slots(cls):
            return cls.__name__
    return model.__name__


def is_use_of_generic(name: str, model: type) -> bool:
    """`InRole[Agent]`, or a generic base made by pydantic (`ReifiedRelation[TypeVar]`): a node of it has the
    `type` of the generic class it is a use of"""
    metadata = getattr(model, "__pydantic_generic_metadata__", None) or {}
    return "[" in name or metadata.get("origin") is not None


def declared_classes() -> list[tuple[str, type]]:
    """The registered classes a node can be of, by name: no uses of generics"""
    return [
        (name, model)
        for name, model in sorted(ModelRegistry._model_dict.items())
        if isinstance(model, type) and not is_use_of_generic(name, model)
    ]


def weightable_fields(model: type) -> set[str]:
    """The fields of a class that are edges: relations and embedded objects"""
    fields = getattr(getattr(model, "_meta", None), "fields", None)
    if fields is None:
        return set()
    return set(fields.relation_fields) | set(fields.embedded_fields)


def _is_weight(value: Any) -> bool:
    return (
        not isinstance(value, bool) and isinstance(value, (int, float)) and value >= 0
    )


def check_meta() -> None:
    """(`ModelRegistry.after_finalise`, when the fields of every class are known) refuse what a `FastRPMeta` cannot
    mean, by the name of the class that says it"""
    for name, model in declared_classes():
        meta = getattr(model, SLOT, None)
        if not isinstance(meta, FastRPMeta):
            continue
        said = declarer(model)
        kind = getattr(model, "__metatype__", None)
        if SLOT in declared_slots(model):
            if not _is_weight(meta.weight):
                raise PanglossMetaError(
                    f"{name}: FastRPMeta(weight={meta.weight!r}) is a number of 0 or more (the weight of the joins "
                    "through the class)"
                )
            if not isinstance(meta.weights, Mapping):
                raise PanglossMetaError(
                    f"{name}: FastRPMeta(weights=...) is a weight for each field, {{'field': 0.5}}, not "
                    f"{meta.weights!r}"
                )
            for field, weight in meta.weights.items():
                if not _is_weight(weight):
                    raise PanglossMetaError(
                        f"{name}: FastRPMeta(weights={{{field!r}: {weight!r}}}) is a number of 0 or more"
                    )
            if kind == "EdgeModel":
                raise PanglossMetaError(
                    f"{name}: FastRPMeta is for a class of documents, entities or wrappers; an edge model is "
                    "neither (its edges have the weight of their field)"
                )
        if kind in ITEM_KINDS:
            if meta.stop:
                raise PanglossMetaError(
                    f"{said}: FastRPMeta(stop=True) is for a wrapper class (a reified relation, a semantic space, "
                    f"a conjunction or an embedded object), and {name} is a class of "
                    f"{'documents' if kind == 'Document' else 'entities'}: use include=False to leave it out"
                )
            if not meta.own:
                raise PanglossMetaError(
                    f"{said}: FastRPMeta(own=False) is for a wrapper class (its relations beside what it holds), "
                    f"and {name} is a class of {'documents' if kind == 'Document' else 'entities'}"
                )
        elif kind in WRAPPER_KINDS:
            if not meta.include:
                raise PanglossMetaError(
                    f"{said}: FastRPMeta(include=False) is for a class of documents or entities; {name} is a "
                    "wrapper, which has no vector: use stop=True to end the chains through it, or weight=0"
                )
        else:
            continue
        if meta.weights:
            known = weightable_fields(model)
            for field in meta.weights:
                if field not in known:
                    raise PanglossMetaError(
                        f"{said}: FastRPMeta(weights=...) names {field!r}, which is not a relation or embedded "
                        f"field of {name}"
                    )


def install() -> None:
    if check_meta not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check_meta)


# (done as soon as a model can say it, whether or not the app is installed)
install()
