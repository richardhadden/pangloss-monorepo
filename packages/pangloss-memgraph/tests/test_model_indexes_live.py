"""The indexes of the models, made in Memgraph, and used by a search"""

from typing import no_type_check

import pytest
from pangloss_memgraph.databases.memgraph.build_search_query import build_search_query
from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.initialise_database import (
    initialise_database,
    structure,
)
from pangloss_memgraph.databases.memgraph.migrations import apply_changes
from pangloss_models import initialise
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.search import Match, check_match

pytestmark = pytest.mark.asyncio(loop_scope="session")

LABELS = ["IdxLetter", "IdxPerson"]


def models():
    class IdxPerson(Entity):
        pass

    class IdxLetter(Document):
        _meta = Document.Meta(indexes=["year"])
        year: int

    initialise()
    return IdxPerson, IdxLetter


def show(db_driver) -> list[dict]:
    with db_driver.session() as session:  # (not in a transaction)
        return session.run("SHOW INDEX INFO").data()


def mine(db_driver) -> set[tuple]:
    return {
        (r["index type"], r["label"], tuple(r["property"] or ()))
        for r in show(db_driver)
        if r["label"] in LABELS
    }


def drop_mine(db_driver) -> None:
    with db_driver.session() as session:
        for row in show(db_driver):
            if row["label"] in LABELS:
                properties = (
                    f"({', '.join(row['property'])})" if row["property"] else ""
                )
                session.run(f"DROP INDEX ON :{row['label']}{properties}").consume()


async def test_the_database_is_set_up_with_the_indexes_of_the_models_and_again_harmlessly(
    db_driver,
):
    models()
    try:
        setup = await initialise_database()
        assert mine(db_driver) == {
            ("label", "IdxLetter", ()),
            ("label+property", "IdxLetter", ("year",)),
            ("label", "IdxPerson", ()),
        }
        assert "index :IdxLetter(year)" in setup.created
        again = await initialise_database()
        assert "index :IdxLetter(year)" in again.already_present
        assert not [d for d in again.created if "Idx" in d]
    finally:
        drop_mine(db_driver)


async def test_they_are_in_the_structure_that_migrations_make_and_unmake(db_driver):
    models()
    entries = [e for e in structure()["indexes"] if e["label"] in LABELS]
    assert len(entries) == 3 and all("app" not in e for e in entries)
    try:
        await apply_changes(
            Database.default,
            EMPTY_SNAPSHOT,
            [c.AddIndex(index=e) for e in entries] * 2,  # (twice: harmless)
        )
        assert len(mine(db_driver)) == 3

        await apply_changes(
            Database.default,
            EMPTY_SNAPSHOT,
            [c.RemoveIndex(index=e) for e in entries] * 2,
        )
        assert mine(db_driver) == set()
    finally:
        drop_mine(db_driver)


@no_type_check
async def test_a_search_of_a_class_starts_at_its_index_and_a_field_asked_for_is_looked_up(
    db_driver,
):
    IdxPerson, IdxLetter = models()

    def plan(model, where):
        query, params = build_search_query(
            model, check_match(model, Match(where=where)), 1, 25
        )
        with db_driver.session() as session:
            return [r["QUERY PLAN"] for r in session.run("EXPLAIN " + query, **params)]

    def scans(lines):
        # (of the node searched for: the page also looks up the creation and the user of each)
        return [
            line.strip("|* ")
            for line in lines
            if "Scan" in line and ("(n)" in line or "(n :" in line)
        ]

    try:
        assert scans(plan(IdxLetter, {"year": {"eq": 800}})) == [
            "ScanAll (n)"  # (nothing yet)
        ]
        await initialise_database()
        assert scans(plan(IdxLetter, {"year": {"eq": 800}})) == [
            "ScanAllByLabelProperties (n :IdxLetter {year})"
        ]
        assert scans(plan(IdxLetter, {})) == ["ScanAllByLabel (n :IdxLetter)"]
        assert scans(plan(IdxPerson, {"label": {"eq": "x"}})) == [
            "ScanAllByLabel (n :IdxPerson)"
        ]
    finally:
        drop_mine(db_driver)
