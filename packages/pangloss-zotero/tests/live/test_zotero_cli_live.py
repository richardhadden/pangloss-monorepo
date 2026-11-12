"""`pangloss zotero sync` and `status`, run against the database (on the backend under test) and a Zotero that is a dict
(`zotero_support.FakeZotero`)"""

from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_testing.live import run, run_command

from pangloss_zotero.cli import cli
from test_zotero_live_store import models
from zotero_support import LIBRARY, FakeZotero, make_item


@pytest.fixture
def zotero(monkeypatch):
    """A Zotero with two items, a book and an article, that the commands' clients talk to"""
    fake = FakeZotero()
    fake.put(make_item("BOOK1", title="An atlas"))
    fake.put(make_item("ART1", item_type="journalArticle", title="An article"))
    monkeypatch.setattr(
        "pangloss_zotero.watch.ZoteroClient", lambda *args, **kwargs: fake.client()
    )
    monkeypatch.setattr(
        "pangloss_zotero.client.ZoteroClient", lambda *args, **kwargs: fake.client()
    )
    return fake


def line_of(output: str, start: str) -> str:
    """(the line that starts so: a slow query's warning may be logged to the output before it)"""
    return next(line for line in output.splitlines() if line.startswith(start))


def zotero_command(backend, settings, *arguments):
    return run_command(cli, backend, *arguments, settings=settings)


@no_type_check
def test_status_and_sync_say_how_a_library_stands(
    live_db, command_backend, db_driver, zotero
):
    models()
    settings = live_db

    before = zotero_command(command_backend, settings, "status")
    assert before.exit_code == 0, before.output
    assert line_of(before.output, LIBRARY) == f"{LIBRARY}: version 0, never synced"
    assert "book -> Atlas" in line_of(before.output, "Item types: ")
    assert "Anything else is written as ZoteroObject" in before.output.splitlines()

    # (a dry run says what it would do, and writes nothing)
    dry = zotero_command(command_backend, settings, "sync", "--dry-run")
    assert dry.exit_code == 0, dry.output
    assert line_of(dry.output, "(dry run)").startswith(
        f"(dry run) {LIBRARY}: 2 created, 0 updated, 0 unchanged"
    )
    assert run(db_driver, "MATCH (n:ZoteroBacked) RETURN count(n) AS n") == [{"n": 0}]

    synced = zotero_command(command_backend, settings, "sync", "--library", LIBRARY)
    assert synced.exit_code == 0, synced.output
    assert line_of(synced.output, LIBRARY).startswith(
        f"{LIBRARY}: 2 created, 0 updated, 0 unchanged"
    )
    assert run(db_driver, "MATCH (n:ZoteroBacked) RETURN count(n) AS n") == [{"n": 2}]

    after = zotero_command(command_backend, settings, "status", "--remote")
    assert after.exit_code == 0, after.output
    assert line_of(after.output, LIBRARY).startswith(
        f"{LIBRARY}: version 2 of 2 (up to date), synced "
    )

    zotero.put(make_item("BOOK2", title="Another atlas"))
    behind = zotero_command(command_backend, settings, "status", "--remote")
    assert "version 2 of 3 (behind)" in behind.output

    again = zotero_command(command_backend, settings, "sync")
    assert line_of(again.output, LIBRARY).startswith(
        f"{LIBRARY}: 1 created, 0 updated, 0 unchanged"
    )


@no_type_check
def test_a_sync_with_no_library_or_that_zotero_refuses_says_so(
    live_db, command_backend, zotero
):
    models()
    nothing = SimpleNamespace(ZOTERO_API_KEY="key", ZOTERO_LIBRARIES=[])
    refused = zotero_command(command_backend, nothing, "sync")
    assert refused.exit_code == 1
    assert "There is no library to sync: set ZOTERO_LIBRARIES" in refused.output

    # (Zotero going away part way: the library's errors are said, and the command fails)
    zotero.fail_from_request = 1
    failed = zotero_command(command_backend, live_db, "sync")
    assert failed.exit_code == 1, failed.output
