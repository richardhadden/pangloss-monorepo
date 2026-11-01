"""The folded labels that Memgraph's text index is on (`label_folded`: see `pangloss_models.text`).

Everything written through the models gets one (`MemgraphDialect.encode_properties`); a migration writes it again where
a change set labels in Cypher (`MemgraphMigrations.rederive`), a change by hand (`RunCypher`) too. What was written
before there was one, or by a query of your own outside a migration, is brought up to date by `refold` (`pangloss
memgraph refold`, deprecated), or, in a migration, by `refold_in_migration`."""

from typing import Any

from pangloss_models.text import fold

from pangloss_memgraph.databases.memgraph.database import Database, current
from pangloss_memgraph.databases.memgraph.dialect import FOLDED_LABEL

BATCH_SIZE = 10_000

# (a batch of nodes with a label, in the order of their ids, after the last one done)
_READ = """
MATCH (n:PGIndexableNode)
WHERE n.id > $after AND n.label IS NOT NULL
RETURN n.id AS id, n.label AS label
ORDER BY n.id
LIMIT $size
"""

_WRITE = f"""
UNWIND $rows AS row
MATCH (n:PGIndexableNode {{id: row.id}})
SET n.{FOLDED_LABEL} = row.folded
"""


async def _refold_batch(tx: Any, after: str, size: int) -> tuple[str | None, int]:
    """Fold the labels of a batch; gives the last id done (None when there were none) and how many were changed"""
    result = await tx.run(_READ, after=after, size=size)
    rows = [
        {"id": record["id"], "folded": fold(record["label"])}
        async for record in result
        if isinstance(record["label"], str)
    ]
    if not rows:
        return None, 0
    await (await tx.run(_WRITE, rows=rows)).consume()
    return rows[-1]["id"], len(rows)


async def refold(database: Database | None = None, batch_size: int = BATCH_SIZE) -> int:
    """Write the folded label of every node that has a label, `batch_size` nodes to a transaction. Gives how many"""
    database = database or current()
    after, total = "", 0
    while True:

        @database.write_transaction
        async def batch(tx: Any) -> tuple[str | None, int]:
            return await _refold_batch(tx, after, batch_size)

        last, done = await batch()
        if last is None:
            return total
        after, total = last, total + done


async def refold_in_migration(tx: Any, state: Any) -> None:
    """The same, in the transaction of a migration (`RunPython`, shipped migration 0006)"""
    after: str | None = ""
    while after is not None:
        after, _ = await _refold_batch(tx, after, BATCH_SIZE)
