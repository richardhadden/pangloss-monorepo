"""The `pangloss review` commands, run against Neo4j.

The commands run their own event loop (`asyncio.run`), so these tests are not async themselves; the driver the
other tests share belongs to their loop, so each loop here gets a driver of its own, and the shared one is put back.
"""

import asyncio
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_neo4j.databases.neo4j.database import Database
from pangloss_review.cli import cli
from pangloss_review.status import ReviewStatus
from typer.testing import CliRunner

from .test_review_live import make_user, models


@pytest.fixture
def own_driver():
    """A backend like the real one, but with a new driver for each event loop"""
    from pangloss_neo4j.databases.neo4j import setup

    database = Database.default
    shared = database.driver

    async def connect():
        await database._initialise_driver()
        await database.driver.verify_connectivity()

    backend = SimpleNamespace(connect=connect, disconnect=setup.disconnect)
    yield backend
    database.driver = shared


def run(backend, *arguments):
    project = SimpleNamespace(
        require_database=lambda: backend, import_models=lambda: None
    )
    return CliRunner().invoke(cli, list(arguments), obj=project)


def seed(backend, make):
    async def main():
        await backend.connect()
        try:
            return await make()
        finally:
            await backend.disconnect()

    return asyncio.run(main())


@no_type_check
def test_the_commands_show_the_queue_check_and_publish(
    clear_database, db_driver, own_driver
):
    _, Letter, *_ = models()
    make_user(db_driver, "bob")

    async def make():
        letter = await Letter.Create(label="First letter", title="t", notes=[]).save()
        await Letter.Create(label="Second letter", title="t", notes=[]).save()
        return letter.id

    letter_id = seed(own_driver, make)

    result = run(own_driver, "queue")
    assert result.exit_code == 0, result.output
    assert "First letter" in result.output and "Second letter" in result.output
    assert "2 in all" in result.output

    result = run(
        own_driver,
        "set",
        str(letter_id),
        "errors_found",
        "-u",
        "bob",
        "-c",
        "The date is wrong",
    )
    assert result.exit_code == 0, result.output
    assert "errors_found" in result.output and "published: False" in result.output

    result = run(own_driver, "show", str(letter_id))
    assert result.exit_code == 0, result.output
    assert "The date is wrong" in result.output and "bob" in result.output

    result = run(own_driver, "queue", "--status", "errors_found")
    assert "First letter" in result.output and "Second letter" not in result.output

    result = run(own_driver, "set", str(letter_id), "checked", "-u", "bob")
    assert result.exit_code == 0, result.output
    assert f"{ReviewStatus.CHECKED}" in result.output
    assert "published: True" in result.output

    # (a document that is published is not in the queue any more)
    result = run(own_driver, "queue")
    assert "First letter" not in result.output and "1 in all" in result.output


@no_type_check
def test_a_command_says_what_went_wrong(clear_database, db_driver, own_driver):
    _, _, Memo, _ = models()

    async def make():
        return (await Memo.Create(label="M", title="t").save()).id

    memo_id = seed(own_driver, make)

    # (a class that is not reviewed)
    result = run(own_driver, "set", str(memo_id), "checked", "-u", "bob")
    assert result.exit_code == 1
    assert result.output.strip() != ""

    # (nothing with that id)
    result = run(own_driver, "show", "7bd4b1c2-0c3e-4a56-9a39-6e0d6d1d9c11")
    assert result.exit_code == 1
