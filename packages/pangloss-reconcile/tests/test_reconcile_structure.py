"""The structure of reconciliation's own nodes (`structure.py`) is what its migrations make, so that `makemigrations`
leaves nothing for a project to write (steps 11.4 and 11.5)"""

from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import graph_of
from pangloss_reconcile import structure


def test_the_migrations_make_every_index_and_constraint_of_the_structure_and_nothing_else():
    graph = graph_of(["pangloss_reconcile"])
    migrations = [m for m in graph.order() if m.app == "pangloss_reconcile"]
    assert [m.name for m in migrations] == ["0001_initial", "0002_models"]
    changes = [change for m in migrations for change in m.changes]
    made = [change.index for change in changes if isinstance(change, c.AddIndex)]
    constrained = [
        change.constraint for change in changes if isinstance(change, c.AddConstraint)
    ]
    assert len(made) + len(constrained) == len(changes)
    assert made == structure.INDEXES
    assert constrained == structure.CONSTRAINTS


def test_a_shown_record_is_unique_by_stand_in_and_user_an_example_by_stand_in_and_a_fit_by_id():
    assert {(e["label"], tuple(e["properties"])) for e in structure.CONSTRAINTS} == {
        ("PGReconcileShown", ("stand_in", "user")),
        ("PGReconcileExample", ("stand_in",)),
        ("PGReconcileModel", ("id",)),
    }
