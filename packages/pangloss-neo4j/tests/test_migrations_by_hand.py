"""Changes written by hand, run against the database"""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations import changes as c
from pangloss_models.model_bases.entity import Entity
from pangloss_neo4j.databases.neo4j.database import Database
from pangloss_neo4j.databases.neo4j.migrations import (
    apply_changes,
    apply_changes_in_batches,
    dry_run,
)

from .helpers import run
from .migration_support import declare

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models():
    class Person(Entity):
        name: str
        born: int | None

    return ns(Person=Person)


async def shout(tx, state):
    """(a function of a migration)"""
    assert "Person" in state["models"]
    result = await tx.run("MATCH (n:Person) SET n.name = toUpper(n.name)")
    await result.consume()


def sync_function(tx, state):
    tx.run("MATCH (n:Person) SET n.born = 1")


def fails(tx, state):
    raise RuntimeError("not today")


@no_type_check
async def test_a_query_is_run_with_its_parameters(db_driver, clear_database):
    made, state = declare(models)
    saved = await made.Person.Create(label="Ann", name="Ann").save()

    await apply_changes(
        Database.default,
        state,
        [
            c.RunCypher(
                query="MATCH (n:Person) SET n.born = $year", parameters={"year": 1900}
            )
        ],
    )
    assert (await made.Person.get(id=saved.id)).born == 1900


@no_type_check
async def test_a_query_may_have_a_parameter_called_query(db_driver, clear_database):
    made, state = declare(models)
    saved = await made.Person.Create(label="Ann", name="Ann").save()
    await apply_changes(
        Database.default,
        state,
        [
            c.RunCypher(
                query="MATCH (n:Person) SET n.name = $query", parameters={"query": "Q"}
            )
        ],
    )
    assert (await made.Person.get(id=saved.id)).name == "Q"


@no_type_check
async def test_a_function_is_run_in_the_transaction(db_driver, clear_database):
    made, state = declare(models)
    saved = await made.Person.Create(label="Ann", name="Ann").save()

    await apply_changes(Database.default, state, [c.RunPython(function=shout)])
    assert (await made.Person.get(id=saved.id)).name == "ANN"


@no_type_check
async def test_a_function_that_fails_changes_nothing(db_driver, clear_database):
    made, state = declare(models)
    saved = await made.Person.Create(label="Ann", name="Ann").save()

    with pytest.raises(RuntimeError, match="not today"):
        await apply_changes(
            Database.default,
            state,
            [
                c.RunCypher(query="MATCH (n:Person) SET n.name = 'changed'"),
                c.RunPython(function=fails),
            ],
        )
    assert (await made.Person.get(id=saved.id)).name == "Ann"


@no_type_check
async def test_a_function_that_is_not_there_is_an_error(db_driver, clear_database):
    _, state = declare(models)
    with pytest.raises(PanglossMigrationError, match="Cannot find"):
        await apply_changes(
            Database.default, state, [c.RunPython(function="no_such_module:f")]
        )
    with pytest.raises(PanglossMigrationError, match="Cannot find"):
        await apply_changes(
            Database.default, state, [c.RunPython(function=f"{__name__}:nothing")]
        )


@no_type_check
async def test_a_query_that_is_wrong_says_what_it_was(db_driver, clear_database):
    _, state = declare(models)
    with pytest.raises(PanglossMigrationError, match="NOT CYPHER"):
        await apply_changes(Database.default, state, [c.RunCypher(query="NOT CYPHER")])


@no_type_check
async def test_state_only_does_nothing_to_the_data(db_driver, clear_database):
    made, state = declare(models)
    await made.Person.Create(label="Ann", name="Ann").save()
    change = c.StateOnly(changes=(c.AlterModelLabels(model="Person", added=["Extra"]),))
    after = await apply_changes(Database.default, state, [change])
    assert after["models"]["Person"]["labels"][-1] == "Extra"
    assert run(db_driver, "MATCH (n:Extra) RETURN count(n) AS c") == [{"c": 0}]


@no_type_check
async def test_by_hand_in_a_dry_run_and_in_batches(db_driver, clear_database):
    made, state = declare(models)
    saved = await made.Person.Create(label="Ann", name="Ann").save()
    changes = [
        c.RunCypher(query="MATCH (n:Person) SET n.born = 5"),
        c.RunPython(function=shout),
    ]

    reports, _ = await dry_run(Database.default, state, changes)
    assert [r.status for r in reports] == ["counted", "counted"]
    assert reports[0].counts["properties_set"] == 1
    assert (await made.Person.get(id=saved.id)).name == "Ann"  # (rolled back)

    await apply_changes_in_batches(Database.default, state, changes, size=10)
    read = await made.Person.get(id=saved.id)
    assert (read.name, read.born) == ("ANN", 5)
