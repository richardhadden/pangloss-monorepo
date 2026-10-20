"""A migration made in batches: the same result, and a run that stops goes on from where it was"""

import dataclasses
from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_memgraph.databases.memgraph import migration_backend as backend
from pangloss_memgraph.databases.memgraph.migrations import runner
from pangloss_models.exceptions import PanglossMigrationAnswerNeeded
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, MigrationGraph
from pangloss_models.migrations.history import pending
from pangloss_models.migrations.planner import plan
from pangloss_models.migrations.questions import with_answer
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation

from .helpers import run
from .migration_support import declare
from .test_migrations_relations import signature

pytestmark = pytest.mark.asyncio(loop_scope="session")

APPS = ["migapp"]


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


class Stopper:
    """Makes the n-th call of a function fail (and counts the calls)"""

    def __init__(self, monkeypatch, module, name, fail_on=None):
        self.calls = 0
        self.fail_on = fail_on
        original = getattr(module, name)

        async def wrapped(*args, **kwargs):
            self.calls += 1
            if self.fail_on and self.calls == self.fail_on:
                raise RuntimeError("stopped part way")
            return await original(*args, **kwargs)

        monkeypatch.setattr(module, name, wrapped)


def person_versions():
    def v1():
        class Person(Entity):
            name: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            name: str
            born: int

        return ns(Person=Person)

    return v1, v2


async def start_with_people(count: int):
    v1, v2 = person_versions()
    old_models, first = declare(v1)
    initial = migrations_between(MigrationGraph(), first)
    graph = MigrationGraph.of(initial)
    await backend.ensure_ready()
    state = await backend.apply(initial, EMPTY_SNAPSHOT)
    people = [await old_models.Person.Create(label=f"P{i}", name=f"P{i}").save() for i in range(count)]
    new_models, second = declare(v2)
    later = migrations_between(graph, second, answer=answering(AddField=("default", 1900)))
    return ns(models=new_models, state=state, later=later, graph=graph, people=people)


@no_type_check
async def test_a_batched_migration_does_what_a_whole_one_does(db_driver, clear_database, monkeypatch):
    world = await start_with_people(10)
    stopper = Stopper(monkeypatch, runner, "apply_window")

    await backend.apply(world.later, world.state, batch_size=3)

    assert stopper.calls == 4  # (3 + 3 + 3 + 1)
    assert run(db_driver, "MATCH (p:Person) WHERE p.born = 1900 RETURN count(p) AS n") == [{"n": 10}]
    record = (await backend.applied())[("migapp", world.later[0].name)]
    assert record["status"] == "applied"
    assert record.get("cursor") is None
    assert pending(MigrationGraph.of([*world.graph.migrations.values(), *world.later]), await backend.applied()) == []


@no_type_check
async def test_a_migration_that_stops_goes_on_from_where_it_was(db_driver, clear_database, monkeypatch):
    world = await start_with_people(10)
    stopper = Stopper(monkeypatch, runner, "apply_window", fail_on=3)

    with pytest.raises(RuntimeError, match="stopped part way"):
        await backend.apply(world.later, world.state, batch_size=3)

    # two batches were made, and kept: the six first (by id)
    done = run(db_driver, "MATCH (p:Person) WHERE p.born IS NOT NULL RETURN p.id AS id ORDER BY id")
    everyone = run(db_driver, "MATCH (p:Person) RETURN p.id AS id ORDER BY id")
    assert [row["id"] for row in done] == [row["id"] for row in everyone][:6]
    record = (await backend.applied())[("migapp", world.later[0].name)]
    assert record["status"] == "failed"
    assert "stopped part way" in record["error"]
    assert '"after": "%s"' % everyone[5]["id"] in record["cursor"]

    # the next run does the rest, and only the rest
    stopper.fail_on = None
    stopper.calls = 0
    notes = []
    await backend.apply(world.later, world.state, batch_size=3, progress=lambda m, what: notes.append(what))
    assert stopper.calls == 2  # (3 + 1: the four that were left)
    assert any("going on from" in note for note in notes)
    assert run(db_driver, "MATCH (p:Person) WHERE p.born = 1900 RETURN count(p) AS n") == [{"n": 10}]
    assert (await backend.applied())[("migapp", world.later[0].name)]["status"] == "applied"


@no_type_check
async def test_what_cannot_be_converted_is_found_before_anything_is_changed(
    db_driver, clear_database, monkeypatch
):
    def v1():
        class Person(Entity):
            age: str

        return ns(Person=Person)

    def v2():
        class Person(Entity):
            age: int

        return ns(Person=Person)

    old_models, first = declare(v1)
    initial = migrations_between(MigrationGraph(), first)
    graph = MigrationGraph.of(initial)
    await backend.ensure_ready()
    state = await backend.apply(initial, EMPTY_SNAPSHOT)
    for i in range(9):
        await old_models.Person.Create(label=f"P{i}", age=str(i)).save()
    await old_models.Person.Create(label="Bad", age="old").save()  # (the last by id, or not: any)
    _, second = declare(v2)
    later = migrations_between(graph, second)

    with pytest.raises(PanglossMigrationAnswerNeeded, match="cannot be converted"):
        await backend.apply(later, state, batch_size=3)
    ages = run(db_driver, "MATCH (p:Person) RETURN DISTINCT valueType(p.age) AS kind")
    assert [row["kind"] for row in ages] == ["STRING"]  # (none was converted before it was found)

    # with an answer, the same, in batches
    answered = migrations_between(graph, second, answer=answering(AlterLiteralType=("on_failure", "null")))
    await backend.apply(answered, state, batch_size=3)
    assert run(db_driver, "MATCH (p:Person) WHERE p.age IS NULL RETURN count(p) AS n") == [{"n": 1}]
    assert run(db_driver, "MATCH (p:Person) WHERE p.age IS NOT NULL RETURN max(p.age) AS n") == [{"n": 8}]


def wrap_versions():
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

    return v1, v2


@no_type_check
async def test_wrapping_relations_in_batches_wraps_each_once_even_when_stopped(
    db_driver, clear_database, monkeypatch
):
    v1, v2 = wrap_versions()
    old_models, first = declare(v1)
    initial = migrations_between(MigrationGraph(), first)
    graph = MigrationGraph.of(initial)
    await backend.ensure_ready()
    state = await backend.apply(initial, EMPTY_SNAPSHOT)
    person = await old_models.Person.Create(label="Ann").save()
    statements = [
        await old_models.Statement.Create(label=f"S{i}", person={"type": "Person", "id": person.id}).save()
        for i in range(10)
    ]
    new_models, second = declare(v2)
    later = migrations_between(graph, second, answer=answering(WrapRelation=("defaults.certainty", 3)))

    stopper = Stopper(monkeypatch, runner, "wrap_reified", fail_on=2)
    with pytest.raises(RuntimeError):
        await backend.apply(later, state, batch_size=3)
    assert run(db_driver, "MATCH (r:IdentifiedAs) RETURN count(r) AS n") == [{"n": 3}]  # (one batch)

    stopper.fail_on = None
    await backend.apply(later, state, batch_size=3)
    assert run(db_driver, "MATCH (r:IdentifiedAs) RETURN count(r) AS n") == [{"n": 10}]
    assert run(db_driver, "MATCH (:Statement)-[e:person]->(:Person) RETURN count(e) AS n") == [{"n": 0}]

    # and each is what the new models write
    native = await new_models.Statement.Create(
        label="S0",
        person={"type": "IdentifiedAs", "certainty": 3, "target": [{"type": "Person", "id": person.id}]},
    ).save()
    assert signature(db_driver, statements[0].id) == signature(db_driver, native.id)


@no_type_check
async def test_a_migration_that_is_not_atomic_is_made_in_batches(db_driver, clear_database, monkeypatch):
    world = await start_with_people(5)
    monkeypatch.setattr(backend, "DEFAULT_BATCH_SIZE", 2)
    stopper = Stopper(monkeypatch, runner, "apply_window")
    not_atomic = [dataclasses.replace(m, atomic=False) for m in world.later]

    await backend.apply(not_atomic, world.state)
    assert stopper.calls == 3  # (2 + 2 + 1)
    assert run(db_driver, "MATCH (p:Person) WHERE p.born = 1900 RETURN count(p) AS n") == [{"n": 5}]

    # one that is atomic is made at once, whatever the default
    world = await start_with_people(5)
    stopper.calls = 0
    await backend.apply(world.later, world.state)
    assert stopper.calls == 0
