"""The URIs that parts of documents name (`pangloss-review`): an unreconciled mention and an identification a
toolchain suggested that name the same URI are of the same person, whoever that is. They are found by the URI
(`pangloss_review.uris`), offered first when one of them is reconciled or confirmed, and done with it."""

import importlib
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_models import Document, Entity, ToolchainRun, initialise
from pangloss_review import ReviewMeta, identify, reconcile, uris
from pangloss_users import current_request_username, service

from .helpers import DATABASE_NAME, run

pytestmark = pytest.mark.asyncio(loop_scope="session")

RUN = ToolchainRun("extractor", version="1.2")
JOHN = "http://example.org/person/john"
MARY = "http://example.org/person/mary"


def same_place(mine, other) -> bool:
    return mine.place == other.place


def models():
    import pangloss_library.models
    import pangloss_review.models

    importlib.reload(pangloss_review.models)
    importlib.reload(pangloss_library.models)
    library = pangloss_library.models
    Alternatives = library.WeightedAlternative

    class Person(Entity):
        _review_meta = ReviewMeta(allow_unreconciled=True)

    class Activity(Document):
        _meta = Document.Meta(create_directly=False)
        by: list[
            Person
            | library.Identification[Alternatives[Person]]  # ty: ignore[invalid-type-form]
            | library.IdentificationByToolchain[Alternatives[Person]]  # ty: ignore[invalid-type-form]
        ]

    class Factoid(Document):
        # (a rule for labels, which a URI in common is not held to)
        _review_meta = ReviewMeta(reviewable=True, reconcile_together=same_place)
        place: str = ""
        statements: list[Activity]

    initialise()
    return SimpleNamespace(Person=Person, Activity=Activity, Factoid=Factoid)


def mention(label: str, *named: str) -> dict:
    return {
        "type": "Unreconciled",
        "unreconciled_type": "Person",
        "label": label,
        "uris": list(named),
    }


def suggested(shares: list[tuple], *named: str) -> dict:
    return {
        "type": "IdentificationByToolchain",
        "uris": list(named),
        "target": [
            {
                "type": "WeightedAlternative",
                "alternatives": [
                    {
                        "type": "Person",
                        "id": id,
                        "edge_properties": {"percent": percent},
                    }
                    for id, percent in shares
                ],
            }
        ],
    }


async def factoid(m, label: str, *by: dict, place: str = ""):
    return await m.Factoid.Create(
        label=label,
        place=place,
        statements=[
            {"type": "Activity", "label": f"{label}: activity", "by": list(by)}
        ],
    ).save(detail=True, toolchain=RUN)


async def start(db_driver):
    m = models()
    db_driver.execute_query("MERGE (:PGUser {username: 'ann'})", database=DATABASE_NAME)
    await service.create_toolchain("extractor")
    return m


def claims(db_driver) -> list[tuple[str, str]]:
    rows = run(db_driver, "MATCH (c:PGUriClaim) RETURN c.uri AS uri, c.kind AS kind")
    return sorted((row["uri"], row["kind"]) for row in rows)


@no_type_check
async def test_the_uris_of_parts_are_found_and_follow_the_writes(
    clear_database, db_driver
):
    m = await start(db_driver)
    (john,) = [(await m.Person.Create(label="John").save()).id]
    one = await factoid(
        m, "One", mention("J. Smith", JOHN), suggested([(john, 100)], JOHN, MARY)
    )
    await factoid(m, "Two", mention("Nobody"))

    found = await uris.naming([JOHN])
    assert (len(found["mention"]), len(found["suggestion"])) == (1, 1)
    assert found["mention"] == [str(one.statements[0].by[0].id)]
    assert (await uris.naming([JOHN], except_id=found["mention"][0]))["mention"] == []
    assert claims(db_driver) == [
        (JOHN, "mention"),
        (JOHN, "suggestion"),
        (MARY, "suggestion"),
    ]
    # (nothing is left to do: the marks of the writes are worked off)
    assert (
        run(
            db_driver, "MATCH (p:PGPending {kind: 'review-uris'}) RETURN count(p) AS c"
        )[0]["c"]
        == 0
    )

    # the document written again without the mention: its claims are those of what it holds now
    edit = (await m.Factoid.get(one.id)).model_dump()
    edit["statements"][0]["by"] = edit["statements"][0]["by"][1:]
    await m.Factoid.Update(id=one.id, label="One", statements=edit["statements"]).save()
    assert (await uris.naming([JOHN]))["mention"] == []
    assert claims(db_driver) == [(JOHN, "suggestion"), (MARY, "suggestion")]

    # made again from the parts there are
    run(db_driver, "MATCH (c:PGUriClaim) DELETE c")
    assert await uris.rebuild() == 2
    assert claims(db_driver) == [(JOHN, "suggestion"), (MARY, "suggestion")]


@no_type_check
async def test_the_parts_of_several_documents_are_found_where_their_labels_are_indexed(
    clear_database, db_driver
):
    """Where the labels of the two kinds of part each have an index (a migrated project on Memgraph), `part:A OR
    part:B` after an `UNWIND` is planned as a union of two scans by label, and what was unwound is lost to the
    conditions after it: the parts of one document of several were found. (`graph.has_a_label`)"""
    from pangloss_review import graph

    from pangloss_testing.backends import under_test

    m = await start(db_driver)
    indexed = ["Unreconciled", "IdentificationByToolchain"]
    memgraph = under_test().name == "memgraph"

    def ddl(verb: str) -> None:
        if memgraph:  # (Neo4j finds nodes by any label without one)
            with db_driver.session(database=DATABASE_NAME) as session:
                for label in indexed:
                    session.run(f"{verb} INDEX ON :{label}").consume()

    john = (await m.Person.Create(label="John").save()).id
    ddl("CREATE")
    try:
        made = [
            await factoid(
                m,
                f"Document {n}",
                mention(f"Name {n}", JOHN),
                suggested([(john, 100)], JOHN),
            )
            for n in range(3)
        ]
        await reconcile.background_done()
        heads = [str(one.id) for one in made]
        run(db_driver, "MATCH (c:PGUriClaim) DELETE c")

        @graph._database().write_transaction
        async def replace(tx) -> None:
            await uris._replace(tx, heads)

        await replace()
        assert claims(db_driver) == sorted(
            [(JOHN, "mention"), (JOHN, "suggestion")] * 3
        )

        # (and read by id, several at once)
        ids = [str(one.statements[0].by[1].id) for one in made]
        assert sorted(
            row["id"] for row in await graph.suggestions_by_id(ids)
        ) == sorted(ids)
        offered = await identify.similar(made[0].statements[0].by[1].id)
        assert sorted(s.head.label for s in offered if s.same_uri) == [
            "Document 1",
            "Document 2",
        ]
    finally:
        ddl("DROP")


@no_type_check
async def test_mentions_of_one_uri_come_first_whatever_they_are_called(
    clear_database, db_driver
):
    m = await start(db_driver)
    john = await m.Person.Create(label="John Smith (1570)", urls=[JOHN]).save()
    mine = await factoid(m, "Mine", mention("John Smith", JOHN), place="Ghent")
    await factoid(m, "By URI", mention("Iohannes Faber", JOHN, MARY), place="Bruges")
    await factoid(m, "By label", mention("john smith"), place="Ghent")
    await factoid(m, "Elsewhere", mention("John Smith"), place="Bruges")
    await factoid(m, "Other URI", mention("Somebody", MARY), place="Ghent")
    id = mine.statements[0].by[0].id

    offered = await reconcile.similar(id)
    # (the one of the same URI first, though its label is unlike and the rule of the document is against it)
    assert [(s.head.label, s.same_uri, s.exact) for s in offered] == [
        ("By URI", True, False),
        ("By label", False, True),
    ]
    # who has the URI already
    known = (await reconcile.get_mention(id)).known
    assert [(k.id, k.label) for k in known] == [(john.id, "John Smith (1570)")]


@no_type_check
async def test_suggestions_of_one_uri_come_first_whoever_their_candidates(
    clear_database, db_driver
):
    m = await start(db_driver)
    john, jack, mary = [
        (await m.Person.Create(label=n).save()).id for n in ("John", "Jack", "Mary")
    ]
    # (with another of the same URI in its own document)
    mine = await factoid(
        m,
        "Mine",
        suggested([(john, 70), (jack, 30)], JOHN),
        suggested([(mary, 100)], JOHN),
    )
    await factoid(m, "By URI", suggested([(mary, 100)], JOHN))
    await factoid(m, "Alike", suggested([(john, 65), (jack, 35)]))
    await factoid(m, "Both", suggested([(john, 70), (jack, 30)], JOHN))
    await factoid(m, "A mention", mention("Iohannes", JOHN))
    id = mine.statements[0].by[0].id

    offered = await identify.similar(id)
    assert sorted((s.head.label, s.same_uri) for s in offered[:3]) == [
        ("Both", True),
        ("By URI", True),
        ("Mine", True),
    ]
    assert [(s.head.label, s.same_uri) for s in offered[3:]] == [("Alike", False)]
    assert [x.head.label for x in await identify.mentions_of_suggestion(id)] == [
        "A mention"
    ]


@no_type_check
async def test_reconciling_a_mention_confirms_the_suggestions_of_its_uri(
    clear_database, db_driver
):
    m = await start(db_driver)
    john, jack = [(await m.Person.Create(label=n).save()).id for n in ("John", "Jack")]
    mine = await factoid(m, "Mine", mention("John Smith", JOHN))
    other = await factoid(m, "Suggested", suggested([(jack, 60), (john, 40)], JOHN))
    id = mine.statements[0].by[0].id
    found = await reconcile.suggestions_of_mention(id)
    assert [s.head.label for s in found] == ["Suggested"]

    token = current_request_username.set("ann")
    try:
        done = await reconcile.reconcile(
            id, "Person", john, suggestions=[s.id for s in found]
        )
    finally:
        current_request_username.reset(token)
    assert done.queued == 1
    await reconcile.background_done()

    held = (await m.Factoid.get(other.id)).statements[0].by[0]
    assert (held.type, held.identified_by) == ("Identification", "ann")
    # (it is John and no other, as the mention was reconciled)
    assert [
        (a.label, a.edge_properties.percent) for a in held.target[0].alternatives
    ] == [("John", 100)]
    assert [str(u) for u in (await m.Person.get(john)).urls] == [JOHN]
    assert (await identify.list_suggestions()).count == 0


@no_type_check
async def test_confirming_a_suggestion_reconciles_the_mentions_of_its_uri(
    clear_database, db_driver
):
    m = await start(db_driver)
    (john,) = [(await m.Person.Create(label="John").save()).id]
    mine = await m.Factoid.Create(
        label="Mine",
        statements=[
            {
                "type": "Activity",
                "label": "a",
                "by": [
                    suggested([(john, 100)], JOHN),
                    mention("In the same document", JOHN),
                ],
            }
        ],
    ).save(detail=True, toolchain=RUN)
    elsewhere = await factoid(m, "Elsewhere", mention("Iohannes", JOHN))
    id = mine.statements[0].by[0].id
    offered = await identify.mentions_of_suggestion(id)
    assert sorted(x.head.label for x in offered) == ["Elsewhere", "Mine"]

    # (in the form of its document: the one of that document is left to the form)
    token = current_request_username.set("ann")
    try:
        queued = await identify.give_to_others(
            id,
            "ann",
            [],
            [{"type": "Person", "id": john}],
            mentions=[x.id for x in offered],
            entity={"type": "Person", "id": str(john)},
        )
    finally:
        current_request_username.reset(token)
    assert queued == 1
    await reconcile.background_done()
    assert (await m.Factoid.get(elsewhere.id)).statements[0].by[0].type == "Person"
    assert (await m.Factoid.get(mine.id)).meta.version == 1
