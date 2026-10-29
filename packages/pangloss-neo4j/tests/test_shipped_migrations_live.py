"""The migrations that library packages ship, applied to Neo4j: the indexes and keys they describe are made"""

import pytest
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, graph_of
from pangloss_neo4j.databases.neo4j.database import Database
from pangloss_neo4j.databases.neo4j.migrations import apply_changes

from .schema_helpers import has_constraint, has_index

pytestmark = pytest.mark.asyncio(loop_scope="session")

APPS = ["pangloss_dates", "pangloss_calendar", "pangloss_zotero", "pangloss_neo4j"]


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
    # (a label has an index in every database, and so is always found)
    assert not any(has_index(db_driver, i) for i in indexes if i["kind"] != "label")

    state = EMPTY_SNAPSHOT
    for migration in migrations:
        state = await apply_changes(Database.default, state, list(migration.changes))
    assert all(has_index(db_driver, i) for i in indexes)
    assert all(has_constraint(db_driver, k) for k in keys)

    for migration in migrations:  # (again: nothing to do, and no error)
        state = await apply_changes(Database.default, state, list(migration.changes))
    assert all(has_index(db_driver, i) for i in indexes)
