"""Finding what changed between two versions of the models, and writing it as migrations (see
`docs/migrations.md`).

- `build_snapshot()` describes the initialised models as they are stored;
- `diff(old, new)` compares two snapshots and returns the changes between them, and the
  questions that cannot be answered from the models (is this a rename?);
- `replay(old, changes)` applies changes to a snapshot: for the changes that `diff` finds, it
  gives the new snapshot;
- `files` is the migration file format and the graph of an app's migrations, `planner` makes the
  migrations to write from the changes, and `questions` is what a person is asked.

Nothing here touches a database; applying a change to one is the business of the database
package (`pangloss_memgraph.databases.memgraph.migrations`).
"""

from pangloss_models.migrations.changes import Change, PossibleRename, change_from_dict
from pangloss_models.migrations.diff import DiffResult, diff
from pangloss_models.migrations.state import apply_change, replay
from pangloss_models.migrations.snapshot import (
    build_snapshot,
    data_view,
    snapshot_hash,
)

__all__ = [
    "Change",
    "apply_change",
    "change_from_dict",
    "replay",
    "DiffResult",
    "PossibleRename",
    "build_snapshot",
    "data_view",
    "diff",
    "snapshot_hash",
]
