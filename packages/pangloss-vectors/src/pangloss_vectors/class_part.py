"""The class part (`"class"`): a vector of what an item is, from the hierarchy of the models alone, beside the parts
the graph gives (implementation_docs/graph-embeddings.md, "Similar by class: the hierarchy as part of the vector";
implementation_docs/similarity-build-plan.md, step 2.3).

- **One dimension for each declared class of documents or entities** (abstract ones too) **and each semantic trait**
  (`SemanticTrait`, `SemanticNonHeritableTrait`), in the order of their names.
- **An item's vector** is its class at 1, each class above it at `decay ** depth` (`VECTORS_CLASS_DECAY`), a semantic
  trait as if it were a parent of the class that has it (and its own semantic traits above it further up), normalised
  to length one. A `SemanticNonHeritableTrait` counts only for the class that names it, not for its subclasses. Where
  there are several ways up to one dimension, the nearest (the largest value) counts. Plain traits, ontology mixins,
  the kinds and generic bases are never dimensions.
- **A class an item fulfils** (`Fulfils`) counts only while it does: a node has the class's label then, and the
  class's own vector (before normalising) is added at `decay`, as a parent would be. Any other label is ignored.

What is worked out of the models is kept from the first use after `initialise()` and forgotten when the models are
(`ModelRegistry.on_reset`, `after_finalise`). The class part reads nothing of an item's contents, so it does not
follow `VECTORS_GRAPH_SEES`: every head that is not deleted nor merged into another has a vector, and a search hides
what a reader may not see.
"""

import dataclasses
import math
from collections.abc import Iterable, Mapping, Sequence
from inspect import isclass
from typing import Any

from pangloss_models import ModelRegistry

from pangloss_vectors.parts import (
    Changed,
    Refreshed,
    Vector,
    VectorRow,
    Writer,
    signature_of,
)
from pangloss_vectors.settings import class_decay

NAME = "class"

# (heads read in each page of a rebuild, and the ids looked up in each query of a refresh)
PAGE = 1000

# The kinds of head the class part gives a vector (`ReifiedRelationDocument` and the rest are never heads a search
# gives)
KINDS = ("Document", "Entity")


def _is_generic(model: type) -> bool:
    """A generic base (`class Wrapper[T](Document)`) or a use of one (`Wrapper[Person]`)"""
    metadata = getattr(model, "__pydantic_generic_metadata__", None) or {}
    return bool(metadata.get("parameters")) or "[" in model.__name__


def _is_class(model: Any) -> bool:
    """A declared class of documents or entities that has a dimension"""
    from pangloss_models import Document, Entity

    return (
        isclass(model)
        and issubclass(model, (Document, Entity))
        and ModelRegistry._model_dict.get(model.__name__) is model
        and not _is_generic(model)
    )


def _is_semantic_trait(model: Any) -> bool:
    from pangloss_models.utils import model_is_semantic_trait

    return (
        isclass(model)
        and ModelRegistry._model_dict.get(model.__name__) is model
        and model_is_semantic_trait(model)
    )


def _is_non_heritable(model: type) -> bool:
    from pangloss_models import SemanticNonHeritableTrait

    return issubclass(model, SemanticNonHeritableTrait)


def _depths(model: type) -> dict[str, int]:
    """The dimensions of a class's vector, each with how far above the class it is (the class itself 0): the nearest
    way up, where there are several"""
    from pangloss_models.utils import get_top_level_classes

    top = get_top_level_classes()
    found: dict[str, int] = {model.__name__: 0}

    def put(name: str, depth: int) -> None:
        if depth < found.get(name, depth + 1):
            found[name] = depth

    def walk(cls: type, depth: int, own: bool) -> None:
        # (`own`: still among the class itself and the traits it names, where a non-heritable trait counts)
        for base in cls.__bases__:
            if base in top or base is object:
                continue
            if _is_class(base):
                put(base.__name__, depth + 1)
                walk(base, depth + 1, own=False)
            elif _is_semantic_trait(base):
                if _is_non_heritable(base) and not own:
                    continue
                put(base.__name__, depth + 1)
                walk(base, depth + 1, own)
            else:
                # (a plain trait, `Fulfils[...]`, a mixin, a use of a generic: no dimension, nor a step up; what is
                # above it may be one)
                walk(base, depth, own)

    walk(model, 0, own=True)
    return found


@dataclasses.dataclass(frozen=True)
class ClassMaps:
    """What the class part works out of the models, independent of the decay"""

    names: tuple[str, ...]
    """The dimensions, in order"""

    depths: Mapping[str, Mapping[str, int]]
    """For each class, its dimensions and how far above it each is"""

    fulfilled: Mapping[str, Mapping[str, int]]
    """For each class that can be fulfilled, by its label: its own dimensions and depths"""

    @property
    def position(self) -> dict[str, int]:
        return {name: i for i, name in enumerate(self.names)}


def _fulfillable(models: Iterable[type]) -> set[type]:
    """Every class some model can fulfil (what `Fulfils` names, through the fields that supply it)"""
    found: set[type] = set()
    for model in models:
        meta = getattr(model, "_meta", None)
        fields = getattr(meta, "fields", None) or {}
        for definition in fields.values():
            for fulfilment in getattr(definition, "field_required_to_fulfil", ()):
                found.add(fulfilment.fulfils_class)
    return found


def build_maps() -> ClassMaps:
    """The class part's maps, from the registered models"""
    registered = list(ModelRegistry._model_dict.values())
    classes = [m for m in registered if _is_class(m)]
    traits = [m for m in registered if _is_semantic_trait(m)]
    names = tuple(sorted({m.__name__ for m in (*classes, *traits)}))
    depths = {m.__name__: _depths(m) for m in classes}
    fulfilled = {
        m.__name__: depths[m.__name__]
        for m in _fulfillable(classes)
        if m.__name__ in depths
    }
    return ClassMaps(names=names, depths=depths, fulfilled=fulfilled)


class ClassPart:
    """The part: an object, registered when `pangloss_vectors` is imported"""

    name = NAME
    local = True
    requires: frozenset[str] = frozenset()
    weight = 0.1

    def __init__(self) -> None:
        self._maps: ClassMaps | None = None

    def __repr__(self) -> str:
        return "ClassPart()"

    # -- what the models say -----------------------------------------------------------------------------------------

    def forget(self) -> None:
        """(`ModelRegistry.on_reset`, `after_finalise`) the models changed: work the maps out again at the next use"""
        self._maps = None

    def maps(self) -> ClassMaps:
        if self._maps is None:
            self._maps = build_maps()
        return self._maps

    def dimension(self) -> int:
        return len(self.maps().names)

    def signature(self) -> str:
        found = self.maps()
        return signature_of(
            list(found.names),
            {name: dict(d) for name, d in found.depths.items()},
            sorted(found.fulfilled),
            class_decay(),
        )

    def vector(self, type_name: str, labels: Iterable[str] = ()) -> list[float] | None:
        """The vector of an item of the class `type_name` whose node has these labels (those of the classes it fulfils
        count); None for a name that is no class of documents or entities"""
        found = self.maps()
        own = found.depths.get(type_name)
        if own is None:
            return None
        depths = dict(own)
        for label in labels:
            if label == type_name or label not in found.fulfilled:
                continue
            for name, depth in found.fulfilled[label].items():
                if depth + 1 < depths.get(name, depth + 2):
                    depths[name] = depth + 1
        decay = class_decay()
        position = found.position
        values = [0.0] * len(found.names)
        for name, depth in depths.items():
            # (`0 ** 0` is 1: the class itself, whatever the decay)
            values[position[name]] = decay**depth
        length = math.sqrt(sum(x * x for x in values))
        return [x / length for x in values]

    # -- the graph ---------------------------------------------------------------------------------------------------

    def _rows(self, records: Iterable[Mapping[str, Any]]) -> list[VectorRow]:
        rows = []
        for record in records:
            vector = self.vector(record["type"], record["labels"] or ())
            if vector is not None:
                rows.append(
                    VectorRow(of=str(record["id"]), type=record["type"], vector=vector)
                )
        return rows

    async def rebuild(self, write: Writer) -> int:
        """Every head document and entity that is not deleted nor merged into another, a page at a time by id"""
        from pangloss_core import backend

        current = backend.current()
        database = current.database()
        query = _heads_query(current.fragments)

        @database.read_transaction
        async def page(tx: Any, after: str) -> list[dict[str, Any]]:
            result = await tx.run(query, after=after, kinds=list(KINDS), limit=PAGE)
            return [dict(r) async for r in result]

        count = 0
        after = ""
        while True:
            records = await page(after)
            if not records:
                return count
            rows = self._rows(records)
            if rows:
                await write(rows)
            count += len(rows)
            if len(records) < PAGE:
                return count
            after = str(records[-1]["id"])

    async def refresh(self, changed: Changed, write: Writer) -> Refreshed:
        """The vectors of the heads written, read again with their labels (what they fulfil may have changed)"""
        ids = sorted({str(item.id) for item in changed.written})
        if not ids:
            return Refreshed()
        from pangloss_core import backend

        current = backend.current()
        database = current.database()
        query = _items_query(current.fragments)

        @database.read_transaction
        async def read(tx: Any, batch: Sequence[str]) -> list[dict[str, Any]]:
            result = await tx.run(query, ids=list(batch), kinds=list(KINDS))
            return [dict(r) async for r in result]

        written = 0
        for start in range(0, len(ids), PAGE):
            rows = self._rows(await read(ids[start : start + PAGE]))
            if rows:
                await write(rows)
            written += len(rows)
        return Refreshed(written=written)

    async def overlay(self, plan: Any) -> dict[str, Vector]:
        """The vector of the plan's head, from its class and the labels the plan gives it (a `Fulfils` class among
        them: the plan's labels are worked out from what the head holds, as the write's are)"""
        head = plan.head
        vector = self.vector(head.type, getattr(head, "labels", ()) or ())
        return {} if vector is None else {str(head.id): vector}


def _heads_query(fragments: Any) -> str:
    """A page of the heads, after an id (keyset: the index of `HeadNode(id)` finds where to start)"""
    # (the kind by `any(...)`, not `n:Document OR n:Entity`: Memgraph plans an OR of two indexed labels as a union of
    # label scans)
    return (
        "MATCH (n:HeadNode) WHERE n.id > $after "
        "AND any(kind IN labels(n) WHERE kind IN $kinds) "
        f"AND {fragments.not_deleted('n')} AND {fragments.not_merged('n')} "
        "RETURN n.id AS id, n.type AS type, labels(n) AS labels ORDER BY n.id LIMIT $limit"
    )


def _items_query(fragments: Any) -> str:
    """The heads of these ids"""
    return (
        "UNWIND $ids AS id MATCH (n:HeadNode {id: id}) "
        "WHERE any(kind IN labels(n) WHERE kind IN $kinds) "
        f"AND {fragments.not_deleted('n')} AND {fragments.not_merged('n')} "
        "RETURN n.id AS id, n.type AS type, labels(n) AS labels"
    )


PART = ClassPart()


def install() -> None:
    """(`pangloss_vectors._install`) register the part, and forget the maps when the models change"""
    from pangloss_vectors.parts import register_part

    register_part(PART)
    for hooks in (ModelRegistry.on_reset, ModelRegistry.after_finalise):
        if PART.forget not in hooks:
            hooks.append(PART.forget)
