"""Neo4j's answers where the Cypher backends differ (`pangloss_cypher.dialect.Dialect`)"""

import functools
import re
from typing import Any
from uuid import UUID

import neo4j
from neo4j.exceptions import ConstraintError

from pangloss_cypher.search_query import wrapper
from pangloss_cypher import Transaction
from pangloss_neo4j.databases.neo4j.properties import (
    ALWAYS_JSON,
    decode,
    flatten,
    json_name,
    meta_map,
    prop,
)
from pangloss_neo4j.databases.neo4j.queries import QUERIES
from pangloss_neo4j.databases.neo4j.schema import search_patterns
from pangloss_neo4j.databases.neo4j.search import Neo4jCompiler, through
from pangloss_neo4j.databases.neo4j.traversal import below, hops, up


class DecodedResult:
    """The result of a query, with the maps that Neo4j keeps flat nested again (`properties.decode`), so that what reads a
    result sees what a Neo4j backend gives. It has the methods of a result that this package uses; anything else is the
    result's."""

    def __init__(self, result: neo4j.AsyncResult) -> None:
        self._result = result

    def _record(self, record: neo4j.Record | None) -> neo4j.Record | None:
        return None if record is None else self._decoded(record)

    def _decoded(self, record: neo4j.Record) -> neo4j.Record:
        return neo4j.Record(
            zip(record.keys(), (decode(v) for v in record.values()), strict=True)
        )

    async def single(self, strict: bool = False) -> neo4j.Record | None:
        return self._record(await self._result.single(strict=strict))  # type: ignore[arg-type]

    async def peek(self) -> neo4j.Record | None:
        return self._record(await self._result.peek())

    async def fetch(self, n: int) -> list[neo4j.Record]:
        return [self._decoded(r) for r in await self._result.fetch(n)]

    async def data(self, *keys: Any) -> list[dict[str, Any]]:
        return [decode(row) for row in await self._result.data(*keys)]

    async def value(self, key: Any = 0, default: Any = None) -> list[Any]:
        return [decode(v) for v in await self._result.value(key, default)]

    async def values(self, *keys: Any) -> list[list[Any]]:
        return [decode(v) for v in await self._result.values(*keys)]

    def __aiter__(self):
        return self._records()

    async def _records(self):
        async for record in self._result:
            yield self._decoded(record)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._result, name)


class DecodingTransaction:
    """A transaction whose results are `DecodedResult`s"""

    def __init__(self, tx: Any) -> None:
        self._tx = tx

    async def run(
        self, query: Any, parameters: Any = None, **kwargs: Any
    ) -> DecodedResult:
        return DecodedResult(await self._tx.run(query, parameters, **kwargs))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._tx, name)


async def lock_node(tx: Transaction, id: UUID) -> None:
    """Take the write lock of a node, held until the transaction ends: another transaction that writes to it waits (writing
    a property takes the lock, and it is set and removed again so that nothing is left)"""
    result = await tx.run(
        "MATCH (n:PGIndexableNode {id: $id}) SET n.pg_lock = true REMOVE n.pg_lock RETURN count(n) AS locked",
        id=str(id),
    )
    await result.consume()


class Neo4jDialect:
    name = "neo4j"

    def driver_options(self) -> dict[str, Any]:
        # (Neo4j reports each use of a deprecated feature with every query that has it)
        return {
            "notifications_disabled_classifications": [
                neo4j.NotificationDisabledClassification.DEPRECATION
            ]
        }

    def wrap_transaction(self, tx: Any) -> Any:
        return DecodingTransaction(tx)

    def is_timeout(self, error: Exception) -> bool:
        """(Neo4j reports it as a client error with a `TransactionTimedOut` code)"""
        return "timedout" in (getattr(error, "code", "") or "").lower() or (
            "timeout" in str(error).lower() or "timed out" in str(error).lower()
        )

    def is_unique_violation(self, error: Exception) -> bool:
        # (Memgraph says "unique constraint"; Neo4j raises a `ConstraintError`, "already exists with label")
        return isinstance(error, ConstraintError) or (
            isinstance(error, neo4j.exceptions.ClientError)
            and "unique constraint" in str(error).lower()
        )

    # (Neo4j reads what is committed: a check of the write, made after another write committed, sees what that made,
    # where Memgraph's would have seen the database as it was when this one began, and met the other write only when
    # this one committed. So a conflict found by a check may be a lost race too: run again, and it is found as what it
    # is.)
    retry_on_check_conflict = True

    async def before_replace(self, tx: Transaction, id: Any) -> None:
        # (Neo4j reads what is committed, and does not make the second of two writers to the same node run again, as
        # Memgraph does: so an update takes the node's lock first, and reads the version after it has it)
        await lock_node(tx, id)

    def encode_properties(
        self, properties: dict[str, Any], *, node: bool = True
    ) -> dict[str, Any]:
        # (Neo4j cannot store a map as a property: `meta` and annotated values are flattened. Its full-text index folds
        # the label itself)
        return flatten(properties)

    def has_meta(self, node: str) -> str:
        return f"{node}.`meta.created_by` IS NOT NULL"

    def meta_of(self, node: str) -> str:
        return meta_map(node)

    def entity_labels(self) -> str:
        return ":PGIndexableNode:Entity"

    def tree_below(self, start: str, end: str) -> str:
        return f"{start}{self.down_tree('tree')}{end}"

    # --- reading ----------------------------------------------------------------------------------------------------

    def text_search(self, index: str, query: str, options: str | None = None) -> str:
        return f'db.index.fulltext.queryNodes("{index}", {query}{", " + options if options else ""})'

    def search_patterns(self, search_terms: str | None) -> list[str]:
        return search_patterns(search_terms)

    def autocomplete_start(self, search_terms: str) -> str:
        # (as typed, in lower case: the label it is compared with is not folded, as Neo4j's index folds only its own copy)
        return " ".join(re.findall(r"\w+", search_terms.lower()))

    def folded_label(self, node: str) -> str:
        return f"toLower({node}.label)"

    def tie_break(self, node: str) -> str:
        return f"elementId({node})"

    def labels_from(self, node: str, labels: str) -> str:
        return f"{node}:$({labels})"

    def facets_from(self, type: str, nodes: str) -> str:
        # (Neo4j has no `collect(key, value)` for a map)
        return f"collect({{type: {type}, nodes: {nodes}}})"

    def read_facets(self, facets: Any) -> dict[str, Any]:
        if isinstance(facets, list):
            return {f["type"]: f["nodes"] for f in facets}
        return facets

    def meta_property(self, node: str, key: str) -> str:
        name = f"meta.{key}"
        return prop(node, json_name(name) if name in ALWAYS_JSON else name)

    def down_tree(self, name: str) -> str:
        return f" {below(name)} "

    def up_reverse(
        self, name: str, *, minimum: int = 1, maximum: int | None = None
    ) -> str:
        return f" {up(name, minimum=minimum, maximum=maximum)} "

    def through_wrappers(self, name: str, *, backwards: bool = False) -> str:
        return f" {through(name, backwards)} "

    def from_wrappers(self, name: str) -> str:
        edge, start = f"{name}_edge", f"{name}_from"
        return f" {hops(name, f'NOT coalesce({edge}.reverse, false) AND {wrapper(start)}', minimum=0)} "

    search_compiler = Neo4jCompiler

    @functools.cached_property
    def migrations(self) -> Any:
        """(`migration_dialect`: made when first asked for)"""
        from pangloss_neo4j.databases.neo4j.migration_dialect import Neo4jMigrations

        return Neo4jMigrations()

    def query(self, name: str, default: str, **context: Any) -> str:
        own = QUERIES.get(name)
        return own(**context) if own else default
