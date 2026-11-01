"""Memgraph's answers where the Cypher backends differ (`pangloss_cypher.dialect.Dialect`)"""

import functools
from typing import Any

import neo4j
from pangloss_models.autocomplete import search_words
from pangloss_models.text import fold

from pangloss_cypher.search_query import Compiler, wrapper
from pangloss_cypher.transaction import Transaction

# The property of a node that the text index is on: its label, folded (`pangloss_models.text.fold`)
FOLDED_LABEL = "label_folded"


def with_folded_label(properties: dict[str, Any]) -> dict[str, Any]:
    """The properties of a node, with `label_folded` beside its `label`. (A `label` of null gives a null `label_folded`,
    so that `SET n += ...` takes away the old one with the label)"""
    if "label" not in properties:
        return properties
    label = properties["label"]
    return {**properties, FOLDED_LABEL: fold(label) if isinstance(label, str) else None}


class MemgraphDialect:
    name = "memgraph"

    def driver_options(self) -> dict[str, Any]:
        return {}

    def wrap_transaction(self, tx: Any) -> Any:
        return tx

    def is_timeout(self, error: Exception) -> bool:
        """(Memgraph reports it as a transient error, which the driver would try again, and the search would take as
        long again)"""
        return (
            isinstance(error, neo4j.exceptions.TransientError)
            and "timeout" in str(error).lower()
        )

    def is_unique_violation(self, error: Exception) -> bool:
        return isinstance(error, neo4j.exceptions.ConstraintError) or (
            isinstance(error, neo4j.exceptions.ClientError)
            and "unique constraint" in str(error).lower()
        )

    # (Memgraph's snapshot isolation makes the second of two writers that conflict run again; a check sees the
    # database as it was when the transaction began, so a conflict it finds is one)
    retry_on_check_conflict = False

    async def before_replace(self, tx: Transaction, id: Any) -> None:
        pass

    def encode_properties(
        self, properties: dict[str, Any], *, node: bool = True
    ) -> dict[str, Any]:
        """A node with a label gets `label_folded`, which the text index is on (Memgraph's index does not fold accents)"""
        return with_folded_label(properties) if node else properties

    def has_meta(self, node: str) -> str:
        return f"{node}.meta IS NOT NULL"

    def meta_of(self, node: str) -> str:
        return f"{node}.meta"

    def entity_labels(self) -> str:
        return ":Entity"

    def tree_below(self, start: str, end: str) -> str:
        return f"{start}{self.down_tree('tree')}{end}"

    # --- reading ----------------------------------------------------------------------------------------------------

    def text_search(self, index: str, query: str, options: str | None = None) -> str:
        return f'text_search.regex_search("{index}", {query}{", " + options if options else ""})'

    def search_patterns(self, search_terms: str | None) -> list[str]:
        """A regular expression for each word of the search. The words are cut as the index cuts a label (`search_words`),
        so no regular-expression character (`(`, `.`, `[`) gets into a pattern; nothing to search for is no pattern
        (`.*.*` would be every node of the index)"""
        return [f".*{word}.*" for word in search_words(search_terms or "")]

    def autocomplete_start(self, search_terms: str) -> str:
        return " ".join(search_words(search_terms))

    def folded_label(self, node: str) -> str:
        return f"{node}.{FOLDED_LABEL}"

    def tie_break(self, node: str) -> str:
        return f"id({node})"

    def facets_from(self, type: str, nodes: str) -> str:
        return f"collect({type}, {nodes})"

    def read_facets(self, facets: Any) -> dict[str, Any]:
        return facets

    def meta_property(self, node: str, key: str) -> str:
        return f"{node}.meta.{key}"

    def down_tree(self, name: str) -> str:
        # (forward edges: a relation is stored as a forward edge and a reverse one marked `reverse: true`, which is not
        # followed)
        edge, to = f"{name}_edge", f"{name}_to"
        return f"-[*BFS ({edge}, {to} | NOT {to}:Entity AND NOT {to}:PGUrl AND NOT coalesce({edge}.reverse, false))]->"

    def up_reverse(
        self, name: str, *, minimum: int = 1, maximum: int | None = None
    ) -> str:
        # (breadth first, which finds the nearest; from no step at all, depth first)
        edge, to = f"{name}_edge", f"{name}_to"
        if minimum == 0:
            walk = f"* 0..{'' if maximum is None else maximum}"
        else:
            walk = f"*BFS{'' if maximum is None else f' ..{maximum}'}"
        return f"-[{walk} ({edge}, {to} | coalesce({edge}.reverse, false))]->"

    def through_wrappers(self, name: str, *, backwards: bool = False) -> str:
        edge, to = f"{name}_edge", f"{name}_to"
        walk = f"[* 0.. ({edge}, {to} | {wrapper(to)})]"
        return f"<-{walk}-" if backwards else f"-{walk}->"

    search_compiler = Compiler

    @functools.cached_property
    def migrations(self) -> Any:
        """(`migration_dialect`, which needs the modules that need this one: made when first asked for)"""
        from pangloss_memgraph.databases.memgraph.migration_dialect import (
            MemgraphMigrations,
        )

        return MemgraphMigrations()

    def query(self, name: str, default: str, **context: Any) -> str:
        return default
