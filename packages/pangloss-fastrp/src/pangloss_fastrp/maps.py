"""The rules of the joined graph as plain data, worked out of the models (implementation_docs/similarity-build-plan.md,
step 3.1; the rules are those of implementation_docs/graph-embeddings.md, "The joined graph, as now proposed").

`graph_maps()` gives a `maths.GraphMaps`, which an engine is handed as it is (it survives `json.dumps`: the Memgraph
module gets it as a parameter). Everything goes by a node's `type`, the name of its own class: a node of a class
below a wrapper has its own label and not the wrapper's, so each class below a class that says something is named
itself, with what it inherits. A use of a generic (`InRole[Agent]`) is a node of the generic (`InRole`).

- `kinds`: a class of documents or entities is a `stop` (a nested document too; an abstract class has no nodes and
  no entry); a wrapper (`ReifiedRelation`, `ReifiedRelationDocument`, `Conjunction`, `SemanticSpace`, `Embedded`)
  is `through`, or `end` with `FastRPMeta(stop=True)`; `out` with `FastRPMeta(include=False)` and for a derived
  document (`pangloss_derived.DerivedDocument`). A cited basis (`PGCitedBasis`), a node of the citing document that
  holds citations of what it stands for, is `through`, holding `basis`.
- `citations`: the classes of a node that names a document by its id (`PGCitation`, `PGUnprotectedCitation`); they
  need no kind.
- `class_weight`, `own`, `field_weight` (`"Type.field"`): from `FastRPMeta`, only what is not the default.
- `held`: a wrapper's fields that hold what it wraps (`held_field_names`); its other relations are its own.
- `shares`: `"Type.field"` → `[property, total]` for a field with `SumsTo` (`WeightedAlternative.alternatives`:
  `["percent", 100]`).
- `steps`, `dimension`, `sees`: the settings `FASTRP_STEPS`, `FASTRP_DIMENSION`, `VECTORS_GRAPH_SEES`.

What comes of the models is kept from the first use after `initialise()` and forgotten when the models are
(`ModelRegistry.on_reset`, `after_finalise`); the settings are read at each call.
"""

import dataclasses
import sys
from typing import Any

lazy from pangloss_fastrp.maths import GraphMaps

from pangloss_fastrp.meta import (
    DEFAULT,
    ITEM_KINDS,
    WRAPPER_KINDS,
    declared_classes,
    fastrp_meta,
)
from pangloss_fastrp.settings import dimension, graph_sees, steps

# (`pangloss_models.citations`: a cited basis holds its citations in this field)
BASIS_FIELD = "basis"

_found: Any = None


def forget() -> None:
    """(`ModelRegistry.on_reset`, `after_finalise`) the models changed: work the maps out again at the next use"""
    global _found
    _found = None


def _is_derived_document(model: type) -> bool:
    # (without importing pangloss_derived: if its module is not loaded, no class can be a derived document)
    documents = sys.modules.get("pangloss_derived.documents")
    derived = getattr(documents, "DerivedDocument", None)
    return isinstance(derived, type) and issubclass(model, derived)


def _shares(model: type) -> dict[str, list[Any]]:
    from pangloss_models import SumsTo

    fields = getattr(getattr(model, "_meta", None), "fields", None)
    found: dict[str, list[Any]] = {}
    for name, definition in (
        fields.relation_fields if fields is not None else {}
    ).items():
        for validator in getattr(definition, "validators", ()) or ():
            if isinstance(validator, SumsTo):
                found[f"{model.__name__}.{name}"] = [validator.field, validator.total]
    return found


def build_maps() -> GraphMaps:
    """The maps of the registered models, with the default settings"""
    from pangloss_models.citations import BASIS, CITATION_TYPES
    from pangloss_models.search import held_field_names

    from pangloss_fastrp.maths import END, OUT, STOP, THROUGH, GraphMaps

    kinds: dict[str, str] = {}
    class_weight: dict[str, float] = {}
    held: dict[str, list[str]] = {}
    own: dict[str, bool] = {}
    field_weight: dict[str, float] = {}
    shares: dict[str, list[Any]] = {}
    citations: dict[str, bool] = {}
    documents: dict[str, bool] = {}
    for name, model in declared_classes():
        kind = getattr(model, "__metatype__", None)
        meta = fastrp_meta(model)
        if name in CITATION_TYPES:
            citations[name] = True
            continue
        if kind in ITEM_KINDS:
            if getattr(getattr(model, "_meta", None), "abstract", False):
                continue
            if name == BASIS:
                kinds[name] = THROUGH
                held[name] = [BASIS_FIELD]
            elif not meta.include or _is_derived_document(model):
                kinds[name] = OUT
                continue
            else:
                kinds[name] = STOP
                if kind == "Document":
                    documents[name] = True
        elif kind in WRAPPER_KINDS:
            kinds[name] = END if meta.stop else THROUGH
            names = sorted(held_field_names(model))
            if names:
                held[name] = names
            if meta.stop:
                continue
            if meta.own != DEFAULT.own:
                own[name] = meta.own
        else:
            continue
        if meta.weight != DEFAULT.weight:
            class_weight[name] = float(meta.weight)
        for field, weight in sorted(meta.weights.items()):
            if weight != 1:
                field_weight[f"{name}.{field}"] = float(weight)
        shares.update(_shares(model))
    return GraphMaps(
        kinds=kinds,
        class_weight=class_weight,
        held=held,
        own=own,
        field_weight=field_weight,
        shares=shares,
        citations=citations,
        documents=documents,
    )


def graph_maps(settings: Any = None) -> GraphMaps:
    """The rules of the joined graph, for the models as they are and the settings"""
    global _found
    if _found is None:
        _found = build_maps()
    return dataclasses.replace(
        _found,
        steps=steps(settings),
        dimension=dimension(settings),
        sees=graph_sees(settings),
    )


def signature(settings: Any = None) -> str:
    """A hash of the maps: of everything the graph part's vectors depend on"""
    from pangloss_vectors.parts import signature_of

    return signature_of(graph_maps(settings).plain())
