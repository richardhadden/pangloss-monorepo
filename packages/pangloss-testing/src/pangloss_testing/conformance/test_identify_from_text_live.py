"""Identifications that keep what the source wrote (`IdentificationFromText`, `IdentificationByToolchainFromText` of
`pangloss-library`): stored and read with their text, made by hand, confirmed through review (`pangloss-review`) as
the class they become with the same id and text, and listed with the other suggestions"""

import importlib
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_models import Document, Entity, ToolchainRun, initialise
from pangloss_review import ReviewMeta, identify
from pangloss_users import current_request_username, service

from .helpers import DATABASE_NAME, run

pytestmark = pytest.mark.asyncio(loop_scope="session")

RUN = ToolchainRun("extractor", version="2.0")


def models():
    # (the registry was reset, and a module is only run once: the library's models are declared again)
    import pangloss_library.models
    import pangloss_review.models

    importlib.reload(pangloss_review.models)
    importlib.reload(pangloss_library.models)
    library = pangloss_library.models
    Alternatives = library.WeightedAlternative

    class Person(Entity):
        pass

    class Activity(Document):
        _meta = Document.Meta(create_directly=False)
        # (an identification takes its subclasses: the two that keep the text among them)
        by: (
            Person | library.Identification[Alternatives[Person]]  # ty: ignore[invalid-type-form]
        )
        # (and one of a single person, with the two classes named)
        witness: (
            Person
            | library.IdentificationFromText[Person]  # ty: ignore[invalid-type-form]
            | library.IdentificationByToolchainFromText[Person]  # ty: ignore[invalid-type-form]
        )

    class Factoid(Document):
        _review_meta = ReviewMeta(reviewable=True)
        statements: list[Activity]

    initialise()
    return SimpleNamespace(Person=Person, Activity=Activity, Factoid=Factoid)


async def people(m, *names: str) -> list:
    return [(await m.Person.Create(label=name).save()).id for name in names]


def alternatives(*shares: tuple) -> list[dict]:
    return [
        {
            "type": "WeightedAlternative",
            "alternatives": [
                {"type": "Person", "id": id, "edge_properties": {"percent": percent}}
                for id, percent in shares
            ],
        }
    ]


def from_text(text: str, *shares: tuple, **more) -> dict:
    """A toolchain's suggestion that keeps what the source wrote"""
    return {
        "type": "IdentificationByToolchainFromText",
        "text": text,
        "target": alternatives(*shares),
        **more,
    }


async def factoid(m, label: str, by: dict, witness: dict, **save):
    return await m.Factoid.Create(
        label=label,
        statements=[
            {
                "type": "Activity",
                "label": f"{label}: activity",
                "by": by,
                "witness": witness,
            }
        ],
    ).save(detail=True, **save)


async def toolchain(db_driver) -> None:
    db_driver.execute_query("MERGE (:PGUser {username: 'ann'})", database=DATABASE_NAME)
    await service.create_toolchain("extractor")


@no_type_check
async def test_a_suggestion_with_text_is_stored_and_read_with_it(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    john, mary = await people(m, "John", "Mary")
    made = await factoid(
        m,
        "Sale",
        from_text("Jon Smyth", (john, 80), (mary, 20), uris=["http://example.org/js"]),
        {
            "type": "IdentificationByToolchainFromText",
            "text": "Marie",
            "target": [{"type": "Person", "id": mary}],
        },
        toolchain=RUN,
    )
    read = (await m.Factoid.get(made.id)).statements[0]
    assert (read.by.type, read.by.text, read.by.identified_by) == (
        "IdentificationByToolchainFromText",
        "Jon Smyth",
        "extractor",
    )
    assert read.by.toolchain_version == "2.0"
    assert [
        (a.label, a.edge_properties.percent) for a in read.by.target[0].alternatives
    ] == [("John", 80), ("Mary", 20)]
    assert (read.witness.type, read.witness.text, read.witness.target[0].id) == (
        "IdentificationByToolchainFromText",
        "Marie",
        mary,
    )
    # (the node has the label of its own class, which review finds it by)
    rows = run(
        db_driver,
        "MATCH (n:IdentificationByToolchainFromText) RETURN n.text AS text ORDER BY text",
    )
    assert [row["text"] for row in rows] == ["Jon Smyth", "Marie"]


@no_type_check
async def test_an_identification_from_text_is_made_by_hand(clear_database, db_driver):
    m = models()
    (john,) = await people(m, "John")
    made = await factoid(
        m,
        "By hand",
        {
            "type": "IdentificationFromText",
            "text": "Johannes",
            "target": alternatives((john, 100)),
        },
        {
            "type": "IdentificationFromText",
            "text": "J.",
            "target": [{"type": "Person", "id": john}],
        },
    )
    read = (await m.Factoid.get(made.id)).statements[0]
    assert (read.by.type, read.by.text, read.by.identified_by) == (
        "IdentificationFromText",
        "Johannes",
        "pangloss_default_user",
    )
    assert (read.witness.type, read.witness.text) == ("IdentificationFromText", "J.")
    # (not a task of review)
    assert (await identify.list_suggestions()).count == 0


@no_type_check
async def test_confirmed_through_review_it_keeps_its_id_and_its_text(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    john, mary = await people(m, "John", "Mary")
    made = await factoid(
        m,
        "Sale",
        # (with alternatives still open)
        from_text("Jon Smyth", (john, 70), (mary, 30)),
        {
            "type": "IdentificationByToolchainFromText",
            "text": "Marie",
            "target": [{"type": "Person", "id": mary}],
        },
        toolchain=RUN,
    )
    statement = made.statements[0]

    token = current_request_username.set("ann")
    try:
        await identify.confirm(statement.by.id, "ann")
        await identify.confirm(statement.witness.id, "ann")
    finally:
        current_request_username.reset(token)

    read = await m.Factoid.get(made.id)
    by, witness = read.statements[0].by, read.statements[0].witness
    assert (by.type, by.id, by.text, by.identified_by) == (
        "IdentificationFromText",
        statement.by.id,
        "Jon Smyth",
        "ann",
    )
    assert not hasattr(by, "toolchain_version")
    assert [
        (a.label, a.edge_properties.percent) for a in by.target[0].alternatives
    ] == [("John", 70), ("Mary", 30)]
    assert (witness.type, witness.id, witness.text, witness.identified_by) == (
        "IdentificationFromText",
        statement.witness.id,
        "Marie",
        "ann",
    )
    assert (read.meta.version, read.meta.updated_by) == (3, "ann")
    rows = run(
        db_driver,
        "MATCH (n {id: $id}) RETURN labels(n) AS labels",
        id=str(statement.by.id),
    )
    assert "IdentificationFromText" in rows[0]["labels"]
    assert "IdentificationByToolchainFromText" not in rows[0]["labels"]
    assert (await identify.list_suggestions()).count == 0


@no_type_check
async def test_the_suggestions_of_both_classes_are_listed_together_in_id_order(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    (john,) = await people(m, "John")
    plain = {
        "type": "IdentificationByToolchain",
        "target": alternatives((john, 100)),
    }
    one = {"type": "Person", "id": john}
    made = [
        await factoid(m, "First", plain, one, toolchain=RUN),
        await factoid(m, "Second", from_text("Jon", (john, 100)), one, toolchain=RUN),
        await factoid(m, "Third", plain, one, toolchain=RUN),
        await factoid(m, "Fourth", from_text("Jhon", (john, 100)), one, toolchain=RUN),
    ]
    ids = sorted(factoid.statements[0].by.id for factoid in made)

    listed = await identify.list_suggestions()
    assert listed.count == 4
    assert [s.id for s in listed.results] == ids
    assert [(s.head.label, s.type, s.becomes) for s in listed.results] == [
        ("First", "IdentificationByToolchain", "Identification"),
        ("Second", "IdentificationByToolchainFromText", "IdentificationFromText"),
        ("Third", "IdentificationByToolchain", "Identification"),
        ("Fourth", "IdentificationByToolchainFromText", "IdentificationFromText"),
    ]
    page = await identify.list_suggestions(page=2, page_size=3)
    assert ([s.id for s in page.results], page.count) == (ids[3:], 4)
    assert (await identify.get_suggestion(ids[1])).type == (
        "IdentificationByToolchainFromText"
    )
