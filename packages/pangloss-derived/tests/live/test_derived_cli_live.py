"""`pangloss derive`: explain, dry-run, rebuild, status and graph, run against the database. (The commands run their
own event loop, as `test_review_cli_live.py` explains: these tests are not async, and each loop has a driver of its
own)"""

import asyncio
import csv
import io
import json
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_testing.under_test.database import current
from typer.testing import CliRunner

from pangloss_derived.cli import cli

from test_derived_live import member, models


@pytest.fixture
def own_driver():
    from pangloss_testing.under_test import setup

    database = current()
    shared = database.driver

    async def connect():
        database.driver = (
            None  # (the shared one belongs to the other loop: not closed here)
        )
        driver = await database.ensure_driver()
        await driver.verify_connectivity()

    yield SimpleNamespace(connect=connect, disconnect=setup.disconnect)
    database.driver = shared


def derive(backend, *arguments):
    project = SimpleNamespace(
        require_database=lambda: backend, import_models=lambda: None
    )
    return CliRunner().invoke(cli, list(arguments), obj=project)


def seeded(backend, make):
    async def main():
        await backend.connect()
        try:
            return await make()
        finally:
            await backend.disconnect()

    return asyncio.run(main())


@no_type_check
def family(backend):
    """A and B, members of G in two factoids; C, a member of nothing"""
    Person, Group, MemberOf, Factoid, SameFamily = models()

    async def make():
        people = {n: await Person.Create(label=n).save() for n in ("A", "B", "C")}
        group = await Group.Create(label="G").save()
        await Factoid.Create(label="F1", statements=[member(people["A"], group)]).save()
        await Factoid.Create(label="F2", statements=[member(people["B"], group)]).save()
        return people, group

    return seeded(backend, make)


@no_type_check
def test_explain_says_each_rule_as_datalog_with_its_triggers_and_join_order(
    clear_database,
):
    models()
    project = SimpleNamespace(require_database=lambda: None, import_models=lambda: None)
    result = CliRunner().invoke(cli, ["explain"], obj=project)
    assert result.exit_code == 0, result.output
    assert "same_family  (SameFamily, hash " in result.output
    assert "Two people said to be members of one family" in result.output
    assert "types: family" in result.output
    assert "triggered by writes of: " in result.output and "Factoid" in result.output
    assert "symmetric: " in result.output
    assert "seeded at " in result.output
    # (the order of the joins, as MATCH clauses; the whole query only with --queries)
    assert "MATCH" in result.output and "RETURN" not in result.output

    with_queries = CliRunner().invoke(
        cli, ["explain", "same_family", "--queries"], obj=project
    )
    assert with_queries.exit_code == 0, with_queries.output
    assert "RETURN" in with_queries.output

    unknown = CliRunner().invoke(cli, ["explain", "no_such_rule"], obj=project)
    assert unknown.exit_code == 2
    assert "No rule no_such_rule. Known: same_family" in unknown.output


@no_type_check
def test_dry_run_counts_what_would_be_derived_and_writes_nothing(
    clear_database, db_driver, own_driver
):
    family(own_driver)

    result = derive(own_driver, "dry-run", "--top", "1")
    assert result.exit_code == 0, result.output
    assert "same_family" in result.output
    assert "1 facts, " in result.output
    # (the seed that gives most, one line of it)
    assert (
        len([line for line in result.output.splitlines() if line.startswith("    ")])
        == 1
    )

    from pangloss_testing.live import run

    assert run(db_driver, "MATCH (d:PGDerived) RETURN count(d) AS n") == [{"n": 0}]


@no_type_check
def test_rebuild_derives_what_the_data_gives_and_status_and_graph_show_it(
    clear_database, own_driver
):
    people, group = family(own_driver)

    before = derive(own_driver, "status")
    assert before.exit_code == 0, before.output
    assert "same_family: not built" in before.output

    rebuilt = derive(own_driver, "rebuild", "same_family")
    assert rebuilt.exit_code == 0, rebuilt.output
    name, counts = rebuilt.output.strip().split(": ", 1)
    assert name == "same_family" and isinstance(json.loads(counts), dict)

    after = derive(own_driver, "status")
    assert after.exit_code == 0, after.output
    assert "pending: " in after.output
    assert "same_family: not built" not in after.output
    assert "(changed since: to build again)" not in after.output

    shown = derive(own_driver, "graph", "family")
    assert shown.exit_code == 0, shown.output
    graph = json.loads(shown.output)
    assert graph["type"] == "family"
    (edge,) = graph["edges"]
    assert {edge["source"]["label"], edge["target"]["label"]} == {"A", "B"}
    assert (edge["class"], edge["justifications"], edge["plain"]) == (
        "SameFamily",
        1,
        True,
    )

    as_csv = derive(own_driver, "graph", "family", "--csv", "--plain-only")
    assert as_csv.exit_code == 0, as_csv.output
    header, *rows = list(csv.reader(io.StringIO(as_csv.output)))
    assert header == [
        "source",
        "source_label",
        "target",
        "target_label",
        "class",
        "justifications",
        "plain",
        "context",
    ]
    assert len(rows) == 1 and {rows[0][1], rows[0][3]} == {"A", "B"}

    # (a type there is not is said, with those there are: not a traceback)
    unknown = derive(own_driver, "graph", "no-such-type")
    assert unknown.exit_code == 2
    assert (
        "There is no type of rule called 'no-such-type'. Known: family"
        in unknown.output
    )


@no_type_check
def test_rebuild_is_refused_while_another_worker_holds_the_lease(
    clear_database, db_driver, own_driver
):
    import time

    from pangloss_derived.worker import KIND, LEASE_LABEL
    from pangloss_testing.live import run

    family(own_driver)
    run(
        db_driver,
        f"MERGE (w:{LEASE_LABEL} {{kind: $kind}}) SET w.holder = 'a server', w.until = $until",
        kind=KIND,
        until=time.time() + 60,
    )
    refused = derive(own_driver, "rebuild")
    assert refused.exit_code == 1
    assert "Another worker is working" in refused.output
    assert run(db_driver, "MATCH (d:PGDerived) RETURN count(d) AS n") == [{"n": 0}]
