"""Identifications that a toolchain suggested (`IdentificationByToolchain` of `pangloss-library`), as tasks of review
(`pangloss-review`): listed with their candidates, confirmed by a person, and others like them confirmed in one go"""

import importlib
from types import SimpleNamespace
from typing import no_type_check
from uuid import uuid4

import pytest
from pangloss_models import Document, Entity, ToolchainRun, initialise
from pangloss_review import PanglossNoSuchTaskError, ReviewMeta, identify, reconcile
from pangloss_users import current_request_username, service
from pydantic import ValidationError

from .helpers import DATABASE_NAME, run

pytestmark = pytest.mark.asyncio(loop_scope="session")

RUN = ToolchainRun("extractor", version="1.2")


def models():
    # (the registry was reset, and a module is only run once: the library's models are declared again)
    import pangloss_library.models
    import pangloss_review.models

    importlib.reload(pangloss_review.models)
    importlib.reload(pangloss_library.models)
    library = pangloss_library.models
    Alternatives = library.WeightedAlternative
    Identification = library.Identification
    Suggested = library.IdentificationByToolchain

    class Person(Entity):
        pass

    class Activity(Document):
        _meta = Document.Meta(create_directly=False)
        by: (
            Person
            | Identification[Alternatives[Person]]  # ty: ignore[invalid-type-form]
            | Suggested[Alternatives[Person]]  # ty: ignore[invalid-type-form]
        )

    class Factoid(Document):
        _review_meta = ReviewMeta(reviewable=True)
        statements: list[Activity]

    initialise()
    return SimpleNamespace(Person=Person, Activity=Activity, Factoid=Factoid)


async def people(m, *names: str) -> list:
    return [(await m.Person.Create(label=name).save()).id for name in names]


def suggested(*shares: tuple, **more) -> dict:
    """An identification by the toolchain: who it could be, each with how likely"""
    return {
        "type": "IdentificationByToolchain",
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
        **more,
    }


async def factoid(m, label: str, by: dict, **save):
    return await m.Factoid.Create(
        label=label,
        statements=[{"type": "Activity", "label": f"{label}: activity", "by": by}],
    ).save(detail=True, **save)


async def toolchain(db_driver) -> None:
    db_driver.execute_query("MERGE (:PGUser {username: 'ann'})", database=DATABASE_NAME)
    await service.create_toolchain("extractor")


@no_type_check
async def test_who_identified_it_is_said_by_the_server(clear_database, db_driver):
    m = models()
    await toolchain(db_driver)
    (john,) = await people(m, "John")
    plain = {
        "type": "Identification",
        "target": [suggested((john, 100))["target"][0]],
    }
    # by whoever saves it
    made = await factoid(m, "By hand", plain)
    assert made.statements[0].by.identified_by == "pangloss_default_user"
    # in an upload for others: the first person named, and for a toolchain's the toolchain and its version
    for_ann = await factoid(m, "For Ann", plain, created_by=["ann"], toolchain=RUN)
    assert for_ann.statements[0].by.identified_by == "ann"
    by_tool = await factoid(
        m, "By the toolchain", suggested((john, 100)), created_by=["ann"], toolchain=RUN
    )
    held = by_tool.statements[0].by
    assert (held.type, held.identified_by, held.toolchain_version) == (
        "IdentificationByToolchain",
        "extractor",
        "1.2",
    )
    # (a suggestion needs its toolchain; it can be named in the suggestion itself)
    with pytest.raises(ValidationError, match="needs its toolchain"):
        await factoid(m, "No toolchain", suggested((john, 100)))
    named = await factoid(m, "Named", suggested((john, 100), identified_by="extractor"))
    assert named.statements[0].by.identified_by == "extractor"

    # a later edit by someone else keeps who identified it
    edit = made.model_dump()
    token = current_request_username.set("ann")
    try:
        await m.Factoid.Update(
            id=made.id, label="Changed", statements=edit["statements"]
        ).save()
    finally:
        current_request_username.reset(token)
    read = await m.Factoid.get(made.id)
    assert (read.meta.updated_by, read.statements[0].by.identified_by) == (
        "ann",
        "pangloss_default_user",
    )


@no_type_check
async def test_the_suggestions_are_listed_with_who_they_could_be(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    john, jack, mary = await people(m, "John", "Jack", "Mary")
    first = await factoid(
        m,
        "First",
        suggested((john, 70), (jack, 30), uris=["http://example.org/j"]),
        toolchain=RUN,
    )
    await factoid(m, "Second", suggested((mary, 100)), toolchain=RUN)
    # (an identification by a person is not a task)
    await factoid(
        m,
        "By hand",
        {"type": "Identification", "target": suggested((mary, 100))["target"]},
    )

    listed = await identify.list_suggestions()
    assert listed.count == 2
    one, two = listed.results
    assert [(c.label, c.percent) for c in one.candidates] == [
        ("John", 70),
        ("Jack", 30),
    ]
    assert (one.identified_by, one.toolchain_version, one.uris) == (
        "extractor",
        "1.2",
        ["http://example.org/j"],
    )
    assert (one.head.label, one.holder.type, one.holder.label) == (
        "First",
        "Activity",
        "First: activity",
    )
    assert [(c.label, c.percent) for c in two.candidates] == [("Mary", 100)]
    assert one.id == first.statements[0].by.id
    assert (await identify.get_suggestion(one.id)).head.label == "First"

    # of the documents given to someone
    from pangloss_review import service as review

    await review.assign(first.id, "ann", "ann", admin=False)
    assert [s.head.label for s in (await identify.list_suggestions("ann")).results] == [
        "First"
    ]
    assert [s.head.label for s in (await identify.list_suggestions("")).results] == [
        "Second"
    ]
    page = await identify.list_suggestions(page=2, page_size=1)
    assert ([s.head.label for s in page.results], page.previous_page) == (["Second"], 1)
    with pytest.raises(PanglossNoSuchTaskError):
        await identify.get_suggestion(uuid4())


@no_type_check
async def test_confirming_makes_it_an_identification_by_the_person(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    john, jack = await people(m, "John", "Jack")
    several = await factoid(
        m,
        "Several",
        suggested((john, 70), (jack, 30), uris=["http://example.org/not-given"]),
        toolchain=RUN,
    )
    one = await factoid(
        m,
        "One",
        suggested((john, 100), uris=["http://example.org/john"]),
        toolchain=RUN,
    )
    id = several.statements[0].by.id

    token = current_request_username.set("ann")
    try:
        done = await identify.confirm(id, "ann")
        single = await identify.confirm(one.statements[0].by.id, "ann")
    finally:
        current_request_username.reset(token)

    read = await m.Factoid.get(several.id)
    held = read.statements[0].by
    # (the same node, of another class; its target as it was)
    assert (held.type, held.id, held.identified_by) == ("Identification", id, "ann")
    assert [
        (a.label, a.edge_properties.percent) for a in held.target[0].alternatives
    ] == [("John", 70), ("Jack", 30)]
    assert (read.meta.version, read.meta.updated_by) == (2, "ann")
    rows = run(db_driver, "MATCH (n {id: $id}) RETURN labels(n) AS labels", id=str(id))
    assert "IdentificationByToolchain" not in rows[0]["labels"]
    assert (await identify.list_suggestions()).count == 0

    # the URIs go to the candidate only when there is one; with several, the identification keeps them
    assert (done.uris_added, done.queued) == ([], 0)
    assert [str(u) for u in held.uris] == ["http://example.org/not-given"]
    assert single.uris_added == ["http://example.org/john"]
    assert (await m.Factoid.get(one.id)).statements[0].by.uris == []
    assert [str(u) for u in (await m.Person.get(john)).urls] == [
        "http://example.org/john"
    ]
    assert (await m.Person.get(jack)).urls == []

    with pytest.raises(PanglossNoSuchTaskError):
        await identify.confirm(id, "ann")


def as_identification(part: dict) -> dict:
    """A suggestion as a form sends it once it is confirmed there: the same node, as an identification (with the
    URIs, if it still has several candidates)"""
    several = len(part["target"][0]["alternatives"]) > 1
    kept = {"uris": part["uris"]} if several and part.get("uris") else {}
    return {
        "type": "Identification",
        "id": part["id"],
        "target": part["target"],
        **kept,
    }


@no_type_check
async def test_uris_kept_by_an_identification_go_to_the_one_it_comes_to_be_of(
    clear_database, db_driver
):
    """Confirmed with several candidates, the identification keeps the URIs of the toolchain; a later save that
    leaves one candidate gives them to that candidate"""
    m = models()
    await toolchain(db_driver)
    john, jack = await people(m, "John", "Jack")
    uri = "http://example.org/one-of-them"
    made = await factoid(
        m, "Several", suggested((john, 70), (jack, 30), uris=[uri]), toolchain=RUN
    )
    id = made.statements[0].by.id

    token = current_request_username.set("ann")
    try:
        await identify.confirm(id, "ann")
        # (a save that changes something else: the URIs stay where they are)
        edit = (await m.Factoid.get(made.id)).model_dump()
        await m.Factoid.Update(
            id=made.id, label="Several, read", statements=edit["statements"]
        ).save(expected_version=2)
        await reconcile.background_done()
        held = (await m.Factoid.get(made.id)).statements[0].by
        assert (held.type, [str(u) for u in held.uris]) == ("Identification", [uri])
        assert (await m.Person.get(john)).urls == []
        # (it is not a task any more, and not found by its URI as one)
        assert (await identify.list_suggestions()).count == 0

        # decided: it is John
        edit = (await m.Factoid.get(made.id)).model_dump()
        statement = edit["statements"][0]
        statement["by"]["target"] = suggested((john, 100))["target"]
        await m.Factoid.Update(
            id=made.id, label="Several, decided", statements=[statement]
        ).save(expected_version=3)
    finally:
        current_request_username.reset(token)
    await reconcile.background_done()

    assert [str(u) for u in (await m.Person.get(john)).urls] == [uri]
    assert (await m.Person.get(jack)).urls == []


@no_type_check
async def test_a_document_saved_with_a_suggestion_as_an_identification_confirms_it(
    clear_database, db_driver
):
    """Confirmed in the form: the suggestion is written as an identification with the rest of what was changed"""
    m = models()
    await toolchain(db_driver)
    john, jack = await people(m, "John", "Jack")
    one = await factoid(
        m,
        "One",
        suggested((john, 100), uris=["http://example.org/john"]),
        toolchain=RUN,
    )
    several = await factoid(
        m,
        "Several",
        suggested((john, 70), (jack, 30), uris=["http://example.org/not-given"]),
        toolchain=RUN,
    )
    kept = await factoid(
        m,
        "Kept",
        suggested((jack, 100), uris=["http://example.org/jack"]),
        toolchain=RUN,
    )

    token = current_request_username.set("ann")
    try:
        for made in (one, several):
            edit = (await m.Factoid.get(made.id)).model_dump()
            statement = edit["statements"][0]
            statement["by"] = as_identification(statement["by"])
            # (with another change of the same save)
            await m.Factoid.Update(
                id=made.id, label=f"{made.label}, checked", statements=[statement]
            ).save(expected_version=1)
        # (a save that leaves the suggestion as it is confirms nothing)
        edit = (await m.Factoid.get(kept.id)).model_dump()
        await m.Factoid.Update(
            id=kept.id, label="Kept, read", statements=edit["statements"]
        ).save(expected_version=1)
    finally:
        current_request_username.reset(token)
    await reconcile.background_done()

    read = await m.Factoid.get(one.id)
    held = read.statements[0].by
    assert (read.label, read.meta.version) == ("One, checked", 2)
    assert (held.type, held.id, held.identified_by) == (
        "Identification",
        one.statements[0].by.id,
        "ann",
    )
    # the URIs go to the candidate when there is one, as when it is confirmed on its own
    assert [str(u) for u in (await m.Person.get(john)).urls] == [
        "http://example.org/john"
    ]
    assert (await m.Person.get(jack)).urls == []
    still = (await m.Factoid.get(several.id)).statements[0].by
    assert (still.type, [str(u) for u in still.uris]) == (
        "Identification",
        ["http://example.org/not-given"],
    )
    left = await identify.list_suggestions()
    assert [s.head.label for s in left.results] == ["Kept, read"]
    assert left.results[0].becomes == "Identification"


@no_type_check
async def test_the_others_are_given_what_a_form_holds(clear_database, db_driver):
    """Confirmed in a form that is not saved yet: the others ticked are done now, but not those of its document"""
    m = models()
    await toolchain(db_driver)
    john, jack = await people(m, "John", "Jack")
    by = suggested((john, 70), (jack, 30))
    mine = await m.Factoid.Create(
        label="Mine",
        statements=[
            {"type": "Activity", "label": "first", "by": by},
            {"type": "Activity", "label": "second", "by": by},
        ],
    ).save(detail=True, toolchain=RUN)
    await factoid(m, "Same", suggested((john, 70), (jack, 30)), toolchain=RUN)
    id = mine.statements[0].by.id
    offered = await identify.similar(id)
    assert sorted(s.head.label for s in offered) == ["Mine", "Same"]

    # (as the form has it: corrected to John)
    target = [
        {
            "type": "WeightedAlternative",
            "id": str(mine.statements[0].by.target[0].id),
            "alternatives": [
                {"type": "Person", "id": john, "edgeProperties": {"percent": 100}}
            ],
        }
    ]
    token = current_request_username.set("ann")
    try:
        queued = await identify.give_to_others(
            id, "ann", [s.id for s in offered], target
        )
    finally:
        current_request_username.reset(token)
    assert queued == 1
    await reconcile.background_done()

    same = (await m.Factoid.list(search_terms="Same")).results[0]
    held = (await m.Factoid.get(same.id)).statements[0].by
    assert (held.type, held.identified_by) == ("Identification", "ann")
    assert [
        (a.label, a.edge_properties.percent) for a in held.target[0].alternatives
    ] == [("John", 100)]
    # the document of the form is as it was: nothing of it was written
    read = await m.Factoid.get(mine.id)
    assert read.meta.version == 1
    assert [s.by.type for s in read.statements] == ["IdentificationByToolchain"] * 2


@no_type_check
async def test_suggestions_that_say_the_same_are_confirmed_in_one_go(
    clear_database, db_driver
):
    m = models()
    await toolchain(db_driver)
    john, jack, mary = await people(m, "John", "Jack", "Mary")
    mine = await factoid(m, "Mine", suggested((john, 70), (jack, 30)), toolchain=RUN)
    await factoid(m, "Same", suggested((john, 70), (jack, 30)), toolchain=RUN)
    await factoid(m, "Near", suggested((jack, 38), (john, 62)), toolchain=RUN)
    await factoid(m, "Far", suggested((john, 40), (jack, 60)), toolchain=RUN)
    await factoid(m, "Others", suggested((john, 70), (mary, 30)), toolchain=RUN)
    await factoid(m, "Fewer", suggested((john, 100)), toolchain=RUN)
    id = mine.statements[0].by.id

    offered = await identify.similar(id)
    assert sorted(s.head.label for s in offered) == ["Near", "Same"]
    assert offered[0].candidates and offered[0].holder.type == "Activity"

    # the person corrects theirs first (it is John, certainly), then confirms it with the others
    edit = (await m.Factoid.get(mine.id)).model_dump()
    part = edit["statements"][0]["by"]
    part["target"][0]["alternatives"] = [
        {"type": "Person", "id": john, "edge_properties": {"percent": 100}}
    ]
    await m.Factoid.Update(
        id=mine.id, label="Mine", statements=edit["statements"]
    ).save()

    done = await identify.confirm(id, "ann", also=[s.id for s in offered] + [uuid4()])
    assert done.queued == 3
    await reconcile.background_done()

    for label in ("Mine", "Same", "Near"):
        head = (await m.Factoid.list(search_terms=label)).results[0]
        held = (await m.Factoid.get(head.id)).statements[0].by
        assert (held.type, held.identified_by) == ("Identification", "ann"), label
        assert [
            (a.label, a.edge_properties.percent) for a in held.target[0].alternatives
        ] == [("John", 100)], label
    left = await identify.list_suggestions()
    assert sorted(s.head.label for s in left.results) == ["Far", "Fewer", "Others"]
    # (each alternative of the others is a node of its own document)
    rows = run(
        db_driver,
        "MATCH (w:WeightedAlternative) RETURN w.id AS id, w.head_node_id AS head",
    )
    assert len({row["id"] for row in rows}) == len(rows) == 6

    # and once it is confirmed, the others like what it is now can still be asked for
    await factoid(m, "Later", suggested((john, 100)), toolchain=RUN)
    assert sorted(s.head.label for s in await identify.similar(id)) == [
        "Fewer",
        "Later",
    ]


@no_type_check
async def test_confirming_over_the_api(clear_database, db_driver):
    from pangloss_api import create_app
    from pangloss_review import api

    from .test_api_models import client_for, logged_in

    m = models()
    await toolchain(db_driver)
    (john,) = await people(m, "John")
    mine = await factoid(m, "Mine", suggested((john, 100)), toolchain=RUN)
    await factoid(m, "Same", suggested((john, 100)), toolchain=RUN)
    id = str(mine.statements[0].by.id)

    app = create_app()
    app.include_router(api.router)
    api.configure_app(app, None)
    async with client_for(app) as client:
        assert (await client.get("/api/review/identifications")).status_code == 401
        bob = await logged_in(client, "bob")
        listed = (await client.get("/api/review/identifications", headers=bob)).json()
        assert listed["count"] == 2
        assert listed["results"][0]["candidates"] == [
            {"type": "Person", "id": str(john), "label": "John", "percent": 100}
        ]
        assert listed["results"][0]["identifiedBy"] == "extractor"
        counts = await client.get("/api/review/tasks/summary", headers=bob)
        assert counts.json() == {
            "documents": 2,
            "reconciliations": 0,
            "identifications": 2,
        }
        mine_only = await client.get(
            "/api/review/tasks/summary", headers=bob, params={"assigned_to": "me"}
        )
        assert mine_only.json()["identifications"] == 0

        similar = (
            await client.get(f"/api/review/identifications/{id}/similar", headers=bob)
        ).json()
        assert [s["head"]["label"] for s in similar] == ["Same"]
        done = await client.post(
            f"/api/review/identifications/{id}/confirm",
            headers=bob,
            json={"also": [similar[0]["id"]]},
        )
        assert done.status_code == 200, done.text
        assert done.json()["queued"] == 1
        await reconcile.background_done()
        after = (await client.get("/api/review/identifications", headers=bob)).json()
        assert after["count"] == 0
        read = (await client.get(f"/api/Factoid/{mine.id}", headers=bob)).json()
        held = read["statements"][0]["by"]
        assert (held["type"], held["identifiedBy"]) == ("Identification", "bob")
        gone = await client.post(
            f"/api/review/identifications/{id}/confirm", headers=bob, json={}
        )
        assert gone.status_code == 404


def models_with_subclasses(confirmed_as=None):
    """A project's own kind of suggestion (`SuggestedReading`) and the identification it becomes (`Reading`)"""
    import pangloss_library.models
    import pangloss_review.models

    importlib.reload(pangloss_review.models)
    importlib.reload(pangloss_library.models)
    library = pangloss_library.models
    Alternatives = library.WeightedAlternative

    class Person(Entity):
        pass

    class Reading[T](library.Identification[T]):
        note: str | None = None

    becomes = Reading if confirmed_as is None else confirmed_as

    class SuggestedReading[T](library.IdentificationByToolchain[T]):
        confirmed_as = becomes
        note: str | None = None
        # (of the suggestion only)
        model: str | None = None

    class Activity(Document):
        _meta = Document.Meta(create_directly=False)
        by: (
            Person
            | Reading[Alternatives[Person]]  # ty: ignore[invalid-type-form]
            | SuggestedReading[Alternatives[Person]]  # ty: ignore[invalid-type-form]
        )

    class Factoid(Document):
        _review_meta = ReviewMeta(reviewable=True)
        statements: list[Activity]

    initialise()
    return SimpleNamespace(Person=Person, Activity=Activity, Factoid=Factoid)


@no_type_check
async def test_a_subclass_is_a_suggestion_too_and_becomes_the_class_it_names(
    clear_database, db_driver
):
    m = models_with_subclasses()
    await toolchain(db_driver)
    current_request_username.set("ann")
    [smith] = await people(m, "John Smith")
    factoid = await m.Factoid.Create(
        label="A sale",
        statements=[
            {
                "type": "Activity",
                "label": "Selling",
                "by": {
                    **suggested((smith, 100)),
                    "type": "SuggestedReading",
                    "note": "the hand is unclear",
                    "model": "ner-large",
                },
            }
        ],
    ).save(toolchain=RUN)

    # it is listed as any suggestion is, with the class it is
    listed = await identify.list_suggestions(None, 1, 25)
    assert [(s.type, s.identified_by) for s in listed.results] == [
        ("SuggestedReading", "extractor")
    ]
    await identify.confirm(listed.results[0].id, "bob")

    # the class its class names, with the field the two share; what is the suggestion's alone is gone
    read = await m.Factoid.get(factoid.id)
    by = read.statements[0].by
    assert (by.type, by.identified_by, by.note) == (
        "Reading",
        "bob",
        "the hand is unclear",
    )
    assert not hasattr(by, "model")
    assert [a.id for a in by.target[0].alternatives] == [smith]
    assert (await identify.list_suggestions(None, 1, 25)).count == 0


@no_type_check
@pytest.mark.parametrize(
    ("confirmed_as", "reason"),
    [("Nothing", "which is not a model"), ("SuggestedReading", "cannot become")],
)
async def test_a_subclass_has_to_name_an_identification_to_become(
    clear_database, db_driver, confirmed_as, reason
):
    from pangloss_models import PanglossModelError

    with pytest.raises(PanglossModelError, match=reason):
        models_with_subclasses(confirmed_as)
