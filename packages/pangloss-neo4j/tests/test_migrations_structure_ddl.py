"""Indexes and constraints as changes, made on a database"""

import pytest
from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT
from pangloss_neo4j.databases.neo4j.database import Database
from pangloss_neo4j.databases.neo4j.initialise_database import structure
from pangloss_neo4j.databases.neo4j.migrations import apply_changes

from .schema_helpers import has_constraint, has_index

pytestmark = pytest.mark.asyncio(loop_scope="session")

INDEX = {"kind": "label+property", "label": "MigScratch", "properties": ["a", "b"]}
TEXT = {
    "kind": "text",
    "label": "MigScratch",
    "properties": ["label"],
    "name": "mig_scratch_text",
}
UNIQUE = {"kind": "unique", "label": "MigScratch", "properties": ["a"]}


async def test_indexes_are_made_and_dropped_and_repeating_is_harmless(
    db_driver, clear_database
):
    state = EMPTY_SNAPSHOT
    try:
        add = [c.AddIndex(index=INDEX), c.AddIndex(index=TEXT)]
        state = await apply_changes(Database.default, state, add)
        assert has_index(db_driver, INDEX) and has_index(db_driver, TEXT)
        assert state["indexes"] == [INDEX, TEXT]

        await apply_changes(Database.default, EMPTY_SNAPSHOT, add)  # (already there)
        assert has_index(db_driver, INDEX)

        drop = [c.RemoveIndex(index=INDEX), c.RemoveIndex(index=TEXT)]
        state = await apply_changes(Database.default, state, drop)
        assert not has_index(db_driver, INDEX) and not has_index(db_driver, TEXT)
        assert state["indexes"] == []
        await apply_changes(Database.default, state, drop)  # (already gone)
    finally:
        await apply_changes(
            Database.default,
            EMPTY_SNAPSHOT,
            [c.RemoveIndex(index=INDEX), c.RemoveIndex(index=TEXT)],
        )


async def test_constraints_are_made_and_dropped(db_driver, clear_database):
    try:
        await apply_changes(
            Database.default, EMPTY_SNAPSHOT, [c.AddConstraint(constraint=UNIQUE)]
        )
        assert has_constraint(db_driver, UNIQUE)
        await apply_changes(
            Database.default, EMPTY_SNAPSHOT, [c.AddConstraint(constraint=UNIQUE)]
        )

        with db_driver.session() as session:
            session.run("CREATE (:MigScratch {a: 1})").consume()
            with pytest.raises(Exception, match="unique|constraint"):
                session.run("CREATE (:MigScratch {a: 1})").consume()

        await apply_changes(
            Database.default, EMPTY_SNAPSHOT, [c.RemoveConstraint(constraint=UNIQUE)]
        )
        assert not has_constraint(db_driver, UNIQUE)
    finally:
        await apply_changes(
            Database.default, EMPTY_SNAPSHOT, [c.RemoveConstraint(constraint=UNIQUE)]
        )


async def test_a_constraint_that_the_data_breaks_says_so(db_driver, clear_database):
    with db_driver.session() as session:
        session.run("CREATE (:MigScratch {a: 1}), (:MigScratch {a: 1})").consume()
    with pytest.raises(PanglossMigrationError, match="may break it"):
        await apply_changes(
            Database.default, EMPTY_SNAPSHOT, [c.AddConstraint(constraint=UNIQUE)]
        )
    assert not has_constraint(db_driver, UNIQUE)


async def test_what_the_database_needs_is_what_the_changes_make(
    db_driver, clear_database
):
    """`structure()` is what `initialise_database` makes: making it by changes finds it all there"""
    needed = structure()
    changes = [c.AddIndex(index=e) for e in needed["indexes"]] + [
        c.AddConstraint(constraint=e) for e in needed["constraints"]
    ]
    await apply_changes(
        Database.default, EMPTY_SNAPSHOT, changes
    )  # (nothing to make: no error)
    assert all(has_index(db_driver, e) for e in needed["indexes"])
    assert all(has_constraint(db_driver, e) for e in needed["constraints"])
    assert {e["app"] for e in [*needed["indexes"], *needed["constraints"]]} == {
        "pangloss_neo4j"
    }
