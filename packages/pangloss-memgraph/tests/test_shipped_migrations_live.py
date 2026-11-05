"""The migrations that library packages ship, applied to Memgraph: the indexes and keys they describe are made"""

import pytest
from pangloss_memgraph.databases.memgraph.migrations import apply_changes
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, graph_of
from pangloss_memgraph.databases.memgraph.database import current

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
        current(),
        EMPTY_SNAPSHOT,
        [c.AddIndex(index=i) for i in indexes]
        + [c.AddConstraint(constraint=k) for k in keys],
    )
    await apply_changes(
        current(),
        state,
        [c.RemoveConstraint(constraint=k) for k in keys]
        + [c.RemoveIndex(index=i) for i in indexes],
    )
    assert not any(has_index(db_driver, i) for i in indexes)

    state = EMPTY_SNAPSHOT
    for migration in migrations:
        state = await apply_changes(current(), state, list(migration.changes))
    assert all(has_index(db_driver, i) for i in indexes)
    assert all(has_constraint(db_driver, k) for k in keys)

    for migration in migrations:  # (again: nothing to do, and no error)
        state = await apply_changes(current(), state, list(migration.changes))
    assert all(has_index(db_driver, i) for i in indexes)


async def test_the_ends_of_a_date_range_are_renamed(db_driver, clear_database):
    """`pangloss_dates` 0002: a range written when its ends were `earliest` and `latest` is read with them as
    `not_before` and `not_after`"""
    import importlib

    from pangloss_dates import julian, models
    from pangloss_models import Document, ModelRegistry, initialise
    from pangloss_testing.live import initialise_database

    ModelRegistry._reset()
    for module in (models, julian):
        importlib.reload(module)

    class Factoid(Document):
        when: julian.JulianDate

    initialise()
    await initialise_database()
    saved = await Factoid.Create(
        label="x",
        when={
            "type": "JulianDateRange",
            "not_before": {"type": "JulianExactDate", "year": 1500},
            "not_after": {"type": "JulianExactDate", "year": 1502},
        },
    ).save()
    # (as it was stored before)
    for new, old in (("not_before", "earliest"), ("not_after", "latest")):
        for suffix in ("", "_reverse"):
            show(
                db_driver,
                f"MATCH (a)-[r:{new}{suffix}]->(b) CREATE (a)-[o:{old}{suffix}]->(b) SET o = properties(r) DELETE r",
            )

    dates = [m for m in graph_of(APPS).order() if m.app == "pangloss_dates"]
    state = await apply_changes(current(), EMPTY_SNAPSHOT, list(dates[0].changes))
    assert dates[1].name.startswith("0002")
    await apply_changes(current(), state, list(dates[1].changes))

    read = await Factoid.get(id=saved.id)
    assert (read.when.not_before.year, read.when.not_after.year) == (1500, 1502)
    assert not show(
        db_driver,
        "MATCH ()-[r:earliest|latest|earliest_reverse|latest_reverse]->() RETURN r",
    )
