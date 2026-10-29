import logging

import neo4j
import pytest
from pangloss_neo4j.databases.neo4j import database as database_module
from pangloss_neo4j.databases.neo4j.database import (
    MAX_LOGGED_QUERY,
    LoggedTransaction,
    timed,
)


class FakeTransaction:
    def __init__(self):
        self.calls = []
        self.other = "kept"

    async def run(self, query, parameters=None, **kwargs):
        self.calls.append((query, parameters, kwargs))
        return "result"


class FakeSettings:
    SLOW_QUERY_MS = 500


class FakeDatabase:
    settings = FakeSettings()


@pytest.mark.asyncio
async def test_a_logged_transaction_logs_names_not_values_and_passes_everything_on(
    caplog,
):
    caplog.set_level(logging.DEBUG, logger="pangloss")
    tx = FakeTransaction()
    logged = LoggedTransaction(tx)

    result = await logged.run(
        "MATCH (n)\n   WHERE n.name = $name RETURN n",
        {"name": "Secret Person"},
        limit=3,
    )

    assert result == "result"
    assert tx.calls == [
        (
            "MATCH (n)\n   WHERE n.name = $name RETURN n",
            {"name": "Secret Person"},
            {"limit": 3},
        )
    ]
    assert logged.other == "kept"
    (line,) = [r.getMessage() for r in caplog.records]
    assert "MATCH (n) WHERE n.name = $name RETURN n" in line
    assert "params: limit, name" in line
    assert "Secret Person" not in caplog.text


@pytest.mark.asyncio
async def test_a_long_query_is_cut(caplog):
    caplog.set_level(logging.DEBUG, logger="pangloss")
    logged = LoggedTransaction(FakeTransaction())
    await logged.run("RETURN 1 " + "x" * (MAX_LOGGED_QUERY * 2))
    (line,) = [r.getMessage() for r in caplog.records]
    assert line.count("x") < MAX_LOGGED_QUERY and "..." in line


@pytest.mark.asyncio
async def test_losing_the_database_is_an_error_and_is_raised_again(caplog):
    caplog.set_level(logging.DEBUG, logger="pangloss")

    async def run():
        raise neo4j.exceptions.ServiceUnavailable("connection refused")

    async def work(tx):
        pass

    with pytest.raises(neo4j.exceptions.ServiceUnavailable):
        await timed(FakeDatabase(), "read", work, run)
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1
    assert "could not be reached" in errors[0] and "work" in errors[0]


@pytest.mark.asyncio
async def test_a_transaction_is_timed_and_a_slow_one_is_a_warning(caplog):
    caplog.set_level(logging.DEBUG, logger="pangloss")

    async def run():
        return 1

    async def work(tx):
        pass

    database = FakeDatabase()
    assert await timed(database, "read", work, run) == 1
    assert caplog.records[-1].levelname == "DEBUG"

    FakeSettings.SLOW_QUERY_MS = -1
    try:
        await timed(database, "write", work, run)
    finally:
        FakeSettings.SLOW_QUERY_MS = 500
    assert caplog.records[-1].levelname == "WARNING"
    assert "(slow)" in caplog.records[-1].getMessage()
    assert database_module.logger.name == "pangloss.neo4j.transactions"
