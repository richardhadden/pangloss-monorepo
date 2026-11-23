"""The structure of reconciliation's own nodes (`structure.py`) is what its migration makes, so that `makemigrations`
leaves nothing for a project to write (step 11.4)"""

from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import graph_of
from pangloss_reconcile import structure


def test_the_one_migration_makes_every_index_and_constraint_of_the_structure_and_nothing_else():
    graph = graph_of(["pangloss_reconcile"])
    (migration,) = [m for m in graph.order() if m.app == "pangloss_reconcile"]
    assert migration.name == "0001_initial"
    made = [
        change.index for change in migration.changes if isinstance(change, c.AddIndex)
    ]
    constrained = [
        change.constraint
        for change in migration.changes
        if isinstance(change, c.AddConstraint)
    ]
    assert len(made) + len(constrained) == len(migration.changes)
    assert made == structure.INDEXES
    assert constrained == structure.CONSTRAINTS


def test_a_shown_record_is_unique_by_stand_in_and_user_and_an_example_by_stand_in():
    assert {(e["label"], tuple(e["properties"])) for e in structure.CONSTRAINTS} == {
        ("PGReconcileShown", ("stand_in", "user")),
        ("PGReconcileExample", ("stand_in",)),
    }
