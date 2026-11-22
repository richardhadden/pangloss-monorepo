"""The name part (`"name"`): a vector of an item from its names, the trigrams of their words hashed and weighted by
how rare each word is (`maths.py`). implementation_docs/similarity-build-plan.md, step 8.3.

- `rebuild`: every name read in pages (the classes that have names, `meta.named()`, and the values of their name
  fields), the table of rarity made over the items a reader could be shown (`maths.Rarity.of`), then a vector for
  each and written in pages. The table, as JSON, is what `kept()` gives: `pangloss-vectors` stores it with the
  generation (`store.keep`).
- `refresh`: the heads written, and the documents nested in them if a class of documents has names, read again and
  weighed by the **kept** table of the generation in use (`store.kept`), never a new one: a refresh is exact against
  the last rebuild's table. A written item that now has no name vector (its names emptied, or no longer one a reader
  could be shown) loses its vector (`store.remove_vectors`).
- `overlay`: the vector of a plan's head by the kept table, if its class has names.

The kept table is parsed once for each generation in use and remembered in the process (it can be megabytes).
numpy is imported only when one of these runs (`maths`), not with the package.
"""

import json
import logging
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from pangloss_models import ModelRegistry
from pangloss_vectors.parts import (
    Changed,
    Refreshed,
    Vector,
    VectorRow,
    Writer,
    signature_of,
)

from pangloss_names import meta, settings

logger = logging.getLogger("pangloss.names")

if TYPE_CHECKING:
    from pangloss_names.maths import Rarity

NAME = "name"

# (items read in each page of a rebuild; rows given to the writer at a time; ids looked up in each query of a refresh)
PAGE = 10_000
WRITE_PAGE = 1000
LOOKUP = 1000

# (an item kept in memory by a rebuild: its id, its class and its names)
type Named = tuple[str, str, list[str]]


def _kept(fragments: Any) -> str:
    """An expression: the node `n`, whose head `h` was looked for, is one a reader could be shown: not merged into
    another, and its head (`n` itself, if it is one) there and not deleted (as the class part's; whether it is
    published is the search's)"""
    head = fragments.head_of("n", "h")
    return (
        f"((n.head_node_id IS NULL OR h IS NOT NULL) AND {fragments.not_deleted(str(head))} "
        f"AND {fragments.not_merged('n')})"
    )


def page_query(fragments: Any) -> str:
    """A page of the items of the classes that have names after an id (keyset: the index of `PGIndexableNode(id)`),
    as one row of `[id, type, [the value of each field of $fields], kept]`: `kept` false for one a reader could not
    be shown, which the page counts all the same (so that a page short of `$limit` is the last)"""
    head = fragments.head_of("n", "h")
    return (
        "MATCH (n:PGIndexableNode) WHERE n.id > $after AND n.type IN $types "
        "WITH n ORDER BY n.id LIMIT $limit "
        f"{head.match} "
        f"RETURN collect([n.id, n.type, [f IN $fields | n[f]], {_kept(fragments)}]) AS rows"
    )


def items_query(fragments: Any) -> str:
    """The items of these ids, of the classes that have names, that a reader could be shown, with their names"""
    head = fragments.head_of("n", "h")
    return (
        "UNWIND $ids AS id MATCH (n:PGIndexableNode {id: id}) "
        "WHERE n.type IN $types "
        f"{head.match} "
        f"WITH n, h WHERE {_kept(fragments)} "
        "RETURN n.id AS id, n.type AS type, [f IN $fields | n[f]] AS names"
    )


# The documents nested in these heads that are of a class with names (by the index of `PGIndexableNode(head_node_id)`)
BELOW_QUERY = """
UNWIND $ids AS id
MATCH (n:PGIndexableNode {head_node_id: id})
WHERE n.type IN $types
RETURN n.id AS id
"""


def names_of(
    type_name: str, values: Sequence[Any], fields: Sequence[str], named: Any
) -> list[str]:
    """The names of an item from the values of `fields` read from its node: only those of the class's own name
    fields (a field another class names and this one has is not a name of this one), nulls left out, a list's items
    each a name"""
    own = set(named.get(type_name, ()))
    found: list[str] = []
    for field, value in zip(fields, values, strict=True):
        if field not in own or value is None:
            continue
        if isinstance(value, (list, tuple)):
            found += [str(v) for v in value if v is not None]
        else:
            found.append(str(value))
    return found


def _plain(vector: Any) -> list[float]:
    return [float(x) for x in vector]


def _same(had: Sequence[float] | None, made: Sequence[float]) -> bool:
    """Whether the vector stored is the one just made (to what a float loses in the database and back)"""
    return (
        had is not None
        and len(had) == len(made)
        and all(abs(a - b) <= 1e-9 for a, b in zip(had, made, strict=True))
    )


def table_text(rarity: Rarity) -> str:
    """The table of rarity as it is kept with a generation: `{"having": {...}, "names": n}`"""
    return json.dumps(
        {"names": rarity.names, "having": dict(sorted(rarity.having.items()))},
        sort_keys=True,
        separators=(",", ":"),
    )


def table_of(text: str) -> Rarity:
    from pangloss_names.maths import Rarity

    found = json.loads(text)
    return Rarity(int(found["names"]), dict(found["having"]))


class NamePart:
    """The part: an object, registered when `pangloss_names` is imported"""

    name = NAME
    local = True
    requires: frozenset[str] = frozenset()
    # (in no profile until a project's `VECTORS_PROFILES` weighs it: installing the package changes no result;
    # decision 4 of the build plan)
    weight = 0.0

    def __init__(self) -> None:
        self._last: str | None = None
        # (the kept table of the generation in use, parsed: by the generation and when it was built)
        self._remembered: tuple[tuple[int, Any], Rarity] | None = None

    def __repr__(self) -> str:
        return "NamePart()"

    def forget(self) -> None:
        """(`ModelRegistry.on_reset`) forget the kept table read"""
        self._remembered = None

    # -- what the models and the settings say ------------------------------------------------------------------------

    def dimension(self) -> int:
        return settings.dimension()

    def table(self) -> dict[str, str]:
        """The table of variants, folded (`maths.variants_table` of the forms and variants of `NAMES_VARIANTS`,
        `settings.variants()`): each variant to its canonical form"""
        from pangloss_names.maths import variants_table

        return variants_table(settings.variants())

    def signature(self) -> str:
        """The classes with names and their fields, the dimension, and the table of variants (its content,
        `settings.variants_hash()`; the table of rarity is what a rebuild makes, not what it depends on)"""
        return signature_of(meta.named(), self.dimension(), settings.variants_hash())

    def vector(
        self,
        names: Iterable[str],
        rarity: Rarity,
        table: dict[str, str] | None = None,
    ) -> list[float] | None:
        """The vector of an item with these names, by this table of rarity; None if they give none"""
        from pangloss_names import maths

        made = maths.vector(
            # (a plain string is one name, not its letters)
            [names] if isinstance(names, str) else list(names),
            rarity,
            self.dimension(),
            self.table() if table is None else table,
        )
        return None if made is None else _plain(made)

    # -- the kept table ----------------------------------------------------------------------------------------------

    def kept(self) -> str | None:
        """(asked by `pangloss_vectors.rebuild` once `rebuild` has returned) the table of rarity the rebuild made, as
        JSON, to be kept with its generation"""
        return self._last

    async def rarity(self) -> Rarity | None:
        """The table of rarity of the generation in use (the last rebuild's), or None if the part was never built.
        Read and parsed once for each generation. Raises `store.RebuildDue` if the part is built and its table is not
        there (the worker says so and goes on)"""
        from pangloss_core import backend
        from pangloss_vectors import store

        remembered = self._remembered
        database = backend.current().database()

        @database.read_transaction
        async def read(tx: Any) -> tuple[tuple[int, Any], str | None] | None:
            found = await store._states(tx)
            state = found.parts.get(NAME)
            if state is None:
                return None
            key = (state.generation, state.built_at)
            if remembered is not None and remembered[0] == key:
                return key, None
            return key, await store.kept_in(tx, NAME, found)

        got = await read()
        if got is None:
            return None
        key, text = got
        if remembered is not None and remembered[0] == key:
            return remembered[1]
        if text is None:
            # (never built is None above: this is built, and the table that was kept with it is not there)
            raise store.RebuildDue(
                "The name part's vectors in use have no table of rarity kept with them, so a name cannot be weighed "
                "as they were: rebuild the part (`pangloss vectors rebuild --part name`)"
            )
        rarity = table_of(text)
        self._remembered = (key, rarity)
        return rarity

    # -- the graph ---------------------------------------------------------------------------------------------------

    async def rebuild(self, write: Writer) -> int:
        """Every item of a class with names that a reader could be shown, read in pages; the table of rarity over
        them; their vectors, written in pages"""
        from pangloss_core import backend

        from pangloss_names import maths

        named = meta.named()
        types = sorted(named)
        fields = sorted({f for own in named.values() for f in own})
        table = self.table()
        current = backend.current()
        database = current.database()
        query = page_query(current.fragments)

        @database.read_transaction
        async def page(tx: Any, after: str) -> list[list[Any]]:
            result = await tx.run(
                query, after=after, types=types, fields=fields, limit=PAGE
            )
            record = await result.single()
            return list(record["rows"] or []) if record is not None else []

        items: list[Named] = []
        after = ""
        while types:
            records = await page(after)
            items += [
                (str(id), type_name, names_of(type_name, values, fields, named))
                for id, type_name, values, kept in records
                if kept
            ]
            if len(records) < PAGE:
                break
            # (the largest id of the page: `collect` is not promised to keep the order it is given)
            after = max(str(record[0]) for record in records)
        rarity = maths.Rarity.of(maths.words(names, table) for _, _, names in items)
        self._last = table_text(rarity)
        count = 0
        rows: list[VectorRow] = []
        for of, type_name, names in items:
            vector = self.vector(names, rarity, table)
            if vector is None:
                continue
            rows.append(VectorRow(of=of, type=type_name, vector=vector))
            if len(rows) == WRITE_PAGE:
                await write(rows)
                count += len(rows)
                rows = []
        if rows:
            await write(rows)
            count += len(rows)
        return count

    async def refresh(self, changed: Changed, write: Writer) -> Refreshed:
        """The vectors of the heads written, and of the documents nested in them (if a class of documents has names),
        by the kept table of the generation in use; nothing if the part was never built. A written item that now has
        no name vector loses its vector, a head whose class was changed to one without names among them. (The vectors of `Changed.removed` are the caller's to delete.)

        Every vector a refresh writes **that is new or not what was stored** is **stale**: a name weighed by a table
        of rarity that does not count it (the last rebuild's), so it is left out of date in the sense of
        `VECTORS_REBUILD_AFTER`, which counts them towards a rebuild that makes the table again. A head saved with
        its names as they were is written the same vector and counts for nothing"""
        named = meta.named()
        # (every head written, not only those of a class with names: one whose class was changed in place to a class
        # without names has a name vector to lose)
        heads = sorted({str(item.id) for item in changed.written})
        # (the classes of documents with names: their items may be nested in any head written)
        nested = sorted(
            name
            for name in named
            if getattr(ModelRegistry._model_dict.get(name), "__metatype__", None)
            == "Document"
        )
        if not heads:
            return Refreshed()
        rarity = await self.rarity()
        if rarity is None:
            return Refreshed()
        from pangloss_core import backend
        from pangloss_vectors import store

        types = sorted(named)
        fields = sorted({f for own in named.values() for f in own})
        current = backend.current()
        database = current.database()
        query = items_query(current.fragments)

        @database.read_transaction
        async def below(tx: Any, batch: Sequence[str]) -> list[str]:
            result = await tx.run(BELOW_QUERY, ids=list(batch), types=nested)
            return [str(r["id"]) async for r in result]

        @database.read_transaction
        async def read(tx: Any, batch: Sequence[str]) -> list[list[Any]]:
            result = await tx.run(query, ids=list(batch), types=types, fields=fields)
            return [[r["id"], r["type"], r["names"]] async for r in result]

        of_named = {str(item.id) for item in changed.written if item.type in named}
        found = set(of_named)
        if nested:
            # (the documents of every head written: one of a class without names may hold some that have)
            for start in range(0, len(heads), LOOKUP):
                found |= set(await below(heads[start : start + LOOKUP]))
        ids = sorted(found)
        table = self.table()
        written = 0
        stale = 0
        none: list[str] = []
        for start in range(0, len(ids), LOOKUP):
            batch = ids[start : start + LOOKUP]
            had = await store.read_part(NAME, batch)
            rows: list[VectorRow] = []
            for id, type_name, values in await read(batch):
                vector = self.vector(
                    names_of(type_name, values, fields, named), rarity, table
                )
                if vector is not None:
                    rows.append(VectorRow(of=str(id), type=type_name, vector=vector))
            if rows:
                await write(rows)
            written += len(rows)
            stale += sum(1 for row in rows if not _same(had.get(row.of), row.vector))
            none += sorted(set(batch) - {row.of for row in rows})
        # (a head written whose class has no names: only if it has a name vector, of the class it was)
        none += sorted(await store.read_part(NAME, sorted(set(heads) - of_named)))
        if none:
            await store.remove_vectors(NAME, none)
        return Refreshed(written=written, stale=stale)

    async def overlay(self, plan: Any) -> dict[str, Vector]:
        """The vector of the plan's head by the kept table, if its class has names; nothing if there is no table yet"""
        head = plan.head
        own = meta.named().get(head.type)
        if own is None:
            return {}
        rarity = await self.rarity()
        if rarity is None:
            return {}
        values = [head.properties.get(field) for field in own]
        vector = self.vector(names_of(head.type, values, own, {head.type: own}), rarity)
        return {} if vector is None else {str(head.id): vector}

    async def unknown(self, plan: Any, unknowns: Sequence[Any]) -> dict[str, Vector]:
        """The vector of each unknown's label (`parts.Unknown`) by the kept table and the table of variants, as a
        stored entity of its class whose `label` is that text has it, where `label` is a name of that class
        (`label_is_a_name`); the plan is not read. Nothing if there is no table yet, or for a label that gives no
        vector"""
        named = meta.named()
        asked = [u for u in unknowns if u.label and label_is_a_name(u.type, named)]
        if not asked:
            return {}
        from pangloss_vectors import store

        try:
            rarity = await self.rarity()
        except store.RebuildDue as error:
            # (built, and its table is not there: the other parts still say theirs, as the worker goes on)
            logger.warning("The name part says nothing of the unknowns: %s", error)
            return {}
        if rarity is None:
            return {}
        table = self.table()
        found: dict[str, Vector] = {}
        for unknown in asked:
            vector = self.vector([unknown.label], rarity, table)
            if vector is not None:
                found[str(unknown.id)] = vector
        return found


def label_is_a_name(type_name: str, named: dict[str, list[str]]) -> bool:
    """Whether the `label` of an entity of this class is a name of it: among the name fields of the class (`named`,
    `meta.named()`, which has the concrete classes with names) if it is concrete; of a class that is not (abstract),
    among those of any concrete class below it"""
    model = ModelRegistry._model_dict.get(type_name)
    if not isinstance(model, type):
        return False
    if not getattr(getattr(model, "_meta", None), "abstract", False):
        return meta.LABEL in named.get(type_name, ())
    return any(
        meta.LABEL in fields
        and isinstance(below := ModelRegistry._model_dict.get(name), type)
        and issubclass(below, model)
        for name, fields in named.items()
    )


PART = NamePart()


def install() -> None:
    """(`pangloss_names._install`) register the part, and forget the kept table read when the models are reset"""
    from pangloss_vectors.parts import register_part

    register_part(PART)
    if PART.forget not in ModelRegistry.on_reset:
        ModelRegistry.on_reset.append(PART.forget)
