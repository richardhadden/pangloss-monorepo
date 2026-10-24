"""Helpers for the tests of migrations: models declared in two versions, data written with
the first, migrated, and read with the second"""

from types import SimpleNamespace

from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.migrations import (
    apply_changes,
    apply_changes_in_batches,
)
from pangloss_models import initialise
from pangloss_models.meta_kit.migrations import build_snapshot, diff
from pangloss_models.model_registry import ModelRegistry


def declare(version) -> tuple[SimpleNamespace, dict]:
    """The models that `version()` declares (it returns them in a namespace), initialised, and
    their snapshot. The models of any other version are forgotten."""
    ModelRegistry._reset()
    models = version()
    initialise()
    return models, build_snapshot()


async def migrate(
    old: dict, new: dict, answer=None, batch_size: int | None = None, **diff_answers
):
    """Apply the changes from `old` to `new` to the database. `answer(changes)` may fill in
    the answers a change needs: it returns the changes to apply. With a `batch_size` they are made
    in batches of that size. Returns them."""
    result = diff(old, new, **diff_answers)
    assert result.is_final, [q.question() for q in result.questions]
    changes = answer(result.changes) if answer else result.changes
    if batch_size:
        await apply_changes_in_batches(Database.default, old, changes, batch_size)
    else:
        await apply_changes(Database.default, old, changes)
    return changes


def with_answers(**by_kind):
    """An `answer` for `migrate`: for each kind of change, the fields to set on it, e.g.
    `with_answers(AddField={"default": 3})`"""
    import dataclasses

    def answer(changes):
        return [
            dataclasses.replace(change, **by_kind[change.kind])
            if change.kind in by_kind
            else change
            for change in changes
        ]

    return answer
