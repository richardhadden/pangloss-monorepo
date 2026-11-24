"""`hooks.confirmed` raised by `pangloss-review`: once for each toolchain's suggestion a person confirms, after its
document is written, with every way of confirming (as it is, as one entity, the others given the same, those a
mention names, a save of the document); the one confirmed by its own route `direct`, the others not. Nothing for a
suggestion that goes otherwise (edited away, deleted, its document deleted), for a confirmation that fails, for an
identification merely written again, or for a write by a toolchain; a listener that fails does not fail it, and a
listener may write to the database. Also: the confirm route's `entity`, and a suggestion's `text`."""

import contextlib
import datetime
import importlib
import logging
from types import SimpleNamespace
from typing import no_type_check
from uuid import uuid4

import pytest
from pangloss_core import backend
from pangloss_models import Document, Entity, ToolchainRun, hooks, initialise
from pangloss_review import PanglossReconcileError, ReviewMeta, identify, reconcile
from pangloss_users import current_request_username, service

from .helpers import DATABASE_NAME, run

pytestmark = pytest.mark.asyncio(loop_scope="session")

RUN = ToolchainRun("extractor", version="1.2")
SUGGESTED = "IdentificationByToolchain"
FROM_TEXT = "IdentificationByToolchainFromText"


def models():
    # (the registry was reset, and a module is only run once: the library's models are declared again)
    import pangloss_library.models
    import pangloss_review.models

    importlib.reload(pangloss_review.models)
    importlib.reload(pangloss_library.models)
    library = pangloss_library.models
    Alternatives = library.WeightedAlternative

    class Person(Entity):
        _review_meta = ReviewMeta(allow_unreconciled=True)

    class Group(Entity):
        pass

    class Activity(Document):
        _meta = Document.Meta(create_directly=False)
        # (an identification takes its subclasses: the two that keep the text among them)
        by: list[
            Person
            | library.Identification[Alternatives[Person]]  # ty: ignore[invalid-type-form]
            | library.IdentificationByToolchain[Alternatives[Person]]  # ty: ignore[invalid-type-form]
        ]

    class Factoid(Document):
        _review_meta = ReviewMeta(reviewable=True)
        statements: list[Activity]

    initialise()
    return SimpleNamespace(
        Person=Person, Group=Group, Activity=Activity, Factoid=Factoid
    )


async def people(m, *names: str) -> list:
    return [(await m.Person.Create(label=name).save()).id for name in names]


def suggested(*shares: tuple, type: str = SUGGESTED, **more) -> dict:
    """An identification by the toolchain: who it could be, each with how likely"""
    text = {"text": "Jon Smyth"} if type == FROM_TEXT else {}
    return {
        "type": type,
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
        **text,
        **more,
    }


async def factoid(m, label: str, *by: dict):
    return await m.Factoid.Create(
        label=label,
        statements=[
            {"type": "Activity", "label": f"{label}: activity", "by": list(by)}
        ],
    ).save(detail=True, toolchain=RUN)


async def toolchain(db_driver) -> None:
    for name in ("ann", "bob"):
        db_driver.execute_query(
            "MERGE (:PGUser {username: $name})", name=name, database_=DATABASE_NAME
        )
    await service.create_toolchain("extractor")


@contextlib.contextmanager
def listening(listener):
    hooks.confirmed.append(listener)
    try:
        yield
    finally:
        hooks.confirmed.remove(listener)


@contextlib.contextmanager
def as_user(username: str):
    token = current_request_username.set(username)
    try:
        yield
    finally:
        current_request_username.reset(token)


def heard() -> tuple[list, object]:
    """What is told, and a listener that keeps it"""
    told: list = []

    async def listen(confirmation):
        told.append(confirmation)

    return told, listen


async def held(m, head) -> object:
    return (await m.Factoid.get(head.id)).statements[0].by[0]


def expected(made, part, entities, direct, user="ann", confirmed=None, **more):
    """The event of a confirmation of `part` (as it was written) in `made`"""
    was = part.type
    return dict(
        suggestion_id=part.id,
        suggestion_type=was,
        confirmed_type=confirmed
        or ("IdentificationFromText" if was == FROM_TEXT else "Identification"),
        head_id=made.id,
        head_type="Factoid",
        user=user,
        entities=tuple((str(id), "Person") for id in entities),
        direct=direct,
        **more,
    )


def fields(confirmation) -> dict:
    found = dict(confirmation.__dict__)
    found.pop("at")
    return found


@no_type_check
async def test_confirmed_as_it_is_with_one_candidate(clear_database, db_driver):
    m = models()
    await toolchain(db_driver)
    (john,) = await people(m, "John")
    made = await factoid(
        m, "One", suggested((john, 100), uris=["http://example.org/j"])
    )
    part = made.statements[0].by[0]
    told = []

    async def listen(confirmation):
        # (after the document's write, before the URIs are given)
        document = await m.Factoid.get(confirmation.head_id)
        person = await m.Person.get(john)
        told.append((confirmation, document.meta.version, list(person.urls)))

    before = datetime.datetime.now(datetime.UTC)
    with listening(listen), as_user("ann"):
        await identify.confirm(part.id, "ann")
    after = datetime.datetime.now(datetime.UTC)

    ((confirmation, version, urls),) = told
    assert confirmation == hooks.Confirmation(
        at=confirmation.at, **expected(made, part, [john], direct=True)
    )
    assert before <= confirmation.at <= after
    assert (version, urls) == (2, [])
    assert [str(u) for u in (await m.Person.get(john)).urls] == ["http://example.org/j"]


@no_type_check
async def test_confirmed_as_it_is_with_three_candidates_names_the_three(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    john, jack, mary = await people(m, "John", "Jack", "Mary")
    made = await factoid(
        m, "Three", suggested((jack, 50), (john, 30), (mary, 20), type=FROM_TEXT)
    )
    part = made.statements[0].by[0]
    told, listen = heard()
    with listening(listen), as_user("ann"):
        await identify.confirm(part.id, "ann")
    assert [fields(c) for c in told] == [
        expected(made, part, [jack, john, mary], direct=True)
    ]
    read = await held(m, made)
    assert (read.type, read.text) == ("IdentificationFromText", "Jon Smyth")


@no_type_check
async def test_confirmed_as_one_of_its_alternatives_or_as_another(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    john, jack, mary = await people(m, "John", "Jack", "Mary")
    uri = "http://example.org/one-of-them"
    one = await factoid(
        m, "One", suggested((john, 70), (jack, 30), uris=[uri], type=FROM_TEXT)
    )
    other = await factoid(m, "Other", suggested((john, 70), (jack, 30), type=FROM_TEXT))
    told, listen = heard()
    with listening(listen), as_user("ann"):
        done = await identify.confirm(
            one.statements[0].by[0].id, "ann", entity={"type": "Person", "id": jack}
        )
        # (one that is none of its alternatives: any entity its place takes)
        await identify.confirm(
            other.statements[0].by[0].id, "ann", entity={"type": "Person", "id": mary}
        )
    assert [fields(c) for c in told] == [
        expected(one, one.statements[0].by[0], [jack], direct=True),
        expected(other, other.statements[0].by[0], [mary], direct=True),
    ]
    read = await held(m, one)
    assert (read.type, read.text, read.uris) == (
        "IdentificationFromText",
        "Jon Smyth",
        [],
    )
    assert [(a.id, a.edge_properties.percent) for a in read.target[0].alternatives] == [
        (jack, 100)
    ]
    # (its URIs go to that one, as when it has one candidate)
    assert done.uris_added == [uri]
    assert [str(u) for u in (await m.Person.get(jack)).urls] == [uri]
    assert (await m.Person.get(john)).urls == []
    assert [a.id for a in (await held(m, other)).target[0].alternatives] == [mary]


@no_type_check
async def test_a_confirmation_that_fails_is_told_nothing_and_writes_nothing(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    (john,) = await people(m, "John")
    group = (await m.Group.Create(label="A guild").save()).id
    made = await factoid(m, "One", suggested((john, 100)))
    told, listen = heard()
    with listening(listen), as_user("ann"):
        # (an entity its place does not take)
        with pytest.raises(PanglossReconcileError, match="does not take that") as error:
            await identify.confirm(
                made.statements[0].by[0].id,
                "ann",
                entity={"type": "Group", "id": group},
            )
    assert "One" in str(error.value)
    await reconcile.background_done()
    assert told == []
    assert (await m.Factoid.get(made.id)).meta.version == 1
    assert (await held(m, made)).type == SUGGESTED


@no_type_check
async def test_the_others_confirmed_with_it_are_told_not_direct(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    john, jack = await people(m, "John", "Jack")
    mine = await factoid(m, "Mine", suggested((john, 70), (jack, 30), type=FROM_TEXT))
    same = await factoid(m, "Same", suggested((john, 70), (jack, 30), type=FROM_TEXT))
    near = await factoid(m, "Near", suggested((john, 65), (jack, 35)))
    told, listen = heard()
    with listening(listen), as_user("ann"):
        await identify.confirm(
            mine.statements[0].by[0].id,
            "ann",
            also=[same.statements[0].by[0].id, near.statements[0].by[0].id, uuid4()],
        )
        await reconcile.background_done()
    assert [fields(c) for c in told] == [
        expected(mine, mine.statements[0].by[0], [john, jack], direct=True),
        expected(same, same.statements[0].by[0], [john, jack], direct=False),
        expected(near, near.statements[0].by[0], [john, jack], direct=False),
    ]
    assert (await held(m, same)).text == "Jon Smyth"

    # confirmed as one entity, the others are given that one
    first = await factoid(m, "First", suggested((john, 70), (jack, 30)))
    second = await factoid(
        m, "Second", suggested((john, 70), (jack, 30), type=FROM_TEXT)
    )
    told.clear()
    with listening(listen), as_user("ann"):
        await identify.confirm(
            first.statements[0].by[0].id,
            "ann",
            also=[second.statements[0].by[0].id],
            entity={"type": "Person", "id": jack},
        )
        await reconcile.background_done()
    assert [fields(c) for c in told] == [
        expected(first, first.statements[0].by[0], [jack], direct=True),
        expected(second, second.statements[0].by[0], [jack], direct=False),
    ]
    read = await held(m, second)
    assert (read.type, read.text) == ("IdentificationFromText", "Jon Smyth")
    assert [a.id for a in read.target[0].alternatives] == [jack]


@no_type_check
async def test_given_to_others_and_confirmed_as_an_entity_are_not_direct(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    john, jack = await people(m, "John", "Jack")
    mine = await factoid(m, "Mine", suggested((john, 70), (jack, 30)))
    same = await factoid(m, "Same", suggested((john, 70), (jack, 30), type=FROM_TEXT))
    named = await factoid(
        m,
        "Named",
        suggested((john, 50), (jack, 50), type=FROM_TEXT, uris=["http://x.org/j"]),
    )
    # (as a form has it: corrected to John)
    target = [
        {
            "type": "WeightedAlternative",
            "alternatives": [
                {"type": "Person", "id": str(john), "edgeProperties": {"percent": 100}}
            ],
        }
    ]
    told, listen = heard()
    with listening(listen), as_user("ann"):
        assert (
            await identify.give_to_others(
                mine.statements[0].by[0].id,
                "ann",
                [same.statements[0].by[0].id],
                target,
            )
            == 1
        )
        await reconcile.background_done()
        # (a mention reconciled, whose URI it names: by the user of the request)
        assert (
            await identify.confirm_as_entity(
                [named.statements[0].by[0].id], {"type": "Person", "id": jack}
            )
            == 1
        )
        await reconcile.background_done()
    assert [fields(c) for c in told] == [
        expected(same, same.statements[0].by[0], [john], direct=False),
        expected(named, named.statements[0].by[0], [jack], direct=False),
    ]
    for made in (same, named):
        read = await held(m, made)
        assert (read.type, read.text) == ("IdentificationFromText", "Jon Smyth")
    # (the form's own document is not written here: of it nothing is said)
    assert (await m.Factoid.get(mine.id)).meta.version == 1


def as_identification(part: dict, **more) -> dict:
    """A suggestion as a form sends it once it is confirmed there: the same node, as the class it becomes"""
    text = {"text": part["text"]} if part.get("text") else {}
    return {
        "type": "IdentificationFromText"
        if part["type"] == FROM_TEXT
        else "Identification",
        "id": part["id"],
        "target": part["target"],
        **text,
        **more,
    }


async def save_with(m, made, change, expected_version=1):
    edit = (await m.Factoid.get(made.id)).model_dump()
    statement = edit["statements"][0]
    statement["by"] = change(statement["by"])
    await m.Factoid.Update(
        id=made.id, label=f"{made.label}, saved", statements=[statement]
    ).save(expected_version=expected_version)


@no_type_check
async def test_a_save_that_confirms_a_suggestion_is_told_not_direct_by_the_saver(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    john, jack, mary = await people(m, "John", "Jack", "Mary")
    # (one of them with URIs, one without; one kept as it is)
    made = await factoid(
        m,
        "Saved",
        suggested((john, 70), (jack, 30), type=FROM_TEXT, uris=["http://x.org/m"]),
        suggested((john, 100)),
        suggested((jack, 100)),
    )
    first, second, kept = made.statements[0].by
    someone_else = suggested((mary, 100))["target"]

    def change(by):
        return [
            as_identification(by[0], target=someone_else),
            as_identification(by[1]),
            by[2],
        ]

    told, listen = heard()
    with listening(listen), as_user("bob"):
        await save_with(m, made, change)
        await reconcile.background_done()
    assert sorted(
        (fields(c) for c in told), key=lambda c: str(c["suggestion_id"])
    ) == sorted(
        [
            expected(made, first, [mary], direct=False, user="bob"),
            expected(made, second, [john], direct=False, user="bob"),
        ],
        key=lambda c: str(c["suggestion_id"]),
    )
    by = (await m.Factoid.get(made.id)).statements[0].by
    assert [(b.type, getattr(b, "text", None)) for b in by] == [
        ("IdentificationFromText", "Jon Smyth"),
        ("Identification", None),
        (SUGGESTED, None),
    ]
    assert [str(u) for u in (await m.Person.get(mary)).urls] == ["http://x.org/m"]
    assert kept.id == by[2].id


@no_type_check
async def test_a_save_s_confirmation_names_the_entities_that_save_wrote_not_a_later_one_s(
    clear_database, db_driver, monkeypatch
):
    """The entities are noted in the write (`ConfirmedInWrite.entities`), not read after it in the background: a
    second save of the document before the background work runs does not put its target under the first saver's
    name"""
    import asyncio

    m = models()
    await toolchain(db_driver)
    john, mary = await people(m, "John", "Mary")
    made = await factoid(m, "Twice", suggested((john, 100)))
    # (the background work of the first save held until the second save is made)
    second_made = asyncio.Event()
    real = identify._after_save

    async def held_back(event, noted):
        await second_made.wait()
        await real(event, noted)

    monkeypatch.setattr(identify, "_after_save", held_back)
    told, listen = heard()
    with listening(listen):
        with as_user("bob"):
            await save_with(m, made, lambda by: [as_identification(by[0])])
        with as_user("ann"):
            await save_with(
                m,
                made,
                lambda by: [{**by[0], "target": suggested((mary, 100))["target"]}],
                expected_version=2,
            )
        second_made.set()
        await reconcile.background_done()
    part = made.statements[0].by[0]
    assert [fields(c) for c in told] == [
        expected(made, part, [john], direct=False, user="bob")
    ]


@no_type_check
async def test_a_restore_that_writes_a_suggestion_again_as_an_identification_is_told_nothing(
    clear_database, db_driver
):
    """A restore (`save(restored_from=)`, as history's) of a version in which the node was an identification, over
    one in which it is a suggestion, is no one's judgement of the suggestion: nothing is told. Its URIs are given as
    for any save"""
    m = models()
    await toolchain(db_driver)
    (john,) = await people(m, "John")
    made = await factoid(m, "Restored", suggested((john, 100), uris=["http://x.org/r"]))
    told, listen = heard()
    with listening(listen), as_user("ann"):
        edit = (await m.Factoid.get(made.id)).model_dump()
        statement = edit["statements"][0]
        statement["by"] = [as_identification(statement["by"][0])]
        await m.Factoid.Update(
            id=made.id, label=made.label, statements=[statement]
        ).save(expected_version=1, restored_from=1)
        await reconcile.background_done()
    assert told == []
    assert (await held(m, made)).type == "Identification"
    assert [str(u) for u in (await m.Person.get(john)).urls] == ["http://x.org/r"]


@no_type_check
async def test_a_suggestion_that_goes_otherwise_is_told_nothing(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    john, jack = await people(m, "John", "Jack")
    away = await factoid(m, "Away", suggested((john, 100)))
    gone = await factoid(m, "Gone", suggested((john, 100)))
    deleted = await factoid(m, "Deleted", suggested((john, 100)))
    kept = await factoid(
        m, "Kept", suggested((john, 70), (jack, 30), uris=["http://x.org/k"])
    )
    told, listen = heard()
    with listening(listen), as_user("ann"):
        # edited away to a stand-in, and taken out of its document
        await save_with(
            m,
            away,
            lambda by: [
                {"type": "Unreconciled", "unreconciled_type": "Person", "label": "J"}
            ],
        )
        await save_with(m, gone, lambda by: [])
        # its document deleted
        await m.Factoid.delete(deleted.id)
        # an identification that keeps its URIs, written again: no confirmation
        await identify.confirm(kept.statements[0].by[0].id, "ann")
        told.clear()
        await save_with(m, kept, lambda by: by, expected_version=2)
        await reconcile.background_done()
    assert told == []
    read = await held(m, kept)
    assert (read.type, [str(u) for u in read.uris]) == (
        "Identification",
        ["http://x.org/k"],
    )


@no_type_check
async def test_a_save_that_fails_is_told_nothing_even_after_another_save(
    clear_database, db_driver
):
    from pangloss_models import PanglossWriteError

    m = models()
    await toolchain(db_driver)
    (john,) = await people(m, "John")
    refused = await factoid(m, "Refused", suggested((john, 100)))
    other = await factoid(m, "Other", suggested((john, 100)))
    told, listen = heard()
    with listening(listen), as_user("ann"):
        # (a later version than there is: refused once what it confirms has been noted)
        with pytest.raises(PanglossWriteError):
            await save_with(
                m, refused, lambda by: [as_identification(by[0])], expected_version=7
            )
        import pangloss_library.models

        # (what it would have confirmed is still noted: the next write must not take it as its own)
        noted = pangloss_library.models.confirmed_in_write.get()
        assert [one.id for one in noted] == [refused.statements[0].by[0].id]
        # (another document saved in the same context, which confirms nothing)
        await save_with(m, other, lambda by: by)
        await reconcile.background_done()
    assert told == []
    assert (await held(m, refused)).type == SUGGESTED


@no_type_check
async def test_a_write_by_a_toolchain_is_told_nothing_and_gives_no_uris(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    (john,) = await people(m, "John")
    made = await factoid(
        m, "Rewritten", suggested((john, 100), uris=["http://x.org/t"])
    )
    told, listen = heard()
    with listening(listen), as_user("extractor"):
        await save_with(m, made, lambda by: [as_identification(by[0])])
        await reconcile.background_done()
    assert told == []
    assert (await held(m, made)).type == "Identification"
    assert (await m.Person.get(john)).urls == []


@no_type_check
async def test_a_listener_that_fails_does_not_fail_the_confirmation(
    clear_database, db_driver, caplog
):
    m = models()
    await toolchain(db_driver)
    (john,) = await people(m, "John")
    made = await factoid(m, "One", suggested((john, 100), uris=["http://x.org/f"]))
    part = made.statements[0].by[0]

    async def failing(confirmation):
        raise RuntimeError("no")

    with (
        listening(failing),
        as_user("ann"),
        caplog.at_level(logging.ERROR, logger="pangloss.models.hooks"),
    ):
        done = await identify.confirm(part.id, "ann")
    assert done.uris_added == ["http://x.org/f"]
    assert (await held(m, made)).type == "Identification"
    (record,) = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert str(part.id) in record.getMessage()


@no_type_check
async def test_a_listener_may_write_to_the_database(clear_database, db_driver):
    m = models()
    await toolchain(db_driver)
    (john,) = await people(m, "John")
    made = await factoid(m, "One", suggested((john, 100)))
    part = made.statements[0].by[0]

    async def keep(confirmation):
        database = backend.current().database()

        @database.write_transaction
        async def write(tx):
            await (
                await tx.run(
                    "CREATE (:PGConfirmedForTest {suggestion: $suggestion, entity: $entity})",
                    suggestion=str(confirmation.suggestion_id),
                    entity=confirmation.entities[0][0],
                )
            ).consume()

        await write()

    with listening(keep), as_user("ann"):
        await identify.confirm(part.id, "ann")
    rows = run(db_driver, "MATCH (n:PGConfirmedForTest) RETURN n")
    assert [(row["n"]["suggestion"], row["n"]["entity"]) for row in rows] == [
        (str(part.id), str(john))
    ]


@no_type_check
async def test_confirming_as_one_entity_over_the_api(clear_database, db_driver):
    from pangloss_api import create_app
    from pangloss_review import api

    from .test_api_models import client_for, logged_in

    m = models()
    await toolchain(db_driver)
    john, jack = await people(m, "John", "Jack")
    group = (await m.Group.Create(label="A guild").save()).id
    made = await factoid(m, "Mine", suggested((john, 60), (jack, 40), type=FROM_TEXT))
    same = await factoid(m, "Same", suggested((john, 60), (jack, 40)))
    id = str(made.statements[0].by[0].id)

    app = create_app()
    app.include_router(api.router)
    api.configure_app(app, None)
    async with client_for(app) as client:
        # (a user who logs in: not one of those `toolchain` makes, who have no password)
        bob = await logged_in(client, "cal")
        listed = (await client.get("/api/review/identifications", headers=bob)).json()
        assert sorted((s["head"]["label"], s["text"]) for s in listed["results"]) == [
            ("Mine", "Jon Smyth"),
            ("Same", None),
        ]
        one = (
            await client.get(f"/api/review/identifications/{id}", headers=bob)
        ).json()
        assert one["text"] == "Jon Smyth"
        # (one its place does not take: a 422 that says why)
        refused = await client.post(
            f"/api/review/identifications/{id}/confirm",
            headers=bob,
            json={"entity": {"type": "Group", "id": str(group)}},
        )
        assert refused.status_code == 422, refused.text
        assert "does not take that" in refused.json()["detail"]
        # (and one that is not there)
        missing = await client.post(
            f"/api/review/identifications/{id}/confirm",
            headers=bob,
            json={"entity": {"type": "Person", "id": str(uuid4())}},
        )
        assert missing.status_code == 422, missing.text
        assert missing.json()["error"] == "PanglossReferenceError"
        done = await client.post(
            f"/api/review/identifications/{id}/confirm",
            headers=bob,
            json={
                "also": [str(same.statements[0].by[0].id)],
                "entity": {"type": "Person", "id": str(jack)},
            },
        )
        assert done.status_code == 200, done.text
        assert done.json()["queued"] == 1
        await reconcile.background_done()
        for head in (made, same):
            read = (await client.get(f"/api/Factoid/{head.id}", headers=bob)).json()
            by = read["statements"][0]["by"][0]
            assert by["identifiedBy"] == "cal"
            assert [a["id"] for a in by["target"][0]["alternatives"]] == [str(jack)]
