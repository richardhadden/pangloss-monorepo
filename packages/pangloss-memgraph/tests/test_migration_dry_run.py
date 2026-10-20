"""A dry run says what a migration would do, and does nothing; `check_data` reads everything"""

from enum import Enum
from types import SimpleNamespace as ns
from typing import Annotated, no_type_check

import pytest
from pangloss_memgraph.databases.memgraph import migration_backend as backend
from pangloss_models.migrations.check import check_data
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, MigrationGraph
from pangloss_models.migrations.planner import plan
from pangloss_models.migrations.questions import with_answer
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation

from .helpers import run
from .migration_support import declare

pytestmark = pytest.mark.asyncio(loop_scope="session")

APPS = ["migapp"]

DryRunColour = Enum("MigrationDryRunColour", {"RED": "red"})


def in_app(snapshot: dict) -> dict:
    for model in snapshot["models"].values():
        model["module"] = "migapp.models"
    return snapshot


def migrations_between(graph, new, answer=None):
    result = plan(graph, in_app(new), APPS, answer=answer)
    assert result.is_final
    return result.migrations


def answering(**by_kind):
    def answer(changes, old):
        return [with_answer(ch, *by_kind[ch.kind]) if ch.kind in by_kind else ch for ch in changes]

    return answer


@no_type_check
async def test_a_dry_run_counts_what_a_migration_would_do_and_does_nothing(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            name: str
            born: int

        return ns(Person=Person)

    old_models, first = declare(v1)
    initial = migrations_between(MigrationGraph(), first)
    graph = MigrationGraph.of(initial)
    await backend.ensure_ready()
    state = await backend.apply(initial, EMPTY_SNAPSHOT)
    for name in ("Ann", "Bob", "Cat"):
        await old_models.Person.Create(label=name, name=name).save()
    _, second = declare(v2)
    later = migrations_between(graph, second, answer=answering(AddField=("default", 1900)))

    (report,) = await backend.dry_run(later, state)
    (change,) = report.changes
    assert change.status == "counted"
    assert change.counts["properties_set"] == 3
    assert "3 properties set" in change.summary()
    # nothing was done
    assert run(db_driver, "MATCH (p:Person) WHERE p.born IS NOT NULL RETURN count(p) AS n") == [{"n": 0}]
    assert await backend.applied() and ("migapp", later[0].name) not in await backend.applied()


@no_type_check
async def test_a_dry_run_counts_the_nodes_a_wrapper_makes(db_driver, clear_database):
    def v1():
        class Person(Entity):
            pass

        class Statement(Document):
            person: Person

        return ns(Person=Person, Statement=Statement)

    def v2():
        class IdentifiedAs[T](ReifiedRelation[T]):
            certainty: int

        class Person(Entity):
            pass

        class Statement(Document):
            person: IdentifiedAs[Person]

        return ns(Person=Person, Statement=Statement)

    old_models, first = declare(v1)
    initial = migrations_between(MigrationGraph(), first)
    graph = MigrationGraph.of(initial)
    await backend.ensure_ready()
    state = await backend.apply(initial, EMPTY_SNAPSHOT)
    person = await old_models.Person.Create(label="Ann").save()
    for label in ("A", "B"):
        await old_models.Statement.Create(label=label, person={"type": "Person", "id": person.id}).save()
    _, second = declare(v2)
    later = migrations_between(graph, second, answer=answering(WrapRelation=("defaults.certainty", 3)))

    (report,) = await backend.dry_run(later, state)
    wrap = next(r for r in report.changes if r.change.kind == "WrapRelation")
    assert wrap.status == "counted"
    assert wrap.counts["nodes_created"] == 2
    assert wrap.counts["relationships_deleted"] >= 4
    assert run(db_driver, "MATCH (r:IdentifiedAs) RETURN count(r) AS n") == [{"n": 0}]
    assert run(db_driver, "MATCH (:Statement)-[e:person]->(:Person) RETURN count(e) AS n") == [{"n": 2}]


@no_type_check
async def test_a_dry_run_finds_what_would_fail(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            name: str
            born: int
            nickname: str | None

        return ns(Person=Person)

    old_models, first = declare(v1)
    initial = migrations_between(MigrationGraph(), first)
    graph = MigrationGraph.of(initial)
    await backend.ensure_ready()
    state = await backend.apply(initial, EMPTY_SNAPSHOT)
    await old_models.Person.Create(label="Ann", name="Ann").save()
    _, second = declare(v2)
    later = migrations_between(graph, second)  # (the value for `born` is not given)

    (report,) = await backend.dry_run(later, state)
    assert report.failed
    failed = [r for r in report.changes if r.status == "error"]
    assert "value for the nodes that exist" in failed[0].message
    assert "WOULD FAIL" in failed[0].summary()
    # (the rest are not tried: the transaction cannot go on after a failure)
    assert [r.status for r in report.changes].count("error") == 1
    assert report.changes[-1].status in ("error", "not tried")


@no_type_check
async def test_changes_to_enums_are_listed_and_not_tried(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            name: str
            colour: DryRunColour | None

        return ns(Person=Person)

    _, first = declare(v1)
    initial = migrations_between(MigrationGraph(), first)
    graph = MigrationGraph.of(initial)
    await backend.ensure_ready()
    state = await backend.apply(initial, EMPTY_SNAPSHOT)
    _, second = declare(v2)
    later = migrations_between(graph, second)

    (report,) = await backend.dry_run(later, state)
    assert [r.status for r in report.changes][0] == "enum"
    assert "not tried" in report.changes[0].summary()
    rows = run(db_driver, "SHOW ENUMS")
    assert "MigrationDryRunColour" not in {row["Enum Name"] for row in rows}


@no_type_check
async def test_check_data_reads_everything_the_models_can_and_reports_the_rest(db_driver, clear_database):
    def v1():
        class Person(Entity):
            name: str

        class Statement(Document):
            text: str

        return ns(Person=Person, Statement=Statement)

    def v2():
        class Person(Entity):
            name: str
            born: int

        class Statement(Document):
            text: str

        return ns(Person=Person, Statement=Statement)

    old_models, first = declare(v1)
    initial = migrations_between(MigrationGraph(), first)
    graph = MigrationGraph.of(initial)
    await backend.ensure_ready()
    state = await backend.apply(initial, EMPTY_SNAPSHOT)
    ann = await old_models.Person.Create(label="Ann", name="Ann").save()
    await old_models.Person.Create(label="Bob", name="Bob").save()
    await old_models.Statement.Create(label="S", text="t").save()

    check = await check_data()
    assert check.ok and check.checked == 3

    # the models change, and the data does not: what cannot be read is reported
    _, second = declare(v2)
    check = await check_data()
    assert check.checked == 3
    assert sorted(p.label for p in check.problems) == ["Ann", "Bob"]
    assert all(p.model == "Person" and any("born" in e for e in p.errors) for p in check.problems)
    assert "Person" in str(check.problems[0])

    # ... until it is migrated
    later = migrations_between(graph, second, answer=answering(AddField=("default", 1900)))
    await backend.apply(later, state)
    check = await check_data()
    assert check.ok

    # only some models, and only some of each
    assert (await check_data(types=["Statement"])).checked == 1
    assert (await check_data(limit=1)).checked == 2  # (one of each of the two models)

    # what is deleted is not read
    await old_models.Person.delete(id=ann.id)
    assert (await check_data()).checked == 2
