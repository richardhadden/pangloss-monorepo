"""Changes written by hand, run against the database"""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations import changes as c
from pangloss_models.model_bases.entity import Entity
from pangloss_cypher.migrations import (
    apply_changes,
    apply_changes_in_batches,
    dry_run,
)

from .helpers import run
from .migration_support import declare
from pangloss_testing.under_test.database import current

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
        current(),
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
        current(),
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

    await apply_changes(current(), state, [c.RunPython(function=shout)])
    assert (await made.Person.get(id=saved.id)).name == "ANN"


@no_type_check
async def test_a_function_that_fails_changes_nothing(db_driver, clear_database):
    made, state = declare(models)
    saved = await made.Person.Create(label="Ann", name="Ann").save()

    with pytest.raises(RuntimeError, match="not today"):
        await apply_changes(
            current(),
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
            current(), state, [c.RunPython(function="no_such_module:f")]
        )
    with pytest.raises(PanglossMigrationError, match="Cannot find"):
        await apply_changes(
            current(), state, [c.RunPython(function=f"{__name__}:nothing")]
        )


@no_type_check
async def test_a_query_that_is_wrong_says_what_it_was(db_driver, clear_database):
    _, state = declare(models)
    with pytest.raises(PanglossMigrationError, match="NOT CYPHER"):
        await apply_changes(current(), state, [c.RunCypher(query="NOT CYPHER")])


@no_type_check
async def test_state_only_does_nothing_to_the_data(db_driver, clear_database):
    made, state = declare(models)
    await made.Person.Create(label="Ann", name="Ann").save()
    change = c.StateOnly(changes=(c.AlterModelLabels(model="Person", added=["Extra"]),))
    after = await apply_changes(current(), state, [change])
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

    reports, _ = await dry_run(current(), state, changes)
    assert [r.status for r in reports] == ["counted", "counted"]
    assert reports[0].counts["properties_set"] == 1
    assert (await made.Person.get(id=saved.id)).name == "Ann"  # (rolled back)

    await apply_changes_in_batches(current(), state, changes, size=10)
    read = await made.Person.get(id=saved.id)
    assert (read.name, read.born) == ("ANN", 5)


# --- a query is written for one backend -----------------------------------------------------------


def this_dialect() -> str:
    return current().dialect.name


def other_dialect() -> str:
    return "neo4j" if this_dialect() != "neo4j" else "memgraph"


@no_type_check
async def test_a_query_written_for_another_backend_is_refused(
    db_driver, clear_database
):
    made, state = declare(models)
    saved = await made.Person.Create(label="Ann", name="Ann").save()
    changes = [
        c.RunCypher(query="MATCH (n:Person) SET n.born = 5"),
        c.RunCypher(query="MATCH (n:Person) SET n.name = 'B'", dialect=other_dialect()),
    ]

    for apply in (
        lambda: apply_changes(current(), state, changes),
        lambda: apply_changes_in_batches(current(), state, changes, size=10),
        lambda: dry_run(current(), state, changes),
    ):
        with pytest.raises(
            PanglossMigrationError,
            match=f"this migration was written for .*; give a .* version with "
            f'`RunCypher\\(..., dialect="{this_dialect()}"\\)` next to it',
        ):
            await apply()
    read = await made.Person.get(id=saved.id)
    assert (read.name, read.born) == (
        "Ann",
        None,
    )  # (nothing was done: not the first change either)


@no_type_check
@pytest.mark.parametrize("order", ["this first", "other first"])
async def test_of_the_versions_next_to_each_other_the_one_for_this_backend_runs(
    clear_database, order
):
    made, state = declare(models)
    saved = await made.Person.Create(label="Ann", name="Ann").save()
    versions = [
        c.RunCypher(
            query="MATCH (n:Person) SET n.name = 'this'", dialect=this_dialect()
        ),
        c.RunCypher(
            query="MATCH (n:Person) SET n.name = 'other'", dialect=other_dialect()
        ),
    ]
    if order == "other first":
        versions.reverse()

    await apply_changes_in_batches(current(), state, versions, size=10)

    assert (await made.Person.get(id=saved.id)).name == "this"


@no_type_check
async def test_a_query_that_does_not_say_its_backend_runs_with_a_warning_once(
    clear_database, caplog
):
    made, state = declare(models)
    saved = await made.Person.Create(label="Ann", name="Ann").save()
    change = c.RunCypher(query="MATCH (n:Person) SET n.born = coalesce(n.born, 0) + 1")

    with caplog.at_level("WARNING", logger="pangloss.cypher.migrations"):
        await apply_changes(current(), state, [change])
        await apply_changes(current(), state, [change])

    assert (await made.Person.get(id=saved.id)).born == 2
    warned = [r for r in caplog.records if "does not say which backend" in r.message]
    assert len(warned) == 1


# --- a label written by hand is found as one written by the models --------------------------------


@no_type_check
@pytest.mark.parametrize("batches", [False, True])
@pytest.mark.parametrize("by", ["query", "function"])
async def test_a_label_set_by_hand_is_found_with_or_without_accents(
    clear_database, batches, by
):
    """(Memgraph's text index is on a folded copy of the label, which the models write beside it: a migration writes
    it again where a change by hand set a label)"""
    made, state = declare(models)
    await made.Person.Create(label="Ann", name="Ann").save()
    change = (
        c.RunCypher(query="MATCH (n:Person) SET n.label = 'Zürich'")
        if by == "query"
        else c.RunPython(function=rename_to_zurich, affects=["Person"])
    )

    if batches:
        await apply_changes_in_batches(current(), state, [change], size=10)
    else:
        await apply_changes(current(), state, [change])

    assert [
        p.label for p in (await made.Person.list(search_terms="zurich")).results
    ] == ["Zürich"]
    assert (await made.Person.list(search_terms="ann")).results == []


async def rename_to_zurich(tx, state):
    """(a function of a migration)"""
    await (await tx.run("MATCH (n:Person) SET n.label = 'Zürich'")).consume()
