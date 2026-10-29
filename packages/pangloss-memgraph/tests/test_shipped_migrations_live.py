"""The migrations that library packages ship, applied to Memgraph: the indexes and keys they describe are made"""

import pytest
from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.migrations import apply_changes
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, graph_of

pytestmark = pytest.mark.asyncio(loop_scope="session")

APPS = ["pangloss_dates", "pangloss_calendar", "pangloss_zotero", "pangloss_memgraph"]


def show(db_driver, what: str) -> list[dict]:
    with db_driver.session() as session:  # (not in a transaction)
        return session.run(what).data()


def has_index(db_driver, entry) -> bool:
    rows = show(db_driver, "SHOW INDEX INFO")
    if entry["kind"] == "text":
        return any(
            r["index type"] == f"label_text (name: {entry['name']})" for r in rows
        )
    if entry["kind"] == "label":
        return any(
            r["index type"] == "label" and r["label"] == entry["label"] for r in rows
        )
    return any(
        r["index type"] == "label+property"
        and r["label"] == entry["label"]
        and r["property"] == entry["properties"]
        for r in rows
    )


def has_constraint(db_driver, entry) -> bool:
    return any(
        r["constraint type"] == "unique"
        and r["label"] == entry["label"]
        and sorted(r["properties"]) == sorted(entry["properties"])
        for r in show(db_driver, "SHOW CONSTRAINT INFO")
    )


@pytest.mark.parametrize("app", APPS)
async def test_the_migrations_of_a_package_make_what_they_describe(db_driver, app):
    migrations = [m for m in graph_of(APPS).order() if m.app == app]
    assert migrations
    changes = [change for m in migrations for change in m.changes]
    indexes = [ch.index for ch in changes if isinstance(ch, c.AddIndex)]
    keys = [ch.constraint for ch in changes if isinstance(ch, c.AddConstraint)]
    assert indexes

    # (taken away first, so that what is found was made by the migrations)
    state = await apply_changes(
        Database.default,
        EMPTY_SNAPSHOT,
        [c.AddIndex(index=i) for i in indexes]
        + [c.AddConstraint(constraint=k) for k in keys],
    )
    await apply_changes(
        Database.default,
        state,
        [c.RemoveConstraint(constraint=k) for k in keys]
        + [c.RemoveIndex(index=i) for i in indexes],
    )
    assert not any(has_index(db_driver, i) for i in indexes)

    state = EMPTY_SNAPSHOT
    for migration in migrations:
        state = await apply_changes(Database.default, state, list(migration.changes))
    assert all(has_index(db_driver, i) for i in indexes)
    assert all(has_constraint(db_driver, k) for k in keys)

    for migration in migrations:  # (again: nothing to do, and no error)
        state = await apply_changes(Database.default, state, list(migration.changes))
    assert all(has_index(db_driver, i) for i in indexes)
