"""Where the Cypher backends differ: the `Dialect` a backend gives, which the shared code calls at those points (and only
those: see `docs/database-abstraction.md` §3 for what differs, measured).

A backend's `Database` class has its dialect (`Database.dialect`); the code of the kit finds it with `dialect()`, from the
database in use."""

from typing import Any, Protocol

from pangloss_models.migrations import changes as c

from pangloss_cypher.transaction import Transaction


class MigrationDialect(Protocol):
    """Where the backends differ in a migration (`pangloss_cypher.migrations`): how a map is stored (a `meta`, an
    annotated value, a `TypedDict`), what a backend derives from what the models write, a walk, and the changes to the
    database itself (indexes and constraints). `Dialect.migrations`"""

    def owned(self, name: str) -> str:
        """A path between two node patterns, from a node down to what it owns: forward edges, not into an entity. (The
        variables in it start with `name`)"""
        ...

    def meta_mentions(self, node: str, model: str) -> str:
        """A condition: the `meta` of the node has the name of a model (`model`, an expression) in its semantic spaces
        or its context labels"""
        ...

    inserted_node_meta: str
    """The clauses that make `new_meta`, for a node a migration makes beside the node `s`, for what `s` holds: its
    times and creator are those of `s` (or, for a head node, which has no `meta`, of its creation); it is in the
    semantic spaces `s` is in; and its context is that of `s`, with `s` in it if `s` is a document nested in another.
    The query gives `$labels_in_context`"""

    def new_meta_properties(self, *, context: bool) -> str:
        """The entries of a map of properties (`CREATE (r {...})`) that give the new node `new_meta` (with
        `context=False`, the times and creator only, no semantic spaces and no context)"""
        ...

    def meta_properties(self, meta: dict[str, Any]) -> dict[str, Any]:
        """The properties that make a node's `meta` this (by `SET n += ...`), what it does not have taken away"""
        ...

    def set_map(self, node: str, name: str, entries: dict[str, str]) -> str:
        """A `SET` clause (or more) that makes the property `name` of the node a map of `entries` (name: expression),
        in place of what it was"""
        ...

    def map_value(self, node: str, name: str, key: str) -> str:
        """An expression: the value at `key` of the map that is the property `name` of the node"""
        ...

    def unwrap_map(self, node: str, name: str, key: str, keys: list[str]) -> str:
        """A `SET` clause (or more) that makes the property `name`, a map with `keys`, the value it has at `key`"""
        ...

    def enum_test(
        self, node: str, name: str, descriptor: dict[str, Any], enum: str, keys: str
    ) -> str:
        """A condition: the property `name` of the node (or edge), of the type `descriptor`, has in it a value of `enum`
        that is one of the parameter `keys` (their text). The type is one that can have one (`has_enum`)"""
        ...

    def enum_rewrite(
        self, node: str, name: str, descriptor: dict[str, Any], enum: str, values: str
    ) -> list[tuple[str, str]]:
        """What to set, for the values of `enum` in the property `name` of the node (or edge) that are keys of the map
        that is the parameter `values` (by their text) to be what it says: pairs of what is set (`n.name`) and its new
        value"""
        ...

    async def rederive(self, tx: Transaction, labels: list[str] | None) -> None:
        """Write again what the backend derives from a node's `label` (Memgraph's `label_folded`), where it is not what
        the label gives, for the nodes with one of `labels` (with None, every node): after a migration changed labels
        in Cypher"""
        ...

    async def add_index(self, database: Any, change: c.AddIndex, state: dict) -> None:
        """Make the index (`AddIndex`), if it is not there: outside a transaction"""
        ...

    async def remove_index(
        self, database: Any, change: c.RemoveIndex, state: dict
    ) -> None: ...

    async def add_constraint(
        self, database: Any, change: c.AddConstraint, state: dict
    ) -> None:
        """Make the uniqueness constraint (`AddConstraint`), if it is not there; a `PanglossMigrationError` if the data
        breaks it"""
        ...

    async def remove_constraint(
        self, database: Any, change: c.RemoveConstraint, state: dict
    ) -> None: ...


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

    def encode_properties(
        self, properties: dict[str, Any], *, node: bool = True
    ) -> dict[str, Any]:
        """The properties of a node (or, with `node=False`, an edge), as they are written. (Memgraph adds a node's
        `label_folded`, which its text index is on: see `pangloss_models.text`)"""
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

    # --- reading ----------------------------------------------------------------------------------------------------

    def text_search(self, index: str, query: str, options: str | None = None) -> str:
        """A call of the text index `index` for `query` (an expression: one of the patterns of `search_patterns`), with
        `options` (a map, as text: `{limit: $limit}`), to be written after `CALL` and before `YIELD node, score`"""
        ...

    def search_patterns(self, search_terms: str | None) -> list[str]:
        """What the text index is asked for, a pattern for each word of the search: none if there is nothing to search for"""
        ...

    def autocomplete_start(self, search_terms: str) -> str:
        """What was typed, as `folded_label` is to be compared with (to put the labels that begin with it first)"""
        ...

    def folded_label(self, node: str) -> str:
        """An expression: the label of the node, as `autocomplete_start` is"""
        ...

    def tie_break(self, node: str) -> str:
        """An expression to order nodes by when all else is equal (the database's own id of the node)"""
        ...

    def facets_from(self, type: str, nodes: str) -> str:
        """An aggregation: the facets of a list, the `nodes` of each `type`, in a form `read_facets` reads"""
        ...

    def read_facets(self, facets: Any) -> dict[str, Any]:
        """The facets of `facets_from`, as `{type: nodes}`"""
        ...

    def meta_property(self, node: str, key: str) -> str:
        """An expression: one value of the `meta` of the node (`semantic_spaces`, `context_labels`)"""
        ...

    def down_tree(self, name: str) -> str:
        """A path between two node patterns, down the tree of a document: forward edges, not into an entity or a URL. (The
        variables in it start with `name`)"""
        ...

    def up_reverse(
        self, name: str, *, minimum: int = 1, maximum: int | None = None
    ) -> str:
        """A path between two node patterns, up from a node to what holds it, along the reverse edges: at least `minimum`
        long (0: the node itself is the end too), and at most `maximum`. (The variables in it start with `name`)"""
        ...

    def through_wrappers(self, name: str, *, backwards: bool = False) -> str:
        """A path between two node patterns through any number of wrappers (a semantic space, a conjunction, a reified
        relation), none too: the path goes on only through them. `backwards`: against the direction of the edges. (The
        variables in it start with `name`)"""
        ...

    @property
    def search_compiler(self) -> type:
        """The class that makes a structured search into Cypher: `pangloss_cypher.search_query.Compiler`, or a subclass that
        finds some of what is tested in another way, for its planner"""
        ...

    migrations: MigrationDialect
    """Where the backends differ in a migration"""

    def query(self, name: str, default: str, **context: Any) -> str:
        """The text of the query (or part of one) called `name` (`"list.plain.page"`): `default`, the kit's, unless the
        backend has its own for it. A replacement takes the same parameters and gives the same columns; it is for where one
        text is slow on one backend. `context`: what the kit made the default from (`object_class`)"""
        ...
