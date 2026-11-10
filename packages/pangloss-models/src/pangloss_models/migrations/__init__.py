"""Finding what changed between two versions of the models, and writing it as migrations (see
`implementation_docs/migrations.md`).

- `build_snapshot()` describes the initialised models as they are stored;
- `diff(old, new)` compares two snapshots and returns the changes between them, and the
  questions that cannot be answered from the models (is this a rename?);
- `replay(old, changes)` applies changes to a snapshot: for the changes that `diff` finds, it
  gives the new snapshot;
- `files` is the migration file format and the graph of an app's migrations, `planner` makes the
  migrations to write from the changes, and `questions` is what a person is asked.

Nothing here touches a database; applying a change to one is the business of the database
package (`pangloss_memgraph.databases.memgraph.migrations`).

What a migration file uses (`changes_from_data`, and the changes written by hand: `RunPython`, `RunCypher`,
`StateOnly`, ...) is imported from here.
"""

from pangloss_models.migrations.changes import (
    AddConstraint,
    AddEnumMember,
    AddField,
    AddIndex,
    AlterAnnotatedValue,
    AlterCardinality,
    AlterEdgeModel,
    AlterEmbedded,
    AlterEnumMemberValue,
    AlterListItemType,
    AlterLiteralType,
    AlterModelKind,
    AlterModelLabels,
    AlterModelOption,
    AlterNullability,
    AlterParentFields,
    AlterRelationTarget,
    AlterReverseName,
    AnnotatedValueToLiteral,
    Change,
    ChangeFieldKind,
    ChangeWrapper,
    CreateEnum,
    CreateModel,
    DeleteModel,
    EmbeddedToLiterals,
    LiteralToAnnotatedValue,
    LiteralsToEmbedded,
    PossibleRename,
    RecomputeFulfils,
    RemoveConstraint,
    RemoveEnum,
    RemoveEnumMember,
    RemoveField,
    RemoveIndex,
    RenameEnum,
    RenameEnumMember,
    RenameField,
    RenameModel,
    RunCypher,
    RunPython,
    StateOnly,
    UnwrapRelation,
    WrapRelation,
    change_from_dict,
)

# (not lazy: `diff` is also the name of a module, which would take its place when it is imported first)
from pangloss_models.migrations.diff import DiffResult, diff
from pangloss_models.migrations.snapshot import build_snapshot, data_view, snapshot_hash
from pangloss_models.migrations.state import apply_change, replay

lazy from pangloss_models.migrations.files import Migration, changes_from_data

__all__ = [
    "AddConstraint",
    "AddEnumMember",
    "AddField",
    "AddIndex",
    "AlterAnnotatedValue",
    "AlterCardinality",
    "AlterEdgeModel",
    "AlterEmbedded",
    "AlterEnumMemberValue",
    "AlterListItemType",
    "AlterLiteralType",
    "AlterModelKind",
    "AlterModelLabels",
    "AlterModelOption",
    "AlterNullability",
    "AlterParentFields",
    "AlterRelationTarget",
    "AlterReverseName",
    "AnnotatedValueToLiteral",
    "apply_change",
    "build_snapshot",
    "Change",
    "change_from_dict",
    "ChangeFieldKind",
    "changes_from_data",
    "ChangeWrapper",
    "CreateEnum",
    "CreateModel",
    "data_view",
    "DeleteModel",
    "diff",
    "DiffResult",
    "EmbeddedToLiterals",
    "LiteralsToEmbedded",
    "LiteralToAnnotatedValue",
    "Migration",
    "PossibleRename",
    "RecomputeFulfils",
    "RemoveConstraint",
    "RemoveEnum",
    "RemoveEnumMember",
    "RemoveField",
    "RemoveIndex",
    "RenameEnum",
    "RenameEnumMember",
    "RenameField",
    "RenameModel",
    "replay",
    "RunCypher",
    "RunPython",
    "snapshot_hash",
    "StateOnly",
    "UnwrapRelation",
    "WrapRelation",
]
