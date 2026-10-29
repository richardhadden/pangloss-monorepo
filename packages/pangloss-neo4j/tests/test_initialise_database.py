import neo4j
import pytest
from pangloss_neo4j.databases.neo4j.initialise_database import (
    INDEXES,
    TEXT_INDEX_NAME,
    UNIQUE_CONSTRAINTS,
    initialise_database,
)
from pangloss_neo4j.databases.neo4j.schema import (
    index_name,
    list_constraints,
    list_indexes,
    run_statement,
    search_patterns,
    unique_name,
)

from .conftest import NEO4J_DATABASE
from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def indexes(database):
    return await list_indexes(database.driver, NEO4J_DATABASE)


async def constraints(database):
    return await list_constraints(database.driver, NEO4J_DATABASE)


@pytest.fixture
def database():
    from pangloss_neo4j.databases.neo4j.database import Database

    return Database.default


# ---------------------------------------------------------------------------
# Indexes, constraints and the text index
# ---------------------------------------------------------------------------


async def test_database_has_indexes_constraints_and_text_index(database):
    """(The tests' own set-up has already run `initialise_database`)"""
    existing = await indexes(database)
    for label, properties in INDEXES:
        assert any(
            i.kind == "label+property"
            and i.label == label
            and i.properties == tuple(properties)
            for i in existing
        ), f"index on {label}{properties}"

    assert any(
        i.kind == "fulltext"
        and i.name == TEXT_INDEX_NAME
        and i.label == "PGIndexableNode"
        and i.properties == ("label",)
        for i in existing
    )

    found = await constraints(database)
    for label, property_name in UNIQUE_CONSTRAINTS:
        assert any(
            c.kind == "unique" and c.label == label and c.properties == (property_name,)
            for c in found
        ), f"unique constraint on {label}({property_name})"


async def test_every_label_has_a_lookup_index_without_being_asked(db_driver):
    """The assumption that node (and relationship) indexes exist by default"""
    rows = run(
        db_driver,
        "SHOW INDEXES YIELD type, entityType WHERE type = 'LOOKUP' RETURN entityType",
    )
    assert {row["entityType"] for row in rows} == {"NODE", "RELATIONSHIP"}


async def test_a_unique_constraint_brings_its_own_index_so_none_is_made_for_it(
    database,
):
    existing = await indexes(database)
    for label, property_name in UNIQUE_CONSTRAINTS:
        owned = [
            i
            for i in existing
            if i.label == label and i.properties == (property_name,) and i.owned
        ]
        assert len(owned) == 1, f"{label}({property_name})"
        # (and not a second one, which Neo4j would have refused or kept apart)
        assert not [
            i
            for i in existing
            if i.label == label and i.properties == (property_name,) and not i.owned
        ]


async def test_initialise_database_can_be_run_again(database):
    first = await initialise_database()
    second = await initialise_database()

    assert second.created == []
    assert len(second.already_present) == len(first.created) + len(
        first.already_present
    )
    assert first.created == []  # (it had already been run for the tests)


async def test_initialise_database_recreates_what_is_missing(database):
    driver = database.driver
    await run_statement(
        driver, NEO4J_DATABASE, f"DROP INDEX {index_name('HeadNode', ['id'])}"
    )
    await run_statement(driver, NEO4J_DATABASE, f"DROP INDEX {TEXT_INDEX_NAME}")
    await run_statement(
        driver, NEO4J_DATABASE, f"DROP CONSTRAINT {unique_name('PGUpdate', ['id'])}"
    )

    setup = await initialise_database()

    assert sorted(setup.created) == sorted(
        [
            "index :HeadNode(id)",
            f"text index {TEXT_INDEX_NAME} on :PGIndexableNode(label)",
            "unique constraint on :PGUpdate(id)",
            "index :PGUpdate(id)",  # (it goes with its constraint, and comes with it)
        ]
    )
    assert any(i.label == "HeadNode" for i in await indexes(database))
    assert any(i.kind == "fulltext" for i in await indexes(database))


async def test_an_index_made_by_hand_under_another_name_is_recognised(database):
    driver = database.driver
    await run_statement(
        driver, NEO4J_DATABASE, f"DROP INDEX {index_name('HeadNode', ['id'])}"
    )
    await run_statement(
        driver,
        NEO4J_DATABASE,
        "CREATE INDEX made_by_hand FOR (n:HeadNode) ON (n.id)",
    )
    try:
        setup = await initialise_database()
        assert "index :HeadNode(id)" in setup.already_present
        assert setup.created == []
    finally:
        await run_statement(driver, NEO4J_DATABASE, "DROP INDEX made_by_hand")
        await initialise_database()


@pytest.mark.parametrize("label, property_name", UNIQUE_CONSTRAINTS)
async def test_ids_and_urls_are_unique(db_driver, clear_database, label, property_name):
    run(db_driver, f"CREATE (:{label} {{{property_name}: 'the-same-value'}})")

    with pytest.raises(neo4j.exceptions.ConstraintError, match="already exists"):
        run(db_driver, f"CREATE (:{label} {{{property_name}: 'the-same-value'}})")

    run(db_driver, f"MATCH (n:{label}) DETACH DELETE n")


# ---------------------------------------------------------------------------
# The text index
# ---------------------------------------------------------------------------


def find(db_driver, pattern: str) -> list[str]:
    return [
        row["id"]
        for row in run(
            db_driver,
            f"CALL db.index.fulltext.queryNodes('{TEXT_INDEX_NAME}', $pattern) "
            "YIELD node RETURN node.id AS id ORDER BY id",
            pattern=pattern,
        )
    ]


def seed(db_driver):
    for id, label in {
        "a": "A Gazetteer",
        "b": "Something else",
        "c": "Zürich Café",
        "d": "Max-Planck_Institut",
        "e": "Straße",
    }.items():
        run(
            db_driver,
            "CREATE (:PGIndexableNode {id: $id, label: $label})",
            id=id,
            label=label,
        )


async def test_the_text_index_is_used_for_searching(db_driver, clear_database):
    seed(db_driver)
    assert find(db_driver, "*gazetteer*") == ["a"]


async def test_search_matches_inside_words_whatever_the_case(db_driver, clear_database):
    seed(db_driver)
    assert find(db_driver, "*GAZET*".lower()) == ["a"]
    assert find(db_driver, "*zett*") == ["a"]


async def test_the_text_index_folds_accents(db_driver, clear_database):
    seed(db_driver)
    assert find(db_driver, "*zurich*") == ["c"]
    assert find(db_driver, "*cafe*") == ["c"]
    assert find(db_driver, "*strasse*") == ["e"]


async def test_a_node_is_found_in_the_transaction_that_wrote_it(
    db_driver, clear_database
):
    """No need to commit before searching (found out, and relied on by the tests that write and then list)"""
    with db_driver.session(database=NEO4J_DATABASE) as session:

        def work(tx):
            tx.run("CREATE (:PGIndexableNode {id: 'x', label: 'Fresh'})")
            return tx.run(
                f"CALL db.index.fulltext.queryNodes('{TEXT_INDEX_NAME}', '*fresh*') YIELD node RETURN count(node) AS c"
            ).single()["c"]

        assert session.execute_write(work) == 1


async def test_a_changed_or_deleted_label_is_found_no_more(db_driver, clear_database):
    seed(db_driver)
    run(db_driver, "MATCH (n:PGIndexableNode {id: 'a'}) SET n.label = 'Ferdinand'")
    assert find(db_driver, "*gazetteer*") == []
    assert find(db_driver, "*ferdin*") == ["a"]
    run(db_driver, "MATCH (n:PGIndexableNode {id: 'a'}) DETACH DELETE n")
    assert find(db_driver, "*ferdin*") == []


async def test_a_search_with_special_characters_is_not_a_parse_error(
    db_driver, clear_database
):
    seed(db_driver)
    for typed in ["a(b", "max-planck", "what? *", "[", "\\", "'quote'", "x:y"]:
        for pattern in search_patterns(typed):
            find(db_driver, pattern)  # (raises if Lucene cannot read it)
    assert [find(db_driver, p) for p in search_patterns("max-planck")] == [["d"], ["d"]]
