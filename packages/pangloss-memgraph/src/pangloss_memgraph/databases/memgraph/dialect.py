"""Memgraph's answers where the Cypher backends differ (`pangloss_cypher.dialect.Dialect`)"""

from typing import Any

import neo4j
from pangloss_models.text import fold

from pangloss_cypher.transaction import Transaction

# Down the tree of a document: forward edges (a relation is stored as a forward edge and a reverse one marked
# `reverse: true`, which is not followed), not into an entity or the URL of one
# The property of a node that the text index is on: its label, folded (`pangloss_models.text.fold`)
FOLDED_LABEL = "label_folded"

TREE_TRAVERSAL = "[*BFS (edge, node | NOT node:Entity AND NOT node:PGUrl AND NOT coalesce(edge.reverse, false))]"


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
        return f"{start}-{TREE_TRAVERSAL}->{end}"
