"""`pangloss memgraph info`, and the `setup` module the `pangloss` command uses, against Memgraph.

Each test gives the command a `Database` of its own: the command connects and disconnects the
default, which the other tests share."""

import asyncio

from pangloss_memgraph import cli as memgraph_cli
from pangloss_memgraph.databases.memgraph import setup
from pangloss_memgraph.databases.memgraph.database import Database
from typer.testing import CliRunner

runner = CliRunner()


def invoke(*args: str):
    # (as `pangloss` adds it: a Typer of one command takes no command name on its own)
    import typer

    app = typer.Typer()
    app.add_typer(memgraph_cli.cli, name="memgraph")
    return runner.invoke(app, ["memgraph", *args])


def own_database(monkeypatch, **database_settings) -> Database:
    shared = Database.default
    settings = shared.settings.model_copy(
        update={
            "DATABASE": shared.settings.DATABASE.model_copy(update=database_settings)
        }
    )
    database = object.__new__(
        Database
    )  # (the constructor would make it the default for good)
    database.settings = settings
    monkeypatch.setattr(Database, "default", database)
    return database


def test_info_shows_the_indexes_and_constraints(monkeypatch):
    database = own_database(monkeypatch)

    result = invoke("info")

    assert result.exit_code == 0, result.output
    assert "Indexes" in result.output and "Unique constraints" in result.output
    assert ":PGIndexableNode(id)" in result.output
    assert "label+property: :PGAccessToken(token_hash)" in result.output
    assert "unique: :PGUser(username)" in result.output
    # (and it closed its connection)
    assert database.driver._closed


def test_info_says_when_the_database_cannot_be_read(monkeypatch):
    own_database(monkeypatch, DB_URL="bolt://localhost:1")

    result = invoke("info")

    assert result.exit_code == 1
    assert "Cannot read the database" in result.output


def test_setup_connects_sets_up_and_disconnects(monkeypatch):
    database = own_database(monkeypatch)

    async def run():
        await setup.connect()
        try:
            return await setup.setup_database()
        finally:
            await setup.disconnect()

    lines = asyncio.run(run())

    # (the session's set-up made everything already: it is safe to repeat)
    assert lines and all(line.startswith("already present: ") for line in lines)
    assert any("PGRevokedSession(jti)" in line for line in lines)
    assert database.driver._closed

    # (connecting again opens a new driver; disconnecting twice is harmless. A driver belongs to
    # the event loop it was made in, as in a command, which runs in one)
    async def again():
        await setup.connect()
        assert not database.driver._closed
        await setup.disconnect()
        await setup.disconnect()

    asyncio.run(again())


def test_create_database_makes_the_default_only_if_there_is_none(monkeypatch):
    database = own_database(monkeypatch)
    setup.create_database(database.settings)
    assert Database.default is database

    monkeypatch.delattr(Database, "default")
    setup.create_database(database.settings)
    assert (
        Database.default is not database
        and Database.default.settings is database.settings
    )
