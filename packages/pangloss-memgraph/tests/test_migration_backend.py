"""Applying migrations to a database: the record of them, the lock, and what a run does"""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_memgraph.databases.memgraph import migration_backend as backend
from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_models.exceptions import PanglossMigrationAnswerNeeded, PanglossMigrationError
from pangloss_models.migrations import data_view
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, Migration, MigrationGraph
from pangloss_models.migrations.history import pending, problems
from pangloss_models.migrations.planner import plan
from pangloss_models.migrations.questions import with_answer
from pangloss_models.model_bases.entity import Entity

from .helpers import run
from .migration_support import declare

pytestmark = pytest.mark.asyncio(loop_scope="session")

APPS = ["migapp"]


def in_app(snapshot: dict) -> dict:
    for model in snapshot["models"].values():
        model["module"] = "migapp.models"
    return snapshot


def migrations_between(graph: MigrationGraph, new: dict, answer=None) -> list[Migration]:
    result = plan(graph, in_app(new), APPS, answer=answer)
    assert result.is_final
    return result.migrations


@no_type_check
async def test_migrations_are_applied_and_recorded(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            name: str
            born: int

        return ns(Person=Person)

    old_models, first_snapshot = declare(v1)
    initial = migrations_between(MigrationGraph(), first_snapshot)
    graph = MigrationGraph.of(initial)

    await backend.ensure_ready()
    assert await backend.applied() == {}
    assert [m.name for m in pending(graph, {})] == ["0001_initial"]

    state = await backend.apply(initial, EMPTY_SNAPSHOT)
    assert state == data_view(first_snapshot)
    saved = await old_models.Person.Create(label="Ann", name="Ann").save()

    applied = await backend.applied()
    record = applied[("migapp", "0001_initial")]
    assert record["status"] == "applied"
    assert record["checksum"] == initial[0].checksum
    assert record["applied_by"] == "pangloss_default_user"
    assert pending(graph, applied) == []
    assert problems(graph, applied) == []

    # a later change, with the answer it needs
    new_models, second_snapshot = declare(v2)

    def answer(changes, old):
        return [with_answer(ch, "default", 1900) if ch.kind == "AddField" else ch for ch in changes]

    later = migrations_between(graph, second_snapshot, answer=answer)
    graph = MigrationGraph.of([*initial, *later])
    assert [m.name[:4] for m in pending(graph, applied)] == ["0002"]
    await backend.apply(later, state)

    assert (await new_models.Person.get(id=saved.id)).born == 1900
    assert pending(graph, await backend.applied()) == []


@no_type_check
async def test_a_failed_migration_is_recorded_and_tried_again(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            name: str
            born: int

        return ns(Person=Person)

    old_models, first_snapshot = declare(v1)
    initial = migrations_between(MigrationGraph(), first_snapshot)
    graph = MigrationGraph.of(initial)
    await backend.ensure_ready()
    state = await backend.apply(initial, EMPTY_SNAPSHOT)
    await old_models.Person.Create(label="Ann", name="Ann").save()

    _, second_snapshot = declare(v2)
    later = migrations_between(graph, second_snapshot)  # (no default given)
    graph = MigrationGraph.of([*initial, *later])

    with pytest.raises(PanglossMigrationAnswerNeeded):
        await backend.apply(later, state)
    applied = await backend.applied()
    failed = applied[("migapp", later[0].name)]
    assert failed["status"] == "failed"
    assert "value for the nodes that exist" in failed["error"]
    # it is still to be done
    assert [m.name for m in pending(graph, applied)] == [later[0].name]


@no_type_check
async def test_a_migration_that_was_edited_after_it_was_applied_is_noticed(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    _, snapshot = declare(v1)
    initial = migrations_between(MigrationGraph(), snapshot)
    await backend.ensure_ready()
    await backend.apply(initial, EMPTY_SNAPSHOT)

    edited = Migration(app="migapp", name="0001_initial", changes=initial[0].changes[:0])
    found = problems(MigrationGraph.of([edited]), await backend.applied())
    assert found and "has been changed since" in found[0]

    gone = problems(MigrationGraph(), await backend.applied())
    assert gone and "no such migration" in gone[0]


@no_type_check
async def test_a_migration_can_be_marked_applied_without_running_it(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str
            born: int

        return ns(Person=Person)

    _, snapshot = declare(v1)
    initial = migrations_between(MigrationGraph(), snapshot)
    await backend.ensure_ready()
    state = await backend.apply(initial, EMPTY_SNAPSHOT, fake=True)
    assert state == data_view(snapshot)
    record = (await backend.applied())[("migapp", "0001_initial")]
    assert (record["status"], record["fake"]) == ("applied", True)


async def test_only_one_migrate_at_a_time(db_driver, clear_database):
    await backend.ensure_ready()
    await backend.lock("ann")
    try:
        with pytest.raises(PanglossMigrationError, match="Another migrate is running"):
            await backend.lock("bob")
        assert run(db_driver, "MATCH (l:PGMigrationLock) RETURN l.acquired_by AS who") == [{"who": "ann"}]
    finally:
        await backend.unlock()
    await backend.lock("bob")
    await backend.unlock()
    assert run(db_driver, "MATCH (l:PGMigrationLock) RETURN count(l) AS n") == [{"n": 0}]
