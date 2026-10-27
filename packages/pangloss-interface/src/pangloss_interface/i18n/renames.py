"""What the migrations know about the models: which things were renamed, and whether the models have
changed since the last migration."""

from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.diff import diff
from pangloss_models.migrations.files import graph_of
from pangloss_models.migrations.snapshot import build_snapshot

from pangloss_interface.i18n.merge import ItemRename


def rename_steps(apps: list[str]) -> list[ItemRename]:
    """The renames of models, fields, enums, enum members and reverse names that the migrations record, in order
    (a rename that is not in a migration yet is not here)"""
    steps: list[ItemRename] = []
    for migration in graph_of(apps).order():
        for change in migration.changes:
            if isinstance(change, c.RenameModel):
                steps.append(ItemRename(("models", change.old), ("models", change.new)))
            elif isinstance(change, c.RenameField):
                steps.append(
                    ItemRename(
                        ("models", change.model, "fields", change.old),
                        ("models", change.model, "fields", change.new),
                    )
                )
            elif isinstance(change, c.AlterReverseName):
                # (it is on the model the field points to, which the change does not say)
                steps.append(
                    ItemRename(
                        ("models", "*", "incoming", change.old),
                        ("models", "*", "incoming", change.new),
                    )
                )
            elif isinstance(change, c.RenameEnum):
                steps.append(ItemRename(("enums", change.old), ("enums", change.new)))
            elif isinstance(change, c.RenameEnumMember):
                steps.append(
                    ItemRename(
                        ("enums", change.enum, "members", change.old),
                        ("enums", change.enum, "members", change.new),
                    )
                )
    return steps


def unmigrated(apps: list[str]) -> list[str]:
    """What the models have that the migrations do not (models and enums; the indexes and constraints
    are the database's business). Needs the models to be initialised."""
    try:
        old = graph_of(apps).state()
    except PanglossMigrationError as error:
        return [f"the migrations cannot be read: {error}"]
    result = diff(old, build_snapshot())
    ignored = (c.AddIndex, c.RemoveIndex, c.AddConstraint, c.RemoveConstraint)
    return [
        *(ch.describe() for ch in result.changes if not isinstance(ch, ignored)),
        *(q.question() for q in result.questions),
    ]
