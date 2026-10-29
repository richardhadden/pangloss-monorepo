"""Applying migrations to a database: the record of them, the lock, and what a run does"""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_models.exceptions import (
    PanglossMigrationAnswerNeeded,
    PanglossMigrationError,
)
from pangloss_models.migrations import data_view
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, Migration, MigrationGraph
from pangloss_models.migrations.history import pending, problems
from pangloss_models.migrations.planner import plan
from pangloss_models.migrations.questions import with_answer
from pangloss_models.model_bases.entity import Entity
from pangloss_neo4j.databases.neo4j import migration_backend as backend

from .helpers import run
from .migration_support import declare

pytestmark = pytest.mark.asyncio(loop_scope="session")

APPS = ["migapp"]


def in_app(snapshot: dict) -> dict:
    for model in snapshot["models"].values():
        model["module"] = "migapp.models"
    return snapshot


def migrations_between(
    graph: MigrationGraph, new: dict, answer=None
) -> list[Migration]:
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
        return [
            with_answer(ch, "default", 1900) if ch.kind == "AddField" else ch
            for ch in changes
        ]

    later = migrations_between(graph, second_snapshot, answer=answer)
    graph = MigrationGraph.of([*initial, *later])
    assert [m.name[:4] for m in pending(graph, applied)] == ["0002"]
    await backend.apply(later, state)

    assert (await new_models.Person.get(id=saved.id)).born == 1900
    assert pending(graph, await backend.applied()) == []


@no_type_check
async def test_a_failed_migration_is_recorded_and_tried_again(
    db_driver, clear_database
):
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
async def test_a_migration_that_was_edited_after_it_was_applied_is_noticed(
    db_driver, clear_database
):
    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    _, snapshot = declare(v1)
    initial = migrations_between(MigrationGraph(), snapshot)
    await backend.ensure_ready()
    await backend.apply(initial, EMPTY_SNAPSHOT)

    edited = Migration(
        app="migapp", name="0001_initial", changes=initial[0].changes[:0]
    )
    found = problems(MigrationGraph.of([edited]), await backend.applied())
    assert found and "has been changed since" in found[0]

    gone = problems(MigrationGraph(), await backend.applied())
    assert gone and "no such migration" in gone[0]


@no_type_check
async def test_a_migration_can_be_marked_applied_without_running_it(
    db_driver, clear_database
):
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
        assert run(
            db_driver, "MATCH (l:PGMigrationLock) RETURN l.acquired_by AS who"
        ) == [{"who": "ann"}]
    finally:
        await backend.unlock()
    await backend.lock("bob")
    await backend.unlock()
    assert run(db_driver, "MATCH (l:PGMigrationLock) RETURN count(l) AS n") == [
        {"n": 0}
    ]


def test_this_backend_has_no_snapshots_and_the_commands_say_so():
    """Memgraph takes and restores snapshots; Neo4j Community has no online snapshot (`neo4j-admin database dump` is offline).
    The functions are optional in the contract, and `pangloss migrate --backup`, `backups` and `restore` check for them
    (`hasattr`) and say that this database cannot."""
    for name in ("backup", "backups", "backup_notice", "restore"):
        assert not hasattr(backend, name), name


@no_type_check
async def test_a_migration_is_undone_and_its_record_removed(db_driver, clear_database):
    from dataclasses import replace

    from pangloss_models.migrations.reverse import reverse_changes

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
    saved = await old_models.Person.Create(label="Ann", name="Ann").save()

    new_models, second_snapshot = declare(v2)

    def answer(changes, old):
        return [
            with_answer(ch, "default", 1900) if ch.kind == "AddField" else ch
            for ch in changes
        ]

    later = migrations_between(graph, second_snapshot, answer=answer)
    after = await backend.apply(later, state)
    assert (await new_models.Person.get(id=saved.id)).born == 1900

    reversal = reverse_changes(later[0].changes, state)
    undoing = replace(later[0], changes=tuple(reversal.changes))
    assert await backend.unapply([undoing], after) == state

    assert [key[1] for key in await backend.applied()] == ["0001_initial"]
    old_models, _ = declare(v1)
    assert (await old_models.Person.get(id=saved.id)).name == "Ann"
    assert run(db_driver, "MATCH (n:Person) RETURN n.born AS born") == [{"born": None}]

    # (and it can be applied again)
    await backend.apply(later, state)
    assert (await new_models.Person.get(id=saved.id)).born == 1900


@no_type_check
async def test_an_undoing_that_fails_leaves_the_record(db_driver, clear_database):
    from dataclasses import replace

    from pangloss_models.migrations import changes as c

    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    _, snapshot = declare(v1)
    initial = migrations_between(MigrationGraph(), snapshot)
    await backend.ensure_ready()
    state = await backend.apply(initial, EMPTY_SNAPSHOT)

    broken = replace(initial[0], changes=(c.RunCypher(query="NOT CYPHER"),))
    with pytest.raises(PanglossMigrationError):
        await backend.unapply([broken], state)
    assert [key[1] for key in await backend.applied()] == ["0001_initial"]


@no_type_check
async def test_a_squashed_migration_makes_what_the_originals_made(
    db_driver, clear_database
):
    from dataclasses import replace

    from pangloss_models.migrations.files import squash
    from pangloss_models.migrations.reverse import reverse_changes

    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            name: str
            nickname: str | None

        class Place(Entity):
            name: str

        return ns(Person=Person, Place=Place)

    _, first = declare(v1)
    initial = migrations_between(MigrationGraph(), first)
    graph = MigrationGraph.of(initial)
    models, second = declare(v2)
    later = migrations_between(graph, second)
    originals = [*initial, *later]
    graph = MigrationGraph.of(originals)
    squashed = squash(graph, "migapp", "0001", originals[-1].name[:4])
    assert len(squashed.replaces) == len(originals)

    # a new database: only the squashed migration, and the models work
    await backend.ensure_ready()
    state = await backend.apply([squashed], EMPTY_SNAPSHOT)
    assert state == data_view(second)
    place = await models.Place.Create(label="Paris", name="Paris").save()
    person = await models.Person.Create(label="Ann", name="Ann", nickname="A").save()
    assert (await models.Place.get(id=place.id)).name == "Paris"
    assert [key[1] for key in await backend.applied()] == [squashed.name]

    # ... that can be undone, and takes the records of the originals with it
    run(
        db_driver,
        "MERGE (:PGMigration {app: 'migapp', name: $name, status: 'applied'})",
        name=originals[0].name,
    )
    reversal = reverse_changes(squashed.changes, EMPTY_SNAPSHOT)
    undoing = replace(squashed, changes=tuple(reversal.changes))
    assert await backend.unapply([undoing], state) == data_view(EMPTY_SNAPSHOT)
    assert await backend.applied() == {}
    assert person.id


async def test_data_is_told_from_the_record_of_migrations(db_driver, clear_database):
    run(db_driver, "MATCH (n) DETACH DELETE n")  # (the tests' user is data too)
    await backend.ensure_ready()
    assert await backend.has_data() is False

    run(
        db_driver,
        "CREATE (:PGMigration {app: 'x', name: '0001_initial', status: 'applied'})",
    )
    assert await backend.has_data() is False  # (the record is not data)

    run(db_driver, "CREATE (:Person {id: 'a'})")
    assert await backend.has_data() is True


@no_type_check
async def test_a_migration_run_is_logged_with_its_lock_and_its_failure(
    db_driver, clear_database, caplog
):
    import logging

    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            name: str
            born: int

        return ns(Person=Person)

    caplog.set_level(logging.DEBUG, logger="pangloss")
    old_models, first_snapshot = declare(v1)
    initial = migrations_between(MigrationGraph(), first_snapshot)
    graph = MigrationGraph.of(initial)
    await backend.ensure_ready()
    await backend.lock("ann")
    state = await backend.apply(initial, EMPTY_SNAPSHOT)
    await backend.unlock()
    await old_models.Person.Create(label="Ann", name="Ann").save()

    _, second_snapshot = declare(v2)
    later = migrations_between(graph, second_snapshot)  # (no default given)
    with pytest.raises(PanglossMigrationAnswerNeeded):
        await backend.apply(later, state)

    lines = [
        (r.levelname, r.getMessage())
        for r in caplog.records
        if r.name == "pangloss.neo4j.migrations"
    ]
    messages = [message for _, message in lines]
    assert "Migration lock taken by 'ann'" in messages
    assert "Migration lock released" in messages
    assert "Migrate: 1 to apply" in messages
    assert any(m.startswith("Applying migapp.0001_initial") for m in messages)
    assert any(m.startswith("Applied migapp.0001_initial in") for m in messages)
    failures = [m for level, m in lines if level == "ERROR"]
    assert len(failures) == 1 and f"migapp.{later[0].name} failed" in failures[0]


@no_type_check
async def test_a_second_lock_is_an_error_in_the_log(db_driver, clear_database, caplog):
    await backend.ensure_ready()
    await backend.lock("ann")
    try:
        with pytest.raises(PanglossMigrationError):
            await backend.lock("bob")
    finally:
        await backend.unlock()
    assert any(
        r.levelname == "ERROR" and "lock is held" in r.getMessage()
        for r in caplog.records
    )
