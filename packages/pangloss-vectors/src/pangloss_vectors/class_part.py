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
follow `VECTORS_GRAPH_SEES`: every document and entity has a vector, a nested document (a statement in a factoid) as
well as a head, unless it is deleted (a nested one: its head is), merged into another, a citation or a cited basis
(`left_out`); a search hides what a reader may not see.
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

# (documents and entities read in each page of a rebuild, one row of lists for each page; and the ids looked up in
# each query of a refresh)
PAGE = 10_000
LOOKUP = 1000

# The kinds of node the class part gives a vector (`ReifiedRelationDocument` and the wrappers have neither label)
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

    def _rows(self, records: Iterable[Sequence[Any]]) -> list[VectorRow]:
        """The rows of `[id, type, labels]`"""
        rows = []
        for id, type_name, labels in records:
            vector = self.vector(type_name, labels or ())
            if vector is not None:
                rows.append(VectorRow(of=str(id), type=type_name, vector=vector))
        return rows

    async def rebuild(self, write: Writer) -> int:
        """Every document and entity, head or nested, that a reader could be shown (`_page_query`), a page at a time
        by id"""
        from pangloss_core import backend

        current = backend.current()
        database = current.database()
        query = _page_query(current.fragments)

        @database.read_transaction
        async def page(tx: Any, after: str) -> list[list[Any]]:
            result = await tx.run(
                query, after=after, kinds=list(KINDS), left_out=left_out(), limit=PAGE
            )
            record = await result.single()
            return list(record["rows"] or []) if record is not None else []

        count = 0
        after = ""
        while True:
            records = await page(after)
            rows = self._rows(
                (id, type_name, labels)
                for id, type_name, labels, kept in records
                if kept
            )
            if rows:
                await write(rows)
            count += len(rows)
            if len(records) < PAGE:
                return count
            # (the largest id of the page: `collect` is not promised to keep the order it is given)
            after = max(str(record[0]) for record in records)

    async def refresh(self, changed: Changed, write: Writer) -> Refreshed:
        """The vectors of the heads written and of the documents nested in them, read again with their labels (what
        they fulfil may have changed). (The vectors of a removed head, and of the nested documents an update replaced,
        which are no longer in the database, are the caller's to delete)"""
        ids = sorted({str(item.id) for item in changed.written})
        if not ids:
            return Refreshed()
        from pangloss_core import backend

        current = backend.current()
        database = current.database()
        query = _items_query(current.fragments)

        @database.read_transaction
        async def tree(tx: Any, batch: Sequence[str]) -> list[str]:
            result = await tx.run(
                BELOW_QUERY, ids=list(batch), kinds=list(KINDS), left_out=left_out()
            )
            return [str(r["id"]) async for r in result]

        @database.read_transaction
        async def read(tx: Any, batch: Sequence[str]) -> list[list[Any]]:
            result = await tx.run(
                query, ids=list(batch), kinds=list(KINDS), left_out=left_out()
            )
            return [[r["id"], r["type"], r["labels"]] async for r in result]

        below: list[str] = []
        for start in range(0, len(ids), LOOKUP):
            below += await tree(ids[start : start + LOOKUP])
        everything = sorted(set(ids) | set(below))
        written = 0
        for start in range(0, len(everything), LOOKUP):
            rows = self._rows(await read(everything[start : start + LOOKUP]))
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

    async def unknown(self, plan: Any, unknowns: Sequence[Any]) -> dict[str, Vector]:
        """The vector of each unknown's class (`parts.Unknown`), with the labels a new entity of it has (those of its
        class: it holds nothing that fulfils another); the plan is not read. A class with classes below it is its
        own; an abstract one, of which no entity is, has its own vector all the same (its class at 1 and those above
        it, nearer every class below it than they are to each other). A name that is no class of documents or
        entities has nothing"""
        from pangloss_models.model_bases.labels import labels_for_model

        found: dict[str, Vector] = {}
        for unknown in unknowns:
            model = ModelRegistry._model_dict.get(unknown.type)
            if model is None or not _is_class(model):
                continue
            unmanaged = getattr(model, "__labels_unmanaged__", ())
            labels = [
                label
                for label in labels_for_model(model, model.__metatype__)
                if label not in unmanaged
            ]
            vector = self.vector(unknown.type, labels)
            if vector is not None:
                found[str(unknown.id)] = vector
        return found


def left_out() -> list[str]:
    """The classes of documents that have no vector: the citations (`PGCitation`, `PGUnprotectedCitation`) and a
    cited basis (`PGCitedBasis`), which are part of the document that holds them and nothing a reader is shown as an
    item (the graph part takes a citation as the end of a chain and a cited basis as a wrapper: neither is a stop)"""
    from pangloss_models.citations import BASIS, CITATION_TYPES

    return sorted({*CITATION_TYPES, BASIS})


# (the kind by `any(...)`, not `n:Document OR n:Entity`: Memgraph plans an OR of two indexed labels as a union of label
# scans)
_ITEM = "any(kind IN labels(n) WHERE kind IN $kinds) AND NOT n.type IN $left_out"


def _kept(fragments: Any) -> str:
    """An expression: the node `n`, whose head `h` was looked for, is one a reader could be shown: not merged into
    another, and its head (`n` itself, if it is one) there and not deleted. (Whether it is published is the search's:
    it depends on the reader)"""
    head = fragments.head_of("n", "h")
    return (
        f"((n.head_node_id IS NULL OR h IS NOT NULL) AND {fragments.not_deleted(str(head))} "
        f"AND {fragments.not_merged('n')})"
    )


def _page_query(fragments: Any) -> str:
    """A page of the documents and entities after an id (keyset: the index of `PGIndexableNode(id)` finds where to
    start), head or nested, as one row of `[id, type, labels, kept]`: `kept` false for one a reader could not be shown
    (`_kept`), which the page counts all the same (so that a page short of `$limit` is the last)"""
    head = fragments.head_of("n", "h")
    return (
        f"MATCH (n:PGIndexableNode) WHERE n.id > $after AND {_ITEM} "
        "WITH n ORDER BY n.id LIMIT $limit "
        f"{head.match} "
        f"RETURN collect([n.id, n.type, labels(n), {_kept(fragments)}]) AS rows"
    )


def _items_query(fragments: Any) -> str:
    """The documents and entities of these ids that a reader could be shown"""
    head = fragments.head_of("n", "h")
    return (
        "UNWIND $ids AS id MATCH (n:PGIndexableNode {id: id}) "
        f"WHERE {_ITEM} "
        f"{head.match} "
        f"WITH n, h WHERE {_kept(fragments)} "
        "RETURN n.id AS id, n.type AS type, labels(n) AS labels"
    )


# The documents nested in these heads (by the index of `PGIndexableNode(head_node_id)`)
BELOW_QUERY = f"""
UNWIND $ids AS id
MATCH (n:PGIndexableNode {{head_node_id: id}})
WHERE {_ITEM}
RETURN n.id AS id
"""


PART = ClassPart()


def install() -> None:
    """(`pangloss_vectors._install`) register the part, and forget the maps when the models change"""
    from pangloss_vectors.parts import register_part

    register_part(PART)
    for hooks in (ModelRegistry.on_reset, ModelRegistry.after_finalise):
        if PART.forget not in hooks:
            hooks.append(PART.forget)
