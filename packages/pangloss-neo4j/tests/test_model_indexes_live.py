"""The indexes of the models, made in Neo4j, and used by a search"""

from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.search import Match, check_match

from .schema_helpers import drop_indexes_of, indexes
from pangloss_neo4j.databases.neo4j.build_search_query import build_search_query
from pangloss_neo4j.databases.neo4j.database import Database
from pangloss_neo4j.databases.neo4j.initialise_database import (
    initialise_database,
    structure,
)
from pangloss_neo4j.databases.neo4j.migrations import apply_changes

pytestmark = pytest.mark.asyncio(loop_scope="session")

LABELS = ["IdxLetter", "IdxPerson", "IdxDate", "IdxPlain"]


def models():
    class IdxPerson(Entity):
        pass

    class IdxLetter(Document):
        _meta = Document.Meta(indexes=["year"])
        year: int

    initialise()
    return IdxPerson, IdxLetter


def mine(db_driver) -> set[tuple]:
    return {
        (
            "label+property" if r["type"] == "RANGE" else r["type"].lower(),
            r["labelsOrTypes"][0],
            tuple(r["properties"]),
        )
        for r in indexes(db_driver)
        if r["labelsOrTypes"][0] in LABELS
    }


def drop_mine(db_driver) -> None:
    drop_indexes_of(db_driver, set(LABELS))


async def test_the_database_is_set_up_with_the_indexes_of_the_models_and_again_harmlessly(
    db_driver,
):
    models()
    try:
        setup = await initialise_database()
        # (the index of a label is not made: every database has one)
        assert mine(db_driver) == {("label+property", "IdxLetter", ("year",))}
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
        # (the two entries for a label are not made: every database has an index of each label)
        assert len(mine(db_driver)) == 1

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
            return session.run("EXPLAIN " + query, **params).consume().plan

    def scans(root):
        """The operators that find the node searched for (`n`), with what they say of it: the page also looks up the
        creation and the user of each"""
        found = []

        def walk(node):
            details = str(node["args"].get("Details", ""))
            if (
                "Scan" in node["operatorType"] or "Seek" in node["operatorType"]
            ) and " n:" in f" {details}":
                found.append((node["operatorType"].split("@")[0], details))
            for child in node.get("children", []):
                walk(child)

        walk(root)
        return found

    try:
        # (without an index of the field, the label's lookup index, which every database has, is what finds them)
        before = scans(plan(IdxLetter, {"year": {"eq": 800}}))
        assert [kind for kind, _ in before] == ["NodeByLabelScan"]
        await initialise_database()
        after = scans(plan(IdxLetter, {"year": {"eq": 800}}))
        assert [kind for kind, _ in after] == ["NodeIndexSeek"]
        assert "IdxLetter(year)" in after[0][1]
        assert [k for k, _ in scans(plan(IdxLetter, {}))] == ["NodeByLabelScan"]
        assert [k for k, _ in scans(plan(IdxPerson, {"label": {"eq": "x"}}))] == [
            "NodeByLabelScan"
        ]
    finally:
        drop_mine(db_driver)


async def test_an_embedded_class_gets_the_indexes_it_asks_for_and_no_label_index(
    db_driver,
):
    class IdxDate(Embedded):
        _meta = Embedded.Meta(indexes=["sort_day"])
        sort_day: int | None = None

    class IdxExact(IdxDate):
        year: int

    class IdxPlain(Embedded):
        text: str

    class IdxNote(Document):
        when: IdxDate | IdxPlain

    initialise()
    try:
        await initialise_database()
        assert mine(db_driver) >= {("label+property", "IdxDate", ("sort_day",))}
        assert not {t for t in mine(db_driver) if t[1] in ("IdxPlain", "IdxExact")}
        assert ("label", "IdxDate", ()) not in mine(db_driver)
    finally:
        drop_mine(db_driver)
