"""What an installed app is given of a migration as it is applied (`hooks.migration_changes`): each change of the data,
in the transaction that makes it, with the snapshots before and after it, and which migration it is of"""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_cypher.migrations import apply_changes_in_batches
from pangloss_models import Entity, hooks
from pangloss_models.migrations import Migration, apply_change
from pangloss_models.migrations import changes as c
from pangloss_testing.under_test import migration_backend as backend
from pangloss_testing.under_test.database import current

from .helpers import run
from .migration_support import declare

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models():
    class Person(Entity):
        name: str
        born: int | None = None

    return ns(Person=Person)


RENAME = c.RenameField(model="Person", old="born", new="year")
MARK = c.RunCypher(query="MATCH (n:Person) SET n.seen = true")
INDEX = {"kind": "label+property", "label": "Person", "properties": ["name"]}


class Listener:
    """A throwaway app: it keeps what it is given, and writes a node in the transaction of each change"""

    def __init__(self, fails_on: str | None = None):
        self.steps: list[hooks.MigrationStep] = []
        self.fails_on = fails_on

    async def __call__(self, tx, step: hooks.MigrationStep) -> None:
        self.steps.append(step)
        result = await tx.run("CREATE (:HookSeen {kind: $kind})", kind=step.change.kind)
        await result.consume()
        if step.change.kind == self.fails_on:
            raise RuntimeError("the app refuses")

    @property
    def kinds(self) -> list[str]:
        return [step.change.kind for step in self.steps]


@pytest.fixture
def listener():
    made = Listener()
    hooks.migration_changes.append(made)
    yield made
    hooks.migration_changes.remove(made)


def seen(db_driver) -> list[str]:
    return sorted(
        row["kind"]
        for row in run(db_driver, "MATCH (n:HookSeen) RETURN n.kind AS kind")
    )


async def people(made) -> None:
    for name, born in (("Ann", 1450), ("Bob", 1460), ("Cat", 1470)):
        await made.Person.Create(label=name, name=name, born=born).save()


def years(db_driver) -> list:
    rows = run(
        db_driver,
        "MATCH (n:Person) RETURN n.born AS born, n.year AS year ORDER BY n.name",
    )
    return [(row["born"], row["year"]) for row in rows]


@no_type_check
async def test_each_change_of_the_data_is_given_in_order_with_its_snapshots_and_its_migration(
    db_driver, clear_database, listener
):
    made, state = declare(models)
    await backend.ensure_ready()
    await people(made)
    migration = Migration(
        app="migapp",
        name="0002_hook",
        changes=(c.AddIndex(index=INDEX), RENAME, MARK, c.RemoveIndex(index=INDEX)),
    )

    await backend.apply([migration], state)

    # (not the index: a change of the database itself is made between transactions)
    assert listener.kinds == ["RenameField", "RunCypher"]
    first, second = listener.steps
    assert {step.migration for step in listener.steps} == {"migapp.0002_hook"}
    assert not any(step.undoing or step.dry_run for step in listener.steps)
    assert first.after == apply_change(first.before, RENAME)
    assert "born" in str(first.before["models"]["Person"]["fields"])
    assert second.before == first.after
    assert seen(db_driver) == ["RenameField", "RunCypher"]
    assert years(db_driver) == [(None, 1450), (None, 1460), (None, 1470)]


@no_type_check
async def test_what_an_app_writes_goes_back_with_the_change_when_the_transaction_fails(
    db_driver, clear_database, listener
):
    made, state = declare(models)
    await backend.ensure_ready()
    await people(made)
    migration = Migration(
        app="migapp",
        name="0002_fails",
        changes=(MARK, RENAME, c.RunPython(function=f"{__name__}:refuse")),
    )
    with pytest.raises(RuntimeError, match="not today"):
        await backend.apply([migration], state)

    # (it was given both changes before the third failed, and nothing of them is kept)
    assert listener.kinds == ["RunCypher", "RenameField"]
    assert seen(db_driver) == []
    assert years(db_driver) == [(1450, None), (1460, None), (1470, None)]


def refuse(tx, state):
    """(a function of a migration)"""
    raise RuntimeError("not today")


@no_type_check
async def test_an_app_that_raises_fails_the_migration_and_nothing_of_it_is_kept(
    db_driver, clear_database
):
    made, state = declare(models)
    await backend.ensure_ready()
    await people(made)
    failing = Listener(fails_on="RenameField")
    hooks.migration_changes.append(failing)
    try:
        with pytest.raises(RuntimeError, match="the app refuses"):
            await backend.apply(
                [Migration(app="migapp", name="0002_refused", changes=(MARK, RENAME))],
                state,
            )
    finally:
        hooks.migration_changes.remove(failing)
    assert seen(db_driver) == []
    assert years(db_driver) == [(1450, None), (1460, None), (1470, None)]
    applied = run(
        db_driver,
        "MATCH (m:PGMigration {name: '0002_refused'}) RETURN m.status AS status",
    )
    assert [row["status"] for row in applied] == ["failed"]


@no_type_check
async def test_a_change_made_in_batches_is_given_once_after_the_last_batch(
    db_driver, clear_database, listener
):
    made, state = declare(models)
    await backend.ensure_ready()
    await people(made)

    await backend.apply(
        [Migration(app="migapp", name="0002_batches", changes=(RENAME, MARK))],
        state,
        batch_size=1,
    )

    assert listener.kinds == ["RenameField", "RunCypher"]
    assert listener.steps[0].migration == "migapp.0002_batches"
    assert years(db_driver) == [(None, 1450), (None, 1460), (None, 1470)]
    assert seen(db_driver) == ["RenameField", "RunCypher"]

    # (changes applied on their own say no migration)
    listener.steps.clear()
    await apply_changes_in_batches(
        current(),
        apply_change(state, RENAME),
        [c.RenameField(model="Person", old="year", new="born")],
        1,
    )
    assert listener.kinds == ["RenameField"] and listener.steps[0].migration is None


@no_type_check
async def test_a_dry_run_gives_the_changes_as_a_dry_run_and_keeps_nothing(
    db_driver, clear_database, listener
):
    made, state = declare(models)
    await backend.ensure_ready()
    await people(made)

    (report,) = await backend.dry_run(
        [Migration(app="migapp", name="0002_tried", changes=(RENAME, MARK))], state
    )

    assert [change.status for change in report.changes] == ["counted", "counted"]
    assert listener.kinds == ["RenameField", "RunCypher"]
    assert all(step.dry_run for step in listener.steps)
    assert listener.steps[0].migration == "migapp.0002_tried"
    assert seen(db_driver) == []
    assert years(db_driver) == [(1450, None), (1460, None), (1470, None)]


@no_type_check
async def test_a_migration_undone_gives_the_changes_that_undo_it_as_undoing(
    db_driver, clear_database, listener
):
    made, state = declare(models)
    await backend.ensure_ready()
    await people(made)
    forward = Migration(app="migapp", name="0002_undone", changes=(RENAME,))
    after = await backend.apply([forward], state)
    listener.steps.clear()

    undoing = Migration(
        app="migapp",
        name="0002_undone",
        changes=(c.RenameField(model="Person", old="year", new="born"),),
    )
    await backend.unapply([undoing], after)

    (step,) = listener.steps
    assert step.undoing and step.migration == "migapp.0002_undone"
    assert step.change.old == "year" and step.before == after
    assert years(db_driver) == [(1450, None), (1460, None), (1470, None)]
