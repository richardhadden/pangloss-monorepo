"""The time part (`"time"`): a vector of an item from its dates (`pangloss_dates`), each date's four bounds a soft
bump along the years (`maths.py`). implementation_docs/similarity-build-plan.md, step 9.3.

**Whose vector a date is** (decided in 9.2):

- a date held by a date (an end of a `DateRange`, the start or end of a `Period` or `Recurrence`) is part of that
  date and counts for nothing itself;
- any other date counts for **what holds it, if that is a document or an entity** (a nested statement with `when`
  has a vector of its own), and for **the head it is under** (a factoid has the dates of all its statements; a head
  that holds the date itself is counted once);
- a date held by anything else (a reified relation, an embedded object, a semantic space) counts for the head only;
- a date whose `precision` is `unknown` (an `UnknownDate` by itself) counts for nothing;
- a date that is **denied**, a date of what the walk says is denied (`pangloss_models.spaces.signature(...).veridical
  == -1` over the path of the statement it is a date of: what holds it, or, where a wrapper holds it, the statement
  the wrapper is in: a statement inside a "not", `Negative[Activity(when=d)]`, a role in such a statement, or a
  space inside a "not" holding the date in a field of its own) counts for nothing,
  neither for what holds it nor for its head (decided 2026-11-25, D4 of
  implementation_docs/spaces-and-comparison-plan.md; step 5.2). A date held by what is neither asserted nor denied
  (reported, possible, a statement that is a part of a service that did not happen) counts in full,
  whatever its lean or degree. The walk reads what each space class says (`spaces.registered_spaces()`, made once a
  rebuild, refresh or overlay), and a path that names a space class the models do not have raises
  `UnknownSpaceError`.

An item's vector is `maths.vector` of the bounds of its dates (each at length one, added). An item with no date
that counts has no vector; only an item of a class that has vectors (`pangloss_vectors.meta.included`) gets one, and
only one a reader could be shown (its head there, not deleted, not merged into another).

- `rebuild`: every date read in pages (by the index of `PGIndexableNode(id)`), kept compactly (the four bounds as
  integers, and the items each date counts for), then the vectors made and written a batch of items at a time.
- `refresh`: the dates under the heads written (by the index of `PGIndexableNode(head_node_id)`), the vectors of
  the items they count for written, and the time vector of a written head, or of a document under it, that has one
  and now has no date that counts, removed. Exact: nothing is stale.
- `overlay`: the vectors of the plan's head and of the documents in it, from the dates of the plan, by the same rule.

Nothing is kept with a generation. numpy is imported only when one of these runs (`maths`), not with the package.
"""

import json
from array import array
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pangloss_vectors.parts import (
    Changed,
    Refreshed,
    Vector,
    VectorRow,
    Writer,
    signature_of,
)

from pangloss_dates_vectors import settings

if TYPE_CHECKING:
    from pangloss_models.spaces import SpaceFacts

    from pangloss_dates_vectors.maths import Ring

NAME = "time"

# (dates read in each page of a rebuild; items made and written at a time; heads looked up in each query of a refresh)
PAGE = 10_000
WRITE_PAGE = 1000
LOOKUP = 1000

# (the label every date has, and the precision of a date that is only unknown)
DATE = "Date"
UNKNOWN = "unknown"

# (a date as a query gives it: its id, its four bounds, its precision; what holds it: id, type, whether it is a date,
# whether it is a document or an entity; its head: id, type; whether the head is one a reader could be shown; the
# date's own stored path, a list or, on a database that cannot hold one, its JSON text)
type Row = Sequence[Any]


def _row(fragments: Any, dialect: Any) -> str:
    """The row of a date `d`, held by `n` (at the end of its one reverse edge), under the head `h`. An item is a
    document or an entity as the class part says it (`class_part.KINDS`, not a citation or a cited basis,
    `$left_out`; by `any(...)`, as there, and not an OR of two labels). `kept`: the head is there, not deleted and
    not merged into another (a date is never a head: it always has a `head_node_id`). Last, the date's stored path
    (`Dialect.meta_property`: Neo4j keeps it as JSON text), for the walk"""
    return (
        "[d.id, d.earliest_fuzzy, d.earliest_strict, d.latest_strict, d.latest_fuzzy, d.precision, "
        f"n.id, n.type, n:{DATE}, "
        "any(kind IN labels(n) WHERE kind IN $kinds) AND NOT n.type IN $left_out, "
        "h.id, h.type, "
        f"(h IS NOT NULL AND {fragments.not_deleted('h')} AND {fragments.not_merged('h')}), "
        f"{dialect.meta_property('d', 'path')}]"
    )


def page_query(fragments: Any, dialect: Any) -> str:
    """A page of the dates after an id (keyset: the index of `PGIndexableNode(id)`), as one row of rows (`_row`)"""
    head = fragments.head_of("d", "h")
    return (
        f"MATCH (d:PGIndexableNode) WHERE d.id > $after AND d:{DATE} "
        "WITH d ORDER BY d.id LIMIT $limit "
        "OPTIONAL MATCH (d)-[r]->(n) WHERE r.reverse = true "
        f"{head.match} "
        f"RETURN collect({_row(fragments, dialect)}) AS rows"
    )


def under_query(fragments: Any, dialect: Any) -> str:
    """The dates under these heads (by the index of `PGIndexableNode(head_node_id)`: a date a head holds itself, an
    entity's own, has the head's id there too), as one row of rows (`_row`)"""
    head = fragments.head_of("d", "h")
    return (
        "UNWIND $ids AS id "
        f"MATCH (d:PGIndexableNode {{head_node_id: id}}) WHERE d:{DATE} "
        "OPTIONAL MATCH (d)-[r]->(n) WHERE r.reverse = true "
        f"{head.match} "
        f"RETURN collect({_row(fragments, dialect)}) AS rows"
    )


# The documents nested in these heads (by the index of `PGIndexableNode(head_node_id)`): those whose time vector a
# refresh may have to remove. (As `class_part.BELOW_QUERY` and `pangloss_names.part.BELOW_QUERY`, with the documents
# only: an entity is never nested)
BELOW_QUERY = """
UNWIND $ids AS id
MATCH (n:PGIndexableNode {head_node_id: id})
WHERE any(kind IN labels(n) WHERE kind = 'Document') AND NOT n.type IN $left_out
RETURN n.id AS id
"""


def stored_path(value: Any) -> list[Any]:
    """A date's path as a query returns it: a list, or (on a database that cannot hold one) its JSON text"""
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return list(value)


def denied(path: Sequence[Any], spaces: Mapping[str, SpaceFacts]) -> bool:
    """Whether a date is denied: whether the walk says so of the statement it is a date of
    (`signature(...).veridical == -1`). That statement is the last entry of the date's own stored path that is not a
    wrapper (a reified relation or an embedded object: the date of a role is a date of the role's statement), and
    its path is the entries before it (a node's path is its holder's and the holder). The whole path would not do:
    the walk reads a statement inside a "not" as saying nothing of what that statement holds, so the date of
    `Negative[Activity(when=d)]` would be neither. A path with no space in it is asserted, and is not walked"""
    from pangloss_models.context import EMBEDDED, REIFIED, SPACE

    held_by = list(path)
    while held_by and held_by[-1]["kind"] in (REIFIED, EMBEDDED):
        held_by.pop()
    held_by = held_by[:-1]
    if not any(entry["kind"] == SPACE for entry in held_by):
        return False
    from pangloss_models.spaces import signature

    # (no grounds given: the head reads as asserted whatever its class's ground. What a rumour says did not happen
    # is denied as what a charter says did not; the ground of a head is no part of this rule, nor of the signature)
    return signature(held_by, spaces, {}).veridical == -1


def counts_for(
    row: Row, spaces: Mapping[str, SpaceFacts]
) -> list[tuple[str, str]] | None:
    """The items a date counts for, `(id, type)`, by the rule of the module's docstring; None if it counts for
    nothing (held by a date, only unknown, a bound missing, under a head a reader could not be shown, or held by
    what is denied: `denied`). `spaces`: what each space class says (`spaces.registered_spaces()`). The classes that have no
    vectors are not left out here"""
    (_, *bounds, precision, holder, holder_type, held_by_date, holder_is_item) = row[
        :10
    ]
    head, head_type, kept, path = row[10:14]
    if held_by_date or not kept or head is None:
        return None
    if str(precision) == UNKNOWN or any(bound is None for bound in bounds):
        return None
    if denied(stored_path(path), spaces):
        return None
    items = [(str(head), str(head_type))]
    if holder_is_item and holder is not None and str(holder) != str(head):
        items.append((str(holder), str(holder_type)))
    return items


class Dates:
    """The dates read and the items they count for, kept compactly: the bounds of each date as four integers, the
    items by number, and a pair (date, item) for each item a date counts for (a million dates are some 32 MB, not a
    matrix of a million by the dimension)"""

    def __init__(self, spaces: Mapping[str, SpaceFacts] | None = None) -> None:
        if spaces is None:
            from pangloss_models.spaces import registered_spaces

            spaces = registered_spaces()
        # (what each space class says, for the walk over each date's path: `counts_for`)
        self.spaces = spaces
        self.bounds = array("q")
        self.ids: list[str] = []
        self.types: list[str] = []
        self.number: dict[str, int] = {}
        self.of_date = array("q")
        self.of_item = array("q")
        self._dates = 0
        self._included: dict[str, bool] = {}

    def included(self, type_name: str) -> bool:
        """`meta.included`, asked once for each class"""
        found = self._included.get(type_name)
        if found is None:
            from pangloss_vectors import meta

            found = self._included[type_name] = meta.included(type_name)
        return found

    def add(self, row: Row) -> None:
        items = counts_for(row, self.spaces)
        if not items:
            return
        items = [(id, type_name) for id, type_name in items if self.included(type_name)]
        if not items:
            return
        date = self._dates
        self._dates += 1
        self.bounds.extend(int(bound) for bound in row[1:5])
        for id, type_name in items:
            number = self.number.get(id)
            if number is None:
                number = self.number[id] = len(self.ids)
                self.ids.append(id)
                self.types.append(type_name)
            self.of_date.append(date)
            self.of_item.append(number)

    def __len__(self) -> int:
        """How many items have a date that counts"""
        return len(self.ids)

    def vectors(self, ring: Ring, batch: int = WRITE_PAGE) -> Iterable[list[VectorRow]]:
        """The vectors of the items, a batch of items at a time (`maths.of_items`)"""
        if not self.ids:
            return
        import numpy as np

        from pangloss_dates_vectors import maths

        bounds = np.frombuffer(self.bounds, dtype=np.int64).reshape(-1, 4)
        of_item = np.frombuffer(self.of_item, dtype=np.int64)
        of_date = np.frombuffer(self.of_date, dtype=np.int64)
        # (the pairs in the order of their items, so that a batch of items is a slice of them)
        order = np.argsort(of_item, kind="stable")
        of_item, of_date = of_item[order], of_date[order]
        for start in range(0, len(self.ids), batch):
            end = min(start + batch, len(self.ids))
            first, last = np.searchsorted(of_item, [start, end])
            made = maths.of_items(
                bounds[of_date[first:last]],
                of_item[first:last] - start,
                end - start,
                ring,
            )
            yield [
                VectorRow(
                    of=self.ids[number],
                    type=self.types[number],
                    vector=[float(x) for x in made[number - start]],
                )
                for number in range(start, end)
            ]


class TimePart:
    """The part: an object, registered when `pangloss_dates_vectors` is imported"""

    name = NAME
    local = True
    requires: frozenset[str] = frozenset()
    # (in no profile until a project's `VECTORS_PROFILES` weighs it: installing the package changes no result, as
    # the name part)
    weight = 0.0

    def __repr__(self) -> str:
        return "TimePart()"

    # -- what the models and the settings say ------------------------------------------------------------------------

    def dimension(self) -> int:
        return settings.dimension()

    def ring(self) -> Ring:
        return settings.ring()

    def signature(self) -> str:
        """The dimension and the width: all a date's vector depends on; and, where the models have semantic spaces,
        what the walk reads of each (`spaces_said`), which decides which dates are denied. (A class newly left out of
        the vectors, or let in, makes a rebuild due by the signature the store compares, `store.part_signature`,
        which adds the classes that have none; a new class that is no space changes no vector there is)"""
        said = spaces_said()
        if not said:
            # (as it was before dates were walked: a project with no space has nothing denied, and no rebuild due)
            return signature_of(self.dimension(), settings.width())
        return signature_of(self.dimension(), settings.width(), said)

    # -- the graph ---------------------------------------------------------------------------------------------------

    def _spaces(self) -> dict[str, SpaceFacts]:
        from pangloss_models.spaces import registered_spaces

        return registered_spaces()

    def _parameters(self) -> dict[str, Any]:
        from pangloss_vectors.class_part import KINDS, left_out

        return {"kinds": list(KINDS), "left_out": left_out()}

    async def rebuild(self, write: Writer) -> int:
        """Every date, read in pages and kept compactly; the vectors of the items they count for, written a batch of
        items at a time"""
        from pangloss_core import backend

        current = backend.current()
        database = current.database()
        query = page_query(current.fragments, current.dialect)
        parameters = self._parameters()

        @database.read_transaction
        async def page(tx: Any, after: str) -> list[Row]:
            result = await tx.run(query, after=after, limit=PAGE, **parameters)
            record = await result.single()
            return list(record["rows"] or []) if record is not None else []

        dates = Dates(self._spaces())
        after = ""
        while True:
            rows = await page(after)
            for row in rows:
                dates.add(row)
            # (a date is a row; the ids, should a date have two rows)
            seen = {str(row[0]) for row in rows}
            if len(seen) < PAGE:
                break
            # (the largest id of the page: `collect` is not promised to keep the order it is given)
            after = max(seen)
        count = 0
        for rows in dates.vectors(self.ring()):
            if rows:
                await write(rows)
                count += len(rows)
        return count

    async def refresh(self, changed: Changed, write: Writer) -> Refreshed:
        """The vectors of the items the dates under the heads written count for; and the time vector of a written
        head, or of a document under it, that has one and now has no date that counts, removed (a date taken away, a
        class changed in place to one without vectors). Nothing if the part was never built. Exact: nothing is stale.
        (The vectors of `Changed.removed` are the caller's to delete)"""
        heads = sorted({str(item.id) for item in changed.written})
        if not heads:
            return Refreshed()
        from pangloss_core import backend
        from pangloss_vectors import store

        if NAME not in (await store.states()).parts:
            return Refreshed()
        current = backend.current()
        database = current.database()
        query = under_query(current.fragments, current.dialect)
        parameters = self._parameters()
        spaces = self._spaces()

        @database.read_transaction
        async def under(tx: Any, batch: Sequence[str]) -> list[Row]:
            result = await tx.run(query, ids=list(batch), **parameters)
            record = await result.single()
            return list(record["rows"] or []) if record is not None else []

        @database.read_transaction
        async def below(tx: Any, batch: Sequence[str]) -> list[str]:
            result = await tx.run(
                BELOW_QUERY, ids=list(batch), left_out=parameters["left_out"]
            )
            return [str(r["id"]) async for r in result]

        ring = self.ring()
        written = 0
        for start in range(0, len(heads), LOOKUP):
            batch = heads[start : start + LOOKUP]
            dates = Dates(spaces)
            for row in await under(batch):
                dates.add(row)
            made: set[str] = set()
            for rows in dates.vectors(ring):
                if rows:
                    await write(rows)
                    written += len(rows)
                    made |= {row.of for row in rows}
            # (what may have had a vector and has none now: the heads, and every document under them)
            looked = set(batch) | set(await below(batch))
            had = await store.read_part(NAME, sorted(looked - made))
            if had:
                await store.remove_vectors(NAME, sorted(had))
        return Refreshed(written=written, stale=0)

    async def overlay(self, plan: Any) -> dict[str, Vector]:
        """The vectors of the plan's head and of the documents in it, from the dates in the plan, by the same rule as
        the stored ones (`overlay_rows` gives the rows a query would): nothing is written"""
        dates = Dates(self._spaces())
        for row in overlay_rows(plan):
            dates.add(row)
        return {
            row.of: row.vector for rows in dates.vectors(self.ring()) for row in rows
        }


def overlay_rows(plan: Any) -> list[Row]:
    """The dates of a write plan (`pangloss_cypher.write_plan.WritePlan`), each as the row a query would give it once
    written (`_row`): the bounds and the precision are on the planned node of the date (its properties, as written:
    the `DBField`s the date's validator worked out); what holds it is the planned node whose relation it is the target
    of; its head is the plan's head; its path is the one the plan writes in its `meta`. An entity written in the document (`InlineEntity`) is a head of its own and is
    not walked, nor is a reference to an existing node"""
    from pangloss_cypher.write_plan import PlannedNode
    from pangloss_vectors.class_part import KINDS, left_out

    skipped = set(left_out())
    head = plan.head
    found: list[Row] = []

    def is_item(node: PlannedNode) -> bool:
        return any(kind in node.labels for kind in KINDS) and node.type not in skipped

    def walk(node: PlannedNode) -> None:
        for relation in node.relations:
            target = relation.target
            if not isinstance(target, PlannedNode):
                continue
            if DATE in target.labels:
                properties = target.properties
                found.append(
                    [
                        target.id,
                        properties.get("earliest_fuzzy"),
                        properties.get("earliest_strict"),
                        properties.get("latest_strict"),
                        properties.get("latest_fuzzy"),
                        properties.get("precision"),
                        node.id,
                        node.type,
                        DATE in node.labels,
                        is_item(node),
                        head.id,
                        head.type,
                        True,
                        (properties.get("meta") or {}).get("path"),
                    ]
                )
            walk(target)

    walk(head)
    return found


def spaces_said() -> dict[str, dict[str, Any]]:
    """What the walk reads of each space class among the models (its `veridical`, `logical` and `abstract`), by
    class name: what decides which paths are denied, for the part's signature. Empty where the models have no space"""
    from pangloss_models.spaces import registered_spaces

    return {
        name: {
            "veridical": facts["veridical"],
            "logical": facts["logical"],
            "abstract": bool(facts.get("abstract")),
        }
        for name, facts in sorted(registered_spaces().items())
    }


PART = TimePart()


def install() -> None:
    """(`pangloss_dates_vectors._install`) register the part"""
    from pangloss_vectors.parts import register_part

    register_part(PART)
