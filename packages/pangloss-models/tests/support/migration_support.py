"""Helpers for the tests of migrations: the snapshots of models that a function declares"""

from pangloss_models import initialise
from pangloss_models.meta_kit.migrations import build_snapshot, data_view, diff, replay
from pangloss_models.model_registry import ModelRegistry


def snapshot_of(declare) -> dict:
    """The snapshot of the models that `declare` declares (and nothing else)"""
    ModelRegistry._reset()
    declare()
    initialise()
    return build_snapshot()


def changes(before, after, **answers):
    old, new = snapshot_of(before), snapshot_of(after)
    result = diff(old, new, **answers)
    # Whatever is found, applying it to the old snapshot gives the new: the property that
    # makes the changes complete (nothing is found that is not in the models, and nothing in
    # the models is missed)
    assert replay(old, result.changes) == data_view(new)
    check_reversal(old, result.changes)
    return result


def check_reversal(old, found):
    """Whatever can be undone is undone to the models as they were (reversing is checked in
    every case that finds changes; what cannot be is said so, not wrong)"""
    from pangloss_models.exceptions import PanglossMigrationIrreversible
    from pangloss_models.meta_kit.migrations.reverse import reverse_changes

    try:
        reversal = reverse_changes(found, data_view(old))
    except PanglossMigrationIrreversible:
        return
    assert replay(replay(old, found), reversal.changes) == data_view(old)
