"""The candidates of an unknown, and the two routes, on the backend under test (implementation_docs/reconcile.md;
implementation_docs/similarity-build-plan.md, step 10.2c).

On `pangloss_testing.similar_models` with its stand-in `Mention` (`declare(stand_in=True)`), the graph, name and class
parts, and the profile `who` (name 1, graph 0.25: the conftest): a small world with two people of one name, Jon
Smyth, in different company (one met Ada and Ben, the other Cy and Dee), and a payload that names a third Jon Smyth,
not identified, beside Ben at a meeting of Ada's. What is claimed: nothing is written, on any path; the namesake who
keeps the unknown's company comes first; a reader sees what they may; an entity merged into another is no candidate;
a payload that would be refused is refused as its create refuses it; the stored route gives what the payload route
gives for the same document."""

import importlib
from types import SimpleNamespace
from typing import Any, no_type_check
from uuid import UUID, uuid4, uuid7

import httpx2 as httpx
import pangloss_core.settings as core_settings
import pytest
import pytest_asyncio
from pangloss_api import create_app
from pangloss_models import hooks
from pangloss_testing.live import run
from pangloss_testing.parts import drop_vector_indexes, one_turn
from pangloss_testing.similar_models import mention_stand_in
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"
NAME = "Jon Smyth"
ROUTE = "/api/reconcile/candidates"


@pytest.fixture
def database(db_driver, clear_database):
    """(the database emptied, and the vector indexes the tests made dropped, before and after; `Mention` a stand-in
    for the whole test: which classes have vectors depends on it)"""
    drop_vector_indexes(db_driver)
    stand_in = mention_stand_in()
    hooks.stand_ins.append(stand_in)
    yield db_driver
    hooks.stand_ins.remove(stand_in)
    drop_vector_indexes(db_driver)


class MadeWhenFirstAsked:
    """The app, made at its first request: after the test has declared its models, whose routes it makes when it is
    made (`POST /api/Factoid`)"""

    def __init__(self) -> None:
        self.app: Any = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if self.app is None:
            self.app = create_app()
        await self.app(scope, receive, send)


@pytest_asyncio.fixture(loop_scope="session")
async def client(database):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=MadeWhenFirstAsked()),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
def announced():
    """The write events announced while the test runs"""
    found: list[Any] = []
    hooks.after_write.append(found.append)
    yield found
    hooks.after_write.remove(found.append)


async def bearer(client) -> dict:
    await service.create_user("root", "root@example.com", PASSWORD, admin=True)
    response = await client.post(
        "/api/users/token", data={"username": "root", "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def counts(db_driver) -> tuple[int, int, int]:
    """The nodes, the edges and the `PGPending` marks"""
    return (
        run(db_driver, "MATCH (n) RETURN count(n) AS n")[0]["n"],
        run(db_driver, "MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"],
        run(db_driver, "MATCH (p:PGPending) RETURN count(p) AS n")[0]["n"],
    )


def ref(id: str, kind: str = "Person") -> dict[str, str]:
    return {"type": kind, "id": str(id)}


def meeting(
    by: Any, guests: list[Any], at: str | None = None, label: str = "a meeting"
) -> dict[str, Any]:
    guest: dict[str, Any] = {"type": "InRole", "role": "guest", "target": guests}
    if at is not None:
        guest["at"] = ref(at, "Place")
    return {
        "type": "Activity",
        "label": label,
        "carried_out_by": by,
        "participants": [guest],
    }


@no_type_check
async def world(m, published: bool | None = None) -> dict[str, str]:
    """Ada, Ben, Cy and Dee; the mill and the ford; Jon Smyth who met Ada and Ben at the mill (twice), and Jon Smyth
    who met Cy and Dee at the ford (twice): the ids by name (`jon`, the first Jon; `namesake`, the second)"""
    ids = {}
    for name in ["Ada", "Ben", "Cy", "Dee"]:
        ids[name] = str((await m.Person.Create(label=name).save()).id)
    for name in ["mill", "ford"]:
        ids[name] = str((await m.Place.Create(label=f"the {name}").save()).id)
    ids["jon"] = str((await m.Person.Create(label=NAME).save()).id)
    ids["namesake"] = str((await m.Person.Create(label=NAME).save()).id)
    options = {} if published is None else {"published": published}
    for jon, (first, second), place in [
        ("jon", ("Ada", "Ben"), "mill"),
        ("namesake", ("Cy", "Dee"), "ford"),
    ]:
        for n in range(2):
            await m.Factoid.Create(
                label=f"{jon} {n}",
                statements=[
                    meeting(
                        ref(ids[jon]),
                        [ref(ids[first]), ref(ids[second])],
                        ids[place],
                    )
                ],
            ).save(**options)
    return ids


async def built(m, database, published: bool | None = None) -> dict[str, str]:
    """The world written, every part rebuilt, and the marks of the writes worked off"""
    from pangloss_vectors.rebuild import rebuild

    ids = await world(m, published)
    await rebuild()
    await one_turn(database)
    return ids


MENTION = {"type": "Mention", "label": NAME, "mentioned_type": "Person"}


def asked(ids: dict[str, str], *guests: Any) -> dict[str, Any]:
    """A factoid: Ada met Ben and Jon Smyth, who is not identified, at the mill (or these guests, beside him)"""
    return {
        "type": "Factoid",
        "label": "Ada met Ben and Jon",
        "statements": [
            meeting(
                ref(ids["Ada"]),
                [*(guests or [ref(ids["Ben"])]), MENTION],
                ids["mill"],
            )
        ],
    }


@no_type_check
async def saved(m, body: dict[str, Any], **options: Any) -> dict[str, str]:
    """The payload written: the ids of the factoid (`head`), its meeting and its mention of Jon Smyth, as stored"""
    view = await m.Factoid.Create(**body).save(detail=True, **options)
    statement = view.statements[0]
    (mention,) = [
        str(target.id)
        for target in statement.participants[0].target
        if target.type == "Mention" and target.label == NAME
    ]
    return {"head": str(view.id), "meeting": str(statement.id), "mention": mention}


@pytest.fixture
def same_ids(monkeypatch):
    """`again()`: the ids made from now on for what a payload gives none come from one list, from its start (so a
    payload planned and then written is written with the ids of its plan: the graph part's vectors start from the
    ids, `pangloss_fastrp.maths.seeds`)"""
    from pangloss_models.model_bases import model_tools

    made = [uuid7() for _ in range(100)]
    taken = [0]

    def next_id() -> UUID:
        taken[0] += 1
        return made[taken[0] - 1]

    def again() -> None:
        monkeypatch.setattr(model_tools, "uuid7", next_id)
        taken[0] = 0

    return again


def candidate_ids(answer: dict[str, Any]) -> list[str]:
    (unknown,) = answer["unknowns"]
    return [candidate["id"] for candidate in unknown["candidates"]]


# ---------------------------------------------------------------------------
# Nothing is written
# ---------------------------------------------------------------------------


@no_type_check
async def test_nothing_is_written_by_candidates_of_nor_by_either_route(
    database, client, announced
):
    from pangloss_cypher.write_functions import checked_create
    from pangloss_reconcile import candidates_of
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)
    announced.clear()
    before = counts(database)

    _, plan, _ = await checked_create(m.Factoid.Create(**asked(ids)))
    found = await candidates_of(plan, see_unpublished=True)
    assert [candidate.id for candidate in found[0].candidates][:2] == [
        ids["jon"],
        ids["namesake"],
    ]
    assert counts(database) == before

    response = await client.post(ROUTE, json=asked(ids), headers=headers)
    assert response.status_code == 200, response.text
    assert counts(database) == before
    assert announced == []

    stored = await saved(m, asked(ids))
    assert announced, "(a write is announced: the test would see one)"
    announced.clear()
    before = counts(database)
    response = await client.get(f"{ROUTE}/{stored['mention']}", headers=headers)
    assert response.status_code == 200, response.text
    assert candidate_ids(response.json())[:2] == [ids["jon"], ids["namesake"]]
    assert counts(database) == before
    assert announced == []


@no_type_check
async def test_each_refused_request_is_refused_as_its_create_is_and_writes_nothing(
    database, client, announced
):
    """A body that does not validate, a reference to an entity that is not there, an id taken, and a reader who is
    not logged in: the same status and the same answer as `POST /api/Factoid` of the same body, and nothing written"""
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)
    stored = await saved(m, asked(ids))
    # (a new person, given the id of the stored factoid)
    taken = {"type": "Person", "id": stored["head"], "create_new": True, "label": "Eve"}
    refused = {
        "does not validate": (
            {"type": "Factoid", "label": "no statements"},
            headers,
        ),
        "a field of the wrong kind": (
            {**asked(ids), "statements": "none"},
            headers,
        ),
        "a reference to no entity": (
            asked({**ids, "Ben": str(uuid4())}),
            headers,
        ),
        "an id taken": (asked(ids, taken), headers),
        "not logged in": (asked(ids), {}),
    }
    announced.clear()
    before = counts(database)
    for name, (body, sent) in refused.items():
        asking = await client.post(ROUTE, json=body, headers=sent)
        assert counts(database) == before, name
        creating = await client.post("/api/Factoid", json=body, headers=sent)
        assert asking.status_code == creating.status_code, (name, asking.text)
        assert asking.status_code >= 400, name
        assert asking.json() == creating.json(), name
    assert counts(database) == before
    assert announced == []


@no_type_check
async def test_a_body_of_no_class_that_can_be_created_is_a_422_that_names_it(
    database, client
):
    from pangloss_testing.similar_models import declare

    declare(stand_in=True)
    headers = await bearer(client)
    for kind in ["Nothing", "Mention", "Statement"]:
        response = await client.post(
            ROUTE, json={"type": kind, "label": "x"}, headers=headers
        )
        assert response.status_code == 422, (kind, response.text)
        assert kind in response.json()["detail"]
    response = await client.post(ROUTE, json={"label": "x"}, headers=headers)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# The candidates
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_namesake_who_keeps_the_unknown_s_company_is_first_and_each_has_the_scores_of_its_parts(
    database, client
):
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)

    response = await client.post(ROUTE, json=asked(ids), headers=headers)

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["status"] == "ok"
    assert answer["profile"] == "who"
    (unknown,) = answer["unknowns"]
    assert {key: unknown[key] for key in ["type", "label"]} == {
        "type": "Person",
        "label": NAME,
    }
    first, second, *rest = unknown["candidates"]
    assert [first["id"], second["id"]] == [ids["jon"], ids["namesake"]]
    for candidate in (first, second):
        # (the reference view, as a list gives it, with the scores)
        assert candidate["type"] == "Person"
        assert candidate["label"] == NAME
        assert set(candidate["scores"]) == {"name", "graph"}
        assert candidate["scores"]["name"] == pytest.approx(1.0)
        # (by the profile's weights: name 1, graph 0.25)
        assert candidate["score"] == pytest.approx(
            (candidate["scores"]["name"] + 0.25 * candidate["scores"]["graph"]) / 1.25
        )
    assert first["scores"]["graph"] > second["scores"]["graph"]
    scores = [candidate["score"] for candidate in unknown["candidates"]]
    assert scores == sorted(scores, reverse=True)
    # (Ada, Ben, Cy and Dee are found by the graph, and are far by the name)
    assert {candidate["id"] for candidate in rest} <= {
        ids[name] for name in ["Ada", "Ben", "Cy", "Dee"]
    }
    assert all(candidate["score"] < second["score"] for candidate in rest)

    limited = await client.post(f"{ROUTE}?limit=1", json=asked(ids), headers=headers)
    assert candidate_ids(limited.json()) == [ids["jon"]]


@no_type_check
async def test_an_entity_merged_into_another_is_no_candidate_and_its_survivor_is(
    database, client
):
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)
    await m.Person.merge(absorb=ids["jon"], into=ids["namesake"])

    response = await client.post(ROUTE, json=asked(ids), headers=headers)

    assert response.status_code == 200, response.text
    found = candidate_ids(response.json())
    assert ids["jon"] not in found
    assert ids["namesake"] in found


@no_type_check
async def test_the_stored_route_gives_what_the_payload_route_gives_for_the_same_document(
    database, client, same_ids
):
    """The payload asked by POST, then written with the ids of that plan (`same_ids`: the graph part's vectors start
    from the ids), then its stand-in asked by GET: the same candidates in the same order, with the same scores; none
    of them the document or a part of it"""
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)
    body = asked(ids)

    same_ids()
    by_payload = await client.post(ROUTE, json=body, headers=headers)
    same_ids()
    written = await saved(m, body)
    assert by_payload.json()["unknowns"][0]["id"] == written["mention"]
    by_id = await client.get(f"{ROUTE}/{written['mention']}", headers=headers)

    assert by_payload.status_code == by_id.status_code == 200, by_id.text
    payload, stored = by_payload.json(), by_id.json()
    assert payload["status"] == stored["status"] == "ok"
    ((one,), (other,)) = payload["unknowns"], stored["unknowns"]
    assert {k: one[k] for k in ["id", "type", "label"]} == {
        k: other[k] for k in ["id", "type", "label"]
    }
    assert [c["id"] for c in one["candidates"]] == [
        c["id"] for c in other["candidates"]
    ]
    assert one["candidates"][0]["id"] == ids["jon"]
    for mine, theirs in zip(one["candidates"], other["candidates"], strict=True):
        assert mine["score"] == pytest.approx(theirs["score"], abs=1e-5)
        assert set(mine["scores"]) == set(theirs["scores"])
        for part, score in mine["scores"].items():
            assert score == pytest.approx(theirs["scores"][part], abs=1e-5), part
    assert not set(written.values()) & {c["id"] for c in other["candidates"]}


@no_type_check
async def test_the_stored_route_is_a_404_for_what_is_no_stored_unknown(
    database, client
):
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    given = await saved(m, asked(ids))
    headers = await bearer(client)

    for id in [str(uuid4()), given["meeting"], given["head"], ids["Ada"]]:
        response = await client.get(f"{ROUTE}/{id}", headers=headers)
        assert response.status_code == 404, (id, response.text)
    answered = await client.get(f"{ROUTE}/{given['mention']}", headers=headers)
    assert answered.status_code == 200


@no_type_check
async def test_a_profile_never_built_says_so_and_lists_no_candidate(database, client):
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await world(m)
    headers = await bearer(client)

    response = await client.post(ROUTE, json=asked(ids), headers=headers)

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["status"] == "pending"
    (unknown,) = answer["unknowns"]
    assert unknown["label"] == NAME
    assert unknown["candidates"] == []


# ---------------------------------------------------------------------------
# What a reader who is not logged in sees
# ---------------------------------------------------------------------------


@pytest.fixture
def searches(monkeypatch):
    """How many times the parts were asked of unknowns, and searches made"""
    from pangloss_vectors import parts, search

    made = {"asked": 0, "searched": 0}
    asking, searching = parts.unknown_vectors, search.nearest

    async def asked_of(*args, **kwargs):
        made["asked"] += 1
        return await asking(*args, **kwargs)

    async def searched(*args, **kwargs):
        made["searched"] += 1
        return await searching(*args, **kwargs)

    monkeypatch.setattr(parts, "unknown_vectors", asked_of)
    monkeypatch.setattr(search, "nearest", searched)
    return made


@no_type_check
async def test_a_reader_who_is_not_logged_in_is_refused_by_both_routes_and_nothing_is_computed(
    database, client, searches
):
    """Reconciling is the work of people logged in: 401 on both routes, as the create is, and no part asked"""
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    stored = await saved(m, asked(ids))

    asking = await client.post(ROUTE, json=asked(ids))
    creating = await client.post("/api/Factoid", json=asked(ids))
    assert asking.status_code == creating.status_code == 401
    assert asking.json() == creating.json()
    assert (await client.get(f"{ROUTE}/{stored['mention']}")).status_code == 401
    assert searches == {"asked": 0, "searched": 0}


@no_type_check
async def test_below_the_routes_a_stand_in_of_an_unpublished_document_is_no_plan_for_a_reader_who_may_not_see_it(
    database,
):
    """(so that the rule holds if a route is opened later) `stored_plan` as a reader who may not see what is not
    published: None for a stand-in of an unpublished document, a plan for one of a published document, whose
    candidates are those the reader may see. (A candidate is an entity of the class the stand-in names, and an
    entity is never unpublished: no unpublished candidate can arise)"""
    from pangloss_reconcile import candidates_of
    from pangloss_reconcile.stored import stored_plan
    from pangloss_testing.similar_models import declare
    from pangloss_users import see_unpublished

    m = declare(reviewed=True, stand_in=True)
    ids = await built(m, database, published=True)
    hidden = await saved(m, asked(ids))
    shown = await saved(m, asked(ids), published=True)

    token = see_unpublished.set(False)
    try:
        assert await stored_plan(hidden["mention"]) is None
        plan = await stored_plan(shown["mention"])
        assert plan is not None
        (found,) = await candidates_of(
            plan, see_unpublished=False, only=[shown["mention"]]
        )
    finally:
        see_unpublished.reset(token)
    assert found.candidates[0].id == ids["jon"]
    assert all(c.type == "Person" for c in found.candidates)
    assert await stored_plan(hidden["mention"]) is not None


# ---------------------------------------------------------------------------
# Limits, and documents that cannot be planned
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_payload_with_more_unknowns_than_the_most_is_refused_before_any_part_is_asked(
    database, client, searches, monkeypatch
):
    from pangloss_reconcile import TooManyUnknowns, candidates_of
    from pangloss_testing.similar_models import declare

    monkeypatch.setattr(core_settings.SETTINGS, "RECONCILE_MOST_UNKNOWNS", 1)
    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)
    body = asked(ids, ref(ids["Ben"]), {**MENTION, "label": "Hal Unknown"})

    response = await client.post(ROUTE, json=body, headers=headers)

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == (
        "The document has 2 unknowns, and at most 1 are asked about at once (RECONCILE_MOST_UNKNOWNS)"
    )
    assert searches == {"asked": 0, "searched": 0}
    from pangloss_cypher.write_functions import checked_create

    _, plan, _ = await checked_create(m.Factoid.Create(**body))
    with pytest.raises(TooManyUnknowns):
        await candidates_of(plan, see_unpublished=True)


@no_type_check
async def test_a_stored_document_with_more_unknowns_than_the_most_answers_for_the_one_asked_by_it_alone(
    database, client, monkeypatch
):
    from pangloss_vectors import parts

    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)
    stored = await saved(
        m, asked(ids, ref(ids["Ben"]), {**MENTION, "label": "Hal Unknown"})
    )
    of = []
    asking = parts.unknown_vectors

    async def asked_of(plan, unknowns):
        of.append([u.id for u in unknowns])
        return await asking(plan, unknowns)

    monkeypatch.setattr(parts, "unknown_vectors", asked_of)

    below = await client.get(f"{ROUTE}/{stored['mention']}", headers=headers)
    monkeypatch.setattr(core_settings.SETTINGS, "RECONCILE_MOST_UNKNOWNS", 1)
    above = await client.get(f"{ROUTE}/{stored['mention']}", headers=headers)

    assert below.status_code == above.status_code == 200, above.text
    assert [len(asked) for asked in of] == [2, 1]
    assert of[1] == [stored["mention"]]
    assert candidate_ids(above.json())[0] == ids["jon"]


@pytest.mark.parametrize("fault", ["the update", "the database model", "a reference"])
@no_type_check
async def test_a_stored_document_that_cannot_be_planned_is_a_404_with_its_reason_logged(
    database, client, monkeypatch, caplog, fault
):
    """What would refuse the stored document as an update (the `Update` not taking its view, a validator or a
    label of the database model, a reference the graph part cannot resolve) is no refusal of a write here: a 404
    with one message, and a warning that says why"""
    from pangloss_cypher import write_functions
    from pangloss_models import PanglossReferenceError, PanglossWriteRefused
    from pangloss_models import utils
    from pangloss_vectors import parts

    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)
    stored = await saved(m, asked(ids))

    def refused(*args, **kwargs):
        raise PanglossWriteRefused("refused here")

    async def unresolved(*args, **kwargs):
        raise PanglossReferenceError("no such entity here")

    if fault == "the update":
        monkeypatch.setattr(utils, "editable", lambda view: {})
    elif fault == "the database model":
        monkeypatch.setattr(write_functions, "to_db_model", refused)
    else:
        monkeypatch.setattr(parts, "unknown_vectors", unresolved)

    with caplog.at_level("WARNING", logger="pangloss.reconcile"):
        response = await client.get(f"{ROUTE}/{stored['mention']}", headers=headers)

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == (
        f"The document of the stand-in {stored['mention']} cannot be planned as it is stored"
    )
    assert any("cannot be found" in record.getMessage() for record in caplog.records), (
        caplog.text
    )


# ---------------------------------------------------------------------------
# Review's own `Unreconciled`
# ---------------------------------------------------------------------------


@no_type_check
def reviewed_models():
    """As review's tests declare them: people who may be unreconciled, and a reviewed factoid of meetings"""
    import pangloss_criteria.models
    import pangloss_library.models
    import pangloss_review.models
    from pangloss_models import Document, Entity, ModelRegistry, initialise
    from pangloss_review import ReviewMeta

    ModelRegistry._reset()
    # (the registry was reset, and a module is only run once: the packages' models are declared again)
    importlib.reload(pangloss_library.models)
    importlib.reload(pangloss_criteria.models)
    importlib.reload(pangloss_review.models)

    class Person(Entity):
        _review_meta = ReviewMeta(allow_unreconciled=True)

    class Meeting(Document):
        _meta = Document.Meta(create_directly=False)
        by: Person
        met: list[Person]

    class Factoid(Document):
        _review_meta = ReviewMeta(reviewable=True)
        statements: list[Meeting]

    initialise()
    return SimpleNamespace(Person=Person, Meeting=Meeting, Factoid=Factoid)


def reviewed_meeting(by: str, met: list[Any]) -> dict[str, Any]:
    return {"type": "Meeting", "label": "a meeting", "by": by, "met": met}


@no_type_check
async def test_review_s_unreconciled_in_an_unpublished_payload_gets_candidates_by_name_and_by_graph(
    db_driver, clear_database, client
):
    """At `VECTORS_GRAPH_SEES = "everyone"`: the payload's head is unpublished (a reviewed class), and its unknown is
    still laid over the graph as if it were published, so a logged-in reader is given candidates by both"""
    from pangloss_cypher.write_functions import checked_create
    from pangloss_reconcile import candidates_of
    from pangloss_vectors.rebuild import rebuild

    drop_vector_indexes(db_driver)
    m = reviewed_models()
    ids = {}
    for name in ["Ada", "Ben", "Cy", "Dee"]:
        ids[name] = str((await m.Person.Create(label=name).save()).id)
    ids["jon"] = str((await m.Person.Create(label=NAME).save()).id)
    ids["namesake"] = str((await m.Person.Create(label=NAME).save()).id)
    for jon, (first, second) in [("jon", ("Ada", "Ben")), ("namesake", ("Cy", "Dee"))]:
        for _ in range(2):
            await m.Factoid.Create(
                label=jon,
                statements=[
                    reviewed_meeting(ref(ids[jon]), [ref(ids[first]), ref(ids[second])])
                ],
            ).save(published=True)
    await rebuild()
    await one_turn(db_driver)
    headers = await bearer(client)
    unknown = {"type": "Unreconciled", "label": NAME, "unreconciled_type": "Person"}
    body = {
        "type": "Factoid",
        "label": "Ada met Ben and Jon",
        "statements": [reviewed_meeting(ref(ids["Ada"]), [ref(ids["Ben"]), unknown])],
    }
    before = counts(db_driver)

    _, plan, _ = await checked_create(m.Factoid.Create(**body))
    assert plan.head.properties["published"] is False
    (found,) = await candidates_of(plan, see_unpublished=True)
    response = await client.post(ROUTE, json=body, headers=headers)

    assert counts(db_driver) == before
    first, second = found.candidates[:2]
    assert [first.id, second.id] == [ids["jon"], ids["namesake"]]
    assert first.scores["name"] == pytest.approx(1.0)
    assert first.scores["graph"] > second.scores["graph"] > -1
    assert first.scores["graph"] > 0
    assert response.status_code == 200, response.text
    assert candidate_ids(response.json())[:2] == [ids["jon"], ids["namesake"]]
    drop_vector_indexes(db_driver)


# ---------------------------------------------------------------------------
# Reasons: what a candidate shares with the payload
# ---------------------------------------------------------------------------


def shared_of(answer: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Each candidate's shared entities, by id: the documents of each"""
    (unknown,) = answer["unknowns"]
    return {
        c["id"]: {s["id"]: s["documents"] for s in c["shared"]}
        for c in unknown["candidates"]
    }


@no_type_check
async def test_the_namesake_who_keeps_the_unknown_s_company_shares_the_place_and_the_others_and_the_other_namesake_nothing(
    database, client
):
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)

    response = await client.post(ROUTE, json=asked(ids), headers=headers)

    assert response.status_code == 200, response.text
    found = shared_of(response.json())
    # (the payload names Ada, Ben and the mill: Jon met the three of them in two documents)
    assert found[ids["jon"]] == {ids["Ada"]: 2, ids["Ben"]: 2, ids["mill"]: 2}
    assert found[ids["namesake"]] == {}
    first = response.json()["unknowns"][0]["candidates"][0]
    # (each a reference view, with how many documents)
    assert {s["label"] for s in first["shared"]} == {"Ada", "Ben", "the mill"}
    # (the score is not changed by them: as the parts give it)
    assert first["score"] == pytest.approx(
        (first["scores"]["name"] + 0.25 * first["scores"]["graph"]) / 1.25
    )


@no_type_check
async def test_reasons_are_cut_to_the_most_those_of_most_documents_first_and_none_are_asked_at_0(
    database, client, monkeypatch
):
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)
    # (a third document with Jon and Ada alone)
    await m.Factoid.Create(
        label="jon 2", statements=[meeting(ref(ids["jon"]), [ref(ids["Ada"])])]
    ).save()

    monkeypatch.setattr(core_settings.SETTINGS, "RECONCILE_REASONS", 2)
    two = await client.post(ROUTE, json=asked(ids), headers=headers)
    monkeypatch.setattr(core_settings.SETTINGS, "RECONCILE_REASONS", 0)
    none = await client.post(ROUTE, json=asked(ids), headers=headers)

    (jon,) = [
        c for c in two.json()["unknowns"][0]["candidates"] if c["id"] == ids["jon"]
    ]
    expected = sorted([ids["Ben"], ids["mill"]])[0]
    assert [(s["id"], s["documents"]) for s in jon["shared"]] == [
        (ids["Ada"], 3),
        (expected, 2),
    ]
    assert all(c["shared"] == [] for c in none.json()["unknowns"][0]["candidates"])


@no_type_check
async def test_an_unpublished_document_is_no_reason_for_a_reader_who_may_not_see_it_and_a_deleted_one_for_no_one(
    database,
):
    """Below the routes (both need a login, and a reader logged in sees what is not published): the document that
    is the namesake's only reason, unpublished, counts only for a reader who may see it; deleted, for no one"""
    from pangloss_cypher.write_functions import checked_create
    from pangloss_reconcile.reasons import shared
    from pangloss_testing.similar_models import declare

    m = declare(reviewed=True, stand_in=True)
    ids = await built(m, database, published=True)
    hidden = await m.Factoid.Create(
        label="namesake met Ada",
        statements=[meeting(ref(ids["namesake"]), [ref(ids["Ada"])])],
    ).save()
    gone = await m.Factoid.Create(
        label="namesake met Ben",
        statements=[meeting(ref(ids["namesake"]), [ref(ids["Ben"])])],
    ).save(published=True)
    await m.Factoid.delete(gone.id)
    _, plan, _ = await checked_create(m.Factoid.Create(**asked(ids)))

    assert await shared(plan, [ids["namesake"]], False, 5) == {}
    assert await shared(plan, [ids["namesake"]], True, 5) == {
        ids["namesake"]: [(ids["Ada"], 1)]
    }
    assert hidden.id


@no_type_check
async def test_an_entity_merged_into_another_counts_as_its_survivor(database, client):
    """A merge moves the references to the absorbed entity onto its survivor (the stored edges of the documents
    that named it lead to the survivor after it), and a payload that names the absorbed one is read as naming the
    survivor (as the write would): so the survivor is shared, in the documents of both"""
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)
    ids["Eve"] = str((await m.Person.Create(label="Eve").save()).id)
    await m.Factoid.Create(
        label="jon met Eve", statements=[meeting(ref(ids["jon"]), [ref(ids["Eve"])])]
    ).save()
    await m.Person.merge(absorb=ids["Eve"], into=ids["Ben"])
    edges = run(
        database,
        "MATCH (:PGIndexableNode {id: $eve})<-[e]-(:PGIndexableNode) "
        "WHERE NOT coalesce(e.reverse, false) RETURN count(e) AS n",
        eve=ids["Eve"],
    )[0]["n"]
    assert edges == 0, "the merge left a forward edge to the absorbed entity"

    response = await client.post(
        ROUTE, json=asked(ids, ref(ids["Eve"])), headers=headers
    )

    assert response.status_code == 200, response.text
    found = shared_of(response.json())[ids["jon"]]
    assert ids["Eve"] not in found
    assert found[ids["Ben"]] == 3


@no_type_check
async def test_the_stored_route_does_not_count_the_document_itself(database, client):
    from pangloss_testing.similar_models import declare

    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)
    # (the stored document names Jon too, beside the mention: by the payload it would be a document of Jon's)
    body = asked(ids, ref(ids["Ben"]), ref(ids["jon"]))
    stored = await saved(m, body)

    response = await client.get(f"{ROUTE}/{stored['mention']}", headers=headers)

    assert response.status_code == 200, response.text
    found = shared_of(response.json())
    assert found[ids["jon"]] == {ids["Ada"]: 2, ids["Ben"]: 2, ids["mill"]: 2}


# ---------------------------------------------------------------------------
# What a request costs
# ---------------------------------------------------------------------------

# What one POST with one unknown runs (measured 2026-11-22, on Memgraph), a change that adds a round trip failing
# here: 13 read transactions (the login, twice, as every request that needs one: the visibility and the user, each
# a user and a revoked session; `checked_create`'s checks; the graph part's lay-out, 33 statements of its 57, over
# this small world; the name part's table of rarity; a search by each of the two parts; their vectors, a part each;
# the states of the profile; the reference views); and, since step 10.3, the reasons (`reasons.shared`): one read
# transaction more, of two statements (the plan's references checked as a write resolves them, and the query))
POST_TRANSACTIONS = 14
POST_STATEMENTS = 59


@pytest.mark.parametrize("reasons", [5, 0])
@no_type_check
async def test_a_post_with_one_unknown_runs_its_budget_of_transactions_and_statements(
    database, client, monkeypatch, reasons
):
    """(and without the reasons, `RECONCILE_REASONS = 0`, one transaction and two statements fewer: the reasons are
    that one read)"""
    from pangloss_testing.conformance.test_query_costs import recorded
    from pangloss_testing.similar_models import declare

    monkeypatch.setattr(core_settings.SETTINGS, "RECONCILE_REASONS", reasons)
    m = declare(stand_in=True)
    ids = await built(m, database)
    headers = await bearer(client)
    body = asked(ids)
    # (once before, so that what is read once for a process is read)
    await client.post(ROUTE, json=body, headers=headers)

    with recorded() as found:
        response = await client.post(ROUTE, json=body, headers=headers)

    assert response.status_code == 200, response.text
    fewer = 0 if reasons else 1
    assert (found.transactions, len(found.statements)) == (
        POST_TRANSACTIONS - fewer,
        POST_STATEMENTS - 2 * fewer,
    )
