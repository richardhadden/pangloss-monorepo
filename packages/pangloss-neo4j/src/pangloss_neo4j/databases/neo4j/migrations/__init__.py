"""Applying the changes that `pangloss_models.migrations` finds, to a Neo4j database.

- `apply_change(tx, change, state)` makes a change to the data, inside a transaction.
- `run_ddl(database, change, state)` makes the changes to the database itself (indexes and constraints), which
  Neo4j does not allow inside a transaction.
- `is_ddl(change)` says which of the two a change is;
- `apply_changes(database, state, changes)` applies a list of them in order.

`state` is the snapshot of the models *before* the change: it says what the labels of a model
are, and how a field is stored. See `docs/migrations.md`.
"""

from pangloss_neo4j.databases.neo4j.migrations.operations import (
    apply_change,
    is_ddl,
    run_ddl,
)
from pangloss_neo4j.databases.neo4j.migrations.runner import (
    Progress,
    apply_changes,
    apply_changes_in_batches,
    dry_run,
)

__all__ = [
    "Progress",
    "apply_change",
    "apply_changes",
    "apply_changes_in_batches",
    "dry_run",
    "is_ddl",
    "run_ddl",
]
