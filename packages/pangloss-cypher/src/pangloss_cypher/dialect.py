"""Where the Cypher backends differ: the `Dialect` a backend gives, which the shared code calls at those points (and only
those: see `docs/database-abstraction.md` §3 for what differs, measured).

A backend's `Database` class has its dialect (`Database.dialect`); the code of the kit finds it with `dialect()`, from the
database in use."""

from typing import Any, Protocol

from pangloss_cypher.transaction import Transaction


class Dialect(Protocol):
    name: str
    """`memgraph`, `neo4j`: also the middle of the names of the loggers (`pangloss.<name>.transactions`)"""

    # --- the driver and the transactions --------------------------------------------------------------------------

    def driver_options(self) -> dict[str, Any]:
        """More keyword arguments for the driver, besides the URL, the credentials, `keep_alive` and the retry time"""
        ...

    def wrap_transaction(self, tx: Any) -> Any:
        """The transaction a function of the kit is given, made from the driver's (Neo4j's decodes the maps it keeps
        flat; Memgraph's is the driver's)"""
        ...

    def is_timeout(self, error: Exception) -> bool:
        """Whether the database stopped the transaction because it ran longer than it was allowed"""
        ...

    def is_unique_violation(self, error: Exception) -> bool:
        """Whether a write was refused at its commit for breaking a uniqueness constraint (an id or a URL that another
        write took at the same moment)"""
        ...

    retry_on_check_conflict: bool
    """Whether a write that a check found to conflict is tried again: on a database that reads what is committed, a
    conflict found by a check may be a race that was lost, and is found as what it is the next time"""

    async def before_replace(self, tx: Transaction, id: Any) -> None:
        """Called in the transaction of an update, before the head node's version is read (Neo4j takes the node's
        lock here, as it does not make the second of two writers run again)"""
        ...

    # --- the storage format ---------------------------------------------------------------------------------------

    def encode_properties(self, properties: dict[str, Any]) -> dict[str, Any]:
        """The properties of a node or an edge, as they are written"""
        ...

    def has_meta(self, node: str) -> str:
        """A condition: the node has a `meta`"""
        ...

    def meta_of(self, node: str) -> str:
        """An expression: the `meta` of the node, as a map"""
        ...

    def entity_labels(self) -> str:
        """The labels to match an entity by its id with (`(:Entity {id: $id})`)"""
        ...

    def tree_below(self, start: str, end: str) -> str:
        """A path pattern from the node pattern `start` down the tree of a document to the node pattern `end`: forward
        edges, not into an entity or a URL"""
        ...
