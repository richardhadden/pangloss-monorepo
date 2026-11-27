"""The pairs through near entities over the API, `GET /api/compare/{type}/{ref}?near=true` (`pangloss_compare.near`,
`compare.compare_near`; implementation_docs/spaces-and-comparison-plan.md, step 6.4), on the backend under test, with
`similar_models.declare(compared=True, ...)`, the graph and name parts and the profile `who` of the conftest: two
namesakes' births pair only so, with both people in the reason; a birth told otherwise disagrees and a gathering a
century off is not given; a pair by rule is not given again; never through a stand-in; a merged entity; what the
reader may see; the states (`none`, `pending`); the floor and `k`; a judgement overriding; nothing written; and what
one lookup costs."""

from typing import Any, no_type_check
from uuid import uuid4

import httpx2 as httpx
import pytest
from pangloss_api import create_app
from pangloss_compare.compare import compare_near
from pangloss_core import settings as core_settings
from pangloss_models import hooks
from pangloss_testing.live import run
from pangloss_testing.parts import drop_vector_indexes, one_turn
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"
ADA = "Ada Lovelace"


@pytest.fixture
def database(db_driver, clear_database):
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    )


def ref(id: str, kind: str = "Person") -> dict[str, str]:
    return {"type": kind, "id": id}


def day(year: int, month: int | None = None, number: int | None = None) -> dict:
    said: dict[str, Any] = {"type": "ExactDate", "year": year}
    if month is not None:
        said["month"] = month
    if number is not None:
        said["day"] = number
    return said


def birth(label: str, person: Any, place: str, year: int) -> dict:
    return {
        "type": "Birth",
        "label": label,
        "when": day(year),
        "person": person if isinstance(person, dict) else ref(person),
        "place": ref(place, "Place"),
    }


def activity(label: str, by: str, participant: str, when: dict) -> dict:
    return {
        "type": "Activity",
        "label": label,
        "when": when,
        "carried_out_by": ref(by),
        "participants": [
            {"type": "InRole", "role": "guest", "target": [ref(participant)]}
        ],  # fmt: skip
    }


@no_type_check
async def people(m, **labels: str) -> dict[str, str]:
    ids = {key: str((await m.Person.Create(label=label).save()).id) for key, label in labels.items()}  # fmt: skip
    ids["mill"] = str((await m.Place.Create(label="the mill").save()).id)
    ids["rome"] = str((await m.Place.Create(label="Rome").save()).id)
    return ids


@no_type_check
async def factoid(m, label: str, *statements: dict, **saved: Any) -> str:
    return str((await m.Factoid.Create(label=label, statements=list(statements)).save(**saved)).id)  # fmt: skip


def stored(db_driver, label: str) -> str:
    (row,) = run(
        db_driver,
        "MATCH (n:PGIndexableNode {label: $label}) WHERE n:Document RETURN n.id AS id",
        label=label,
    )
    return row["id"]


def counts(db_driver) -> tuple[int, int, int]:
    """The nodes, the edges and the `PGPending` marks"""
    return (
        run(db_driver, "MATCH (n) RETURN count(n) AS n")[0]["n"],
        run(db_driver, "MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"],
        run(db_driver, "MATCH (p:PGPending) RETURN count(p) AS n")[0]["n"],
    )


async def built(db_driver) -> None:
    """Every part rebuilt, and the marks of the writes worked off"""
    from pangloss_vectors.rebuild import rebuild

    await rebuild()
    await one_turn(db_driver)


async def asked(api, kind: str, id: str, **headers: Any) -> dict:
    response = await api.get(f"/api/compare/{kind}/{id}?near=true", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def by_label(answer: dict) -> dict[str, dict]:
    return {entry["other"]["label"]: entry for entry in answer["pairs"]}


NEAR = {"profile": "who", "k": 5, "floor": 0.6, "state": "ok"}


# ---------------------------------------------------------------------------
# What is found, and what is said of it
# ---------------------------------------------------------------------------


@no_type_check
async def test_two_namesakes_births_pair_only_through_near_entities_with_both_in_the_reason(
    database,
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await people(m, ada=ADA, ada2=ADA, ben="Ben Jonson")
    await factoid(m, "a birth", birth("Ada is born", ids["ada"], ids["mill"], 1815))
    await factoid(m, "another birth", birth("Ada is born, says another", ids["ada2"], ids["mill"], 1815))  # fmt: skip
    await built(database)
    one, other = stored(database, "Ada is born"), stored(database, "Ada is born, says another")  # fmt: skip

    async with client() as api:
        plain = (await api.get(f"/api/compare/Birth/{one}")).json()
        found = await asked(api, "Birth", one)
        back = await asked(api, "Birth", other)

    assert plain["pairs"] == [] and plain["near"] is None
    assert found["near"] == NEAR and found["more"] is False
    assert found["statement"]["id"] == one
    (entry,) = found["pairs"]
    assert entry["other"]["id"] == other and entry["found"] == "near"
    # (once per person, certain: with her namesake read as Ada, the same birth)
    assert entry["relation"] == "agree" and entry["likelihood"] == 1.0
    assert entry["superseded"] is False and entry["judged"] is None
    (reason,) = entry["by"]
    assert reason["field"] == "person" and reason["kind"] == "near"
    assert reason["entity"] == {"id": ids["ada"], "type": "Person", "label": ADA}
    assert reason["near"] == {"id": ids["ada2"], "type": "Person", "label": ADA}
    assert 0.6 <= reason["score"] <= 1.0
    # (and the other way about)
    (entry,) = back["pairs"]
    assert entry["other"]["id"] == one
    assert entry["by"][0]["entity"]["id"] == ids["ada2"] and entry["by"][0]["near"]["id"] == ids["ada"]  # fmt: skip


@no_type_check
async def test_a_namesake_s_birth_told_otherwise_disagrees_and_a_gathering_a_century_off_is_not_given(
    database,
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await people(m, ada=ADA, ada2=ADA, ben="Ben Jonson", cy="Cy Twombly")
    await factoid(m, "a birth", birth("Ada is born", ids["ada"], ids["mill"], 1815))
    await factoid(m, "a later birth", birth("Ada is born in Rome", ids["ada2"], ids["rome"], 1915))  # fmt: skip
    await factoid(m, "a gathering", activity("Ada met Ben", ids["ada"], ids["ben"], day(1840, 5, 1)))  # fmt: skip
    await factoid(m, "a later gathering", activity("Ada met Cy", ids["ada2"], ids["cy"], day(1940, 5, 1)))  # fmt: skip
    await built(database)

    async with client() as api:
        born = await asked(api, "Birth", stored(database, "Ada is born"))
        met = await asked(api, "Activity", stored(database, "Ada met Ben"))

    (entry,) = born["pairs"]
    assert entry["other"]["label"] == "Ada is born in Rome"
    assert entry["relation"] == "disagree"
    assert set(entry["fields"]) == {"when", "place"}
    assert entry["by"][0]["field"] == "person"
    # (two gatherings a century apart are two: not given, though Ada's namesake was found)
    assert met["pairs"] == [] and met["near"] == NEAR


@no_type_check
async def test_a_pair_by_rule_is_not_given_again_through_a_near_entity(database):
    """Ada's gathering and her namesake's both have Ben as a guest: a pair by rule, not one through the namesake"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await people(m, ada=ADA, ada2=ADA, ben="Ben Jonson")
    await factoid(m, "one", activity("Ada met Ben", ids["ada"], ids["ben"], day(1840, 5, 1)))  # fmt: skip
    await factoid(m, "two", activity("Ada met Ben again", ids["ada2"], ids["ben"], day(1840, 5, 1)))  # fmt: skip
    await built(database)
    id = stored(database, "Ada met Ben")

    async with client() as api:
        plain = (await api.get(f"/api/compare/Activity/{id}")).json()
        found = await asked(api, "Activity", id)

    assert [e["other"]["label"] for e in plain["pairs"]] == ["Ada met Ben again"]
    assert found["pairs"] == [] and found["near"] == NEAR


@no_type_check
async def test_never_through_a_stand_in(database):
    """A birth whose person is a mention not identified (`Mention`, a stand-in), of the same name as Ada: neither
    pairs with the other"""
    from pangloss_testing.similar_models import declare, mention_stand_in

    stand_in = mention_stand_in()
    hooks.stand_ins.append(stand_in)
    try:
        m = declare(compared=True, stand_in=True)
        ids = await people(m, ada=ADA, ada2=ADA)
        mention = {"type": "Mention", "label": ADA, "mentioned_type": "Person"}
        await factoid(m, "a birth", birth("Ada is born", ids["ada"], ids["mill"], 1815))
        await factoid(m, "a mention", birth("Someone is born", mention, ids["mill"], 1815))  # fmt: skip
        await built(database)

        async with client() as api:
            found = await asked(api, "Birth", stored(database, "Ada is born"))
            mentioned = await asked(api, "Birth", stored(database, "Someone is born"))
        assert found["pairs"] == [] and found["near"] == NEAR
        assert mentioned["pairs"] == [] and mentioned["near"] == NEAR
    finally:
        hooks.stand_ins.remove(stand_in)


@no_type_check
async def test_a_merged_entity_is_the_one_kept_and_its_absorbed_ones_are_found_through_it(
    database,
):
    """Ada's namesake absorbed another namesake (a merge, which moves the reference); and a reference a merge has not
    moved, marked by hand as a merge leaves it: each is found through the one kept, never the one absorbed"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await people(m, ada=ADA, ada2=ADA, ada3=ADA, eve="Eve Smith", eve2="Eve Smith", eve3="Eve Smith")  # fmt: skip
    await factoid(m, "a birth", birth("Ada is born", ids["ada"], ids["mill"], 1815))
    await factoid(m, "the third", birth("Ada is born, says a third", ids["ada3"], ids["mill"], 1815))  # fmt: skip
    await factoid(m, "Eve", birth("Eve is born", ids["eve"], ids["mill"], 1820))
    await factoid(m, "Eve again", birth("Eve is born, again", ids["eve3"], ids["mill"], 1820))  # fmt: skip
    await m.Person.merge(absorb=ids["ada3"], into=ids["ada2"])
    await built(database)
    run(
        database,
        "MATCH (e:PGIndexableNode {id: $absorbed}) SET e.merged_into = $kept "
        "CREATE (:PGMerge {id: $merge, survivor: $kept, absorbed: $absorbed, state: 'done'})",
        absorbed=ids["eve3"],
        kept=ids["eve2"],
        merge=str(uuid4()),
    )

    async with client() as api:
        ada = await asked(api, "Birth", stored(database, "Ada is born"))
        eve = await asked(api, "Birth", stored(database, "Eve is born"))

    (entry,) = ada["pairs"]
    assert entry["other"]["label"] == "Ada is born, says a third"
    assert [r["near"]["id"] for r in entry["by"]] == [ids["ada2"]]
    (entry,) = eve["pairs"]
    assert entry["other"]["label"] == "Eve is born, again"
    assert [r["near"]["id"] for r in entry["by"]] == [ids["eve2"]]
    assert entry["relation"] == "agree"


@no_type_check
async def test_an_unpublished_factoid_is_paired_only_for_a_reader_who_may_see_it(database):  # fmt: skip
    from pangloss_testing.similar_models import declare

    m = declare(compared=True, reviewed=True)
    ids = await people(m, ada=ADA, ada2=ADA)
    await factoid(m, "a birth", birth("Ada is born", ids["ada"], ids["mill"], 1815), published=True)  # fmt: skip
    await factoid(m, "not published", birth("Ada is born, unpublished", ids["ada2"], ids["mill"], 1815), published=False)  # fmt: skip
    await built(database)
    seen, hidden = stored(database, "Ada is born"), stored(database, "Ada is born, unpublished")  # fmt: skip

    assert (await compare_near(seen, False)).entries == ()
    (entry,) = (await compare_near(seen, True)).entries
    assert entry.other.id == hidden
    assert await compare_near(hidden, False) is None
    assert [e.other.id for e in (await compare_near(hidden, True)).entries] == [seen]
    # (over the route, not logged in: the hidden one is a 404, and the one seen has no pair)
    async with client() as api:
        assert (
            await api.get(f"/api/compare/Birth/{hidden}?near=true")
        ).status_code == 404
        assert (await asked(api, "Birth", seen))["pairs"] == []


# ---------------------------------------------------------------------------
# The states, the floor and k
# ---------------------------------------------------------------------------


@no_type_check
async def test_vectors_not_built_are_pending_and_no_profile_is_none(database, monkeypatch):  # fmt: skip
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await people(m, ada=ADA, ada2=ADA)
    await factoid(m, "a birth", birth("Ada is born", ids["ada"], ids["mill"], 1815))
    await factoid(m, "another", birth("Ada is born, says another", ids["ada2"], ids["mill"], 1815))  # fmt: skip
    id = stored(database, "Ada is born")

    async with client() as api:
        pending = await asked(api, "Birth", id)
        await built(database)
        ok = await asked(api, "Birth", id)
        monkeypatch.setattr(core_settings.SETTINGS, "COMPARE_PROFILE", None)
        none = await asked(api, "Birth", id)

    assert pending["pairs"] == [] and pending["near"] == {**NEAR, "state": "pending"}
    assert len(ok["pairs"]) == 1 and ok["near"] == NEAR
    # (no profile, and no reconciliation to choose one)
    assert none["pairs"] == []
    assert none["near"] == {"profile": None, "k": 5, "floor": 0.6, "state": "none"}


@no_type_check
async def test_the_floor_and_k_are_kept_to(database, monkeypatch):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await people(m, ada=ADA, ada2=ADA, ada3=ADA)
    await factoid(m, "a birth", birth("Ada is born", ids["ada"], ids["mill"], 1815))
    await factoid(m, "the second", birth("Ada is born, says a second", ids["ada2"], ids["mill"], 1815))  # fmt: skip
    await factoid(m, "the third", birth("Ada is born, says a third", ids["ada3"], ids["mill"], 1815))  # fmt: skip
    await built(database)
    id = stored(database, "Ada is born")
    SETTINGS = core_settings.SETTINGS

    async with client() as api:
        both = await asked(api, "Birth", id)
        scores = sorted(r["score"] for e in both["pairs"] for r in e["by"])
        assert len(both["pairs"]) == 2 and len(scores) == 2, both
        monkeypatch.setattr(SETTINGS, "COMPARE_NEAR_K", 1)
        one = await asked(api, "Birth", id)
        monkeypatch.setattr(SETTINGS, "COMPARE_NEAR_K", 5)
        monkeypatch.setattr(SETTINGS, "COMPARE_NEAR", max(scores) + 1e-6)
        none = await asked(api, "Birth", id)
        monkeypatch.setattr(SETTINGS, "COMPARE_NEAR", min(scores))
        again = await asked(api, "Birth", id)
        monkeypatch.setattr(SETTINGS, "COMPARE_MOST_PAIRS", 1)
        cut = await asked(api, "Birth", id)

    nearest = max(both["pairs"], key=lambda e: e["by"][0]["score"])
    (entry,) = one["pairs"]
    assert entry["other"]["id"] == nearest["other"]["id"]
    assert one["near"]["k"] == 1
    assert none["pairs"] == [] and none["near"]["floor"] == pytest.approx(
        max(scores) + 1e-6
    )
    assert len(again["pairs"]) == 2
    # (the cut: the nearest-scored first, and the answer says there were more)
    assert cut["more"] is True
    assert [e["other"]["id"] for e in cut["pairs"]] == [nearest["other"]["id"]]


# ---------------------------------------------------------------------------
# A person's judgement, nothing written, and the cost
# ---------------------------------------------------------------------------


async def bearer(api, username: str) -> dict:
    await service.create_user(username, f"{username}@example.com", PASSWORD)
    response = await api.post(
        "/api/users/token", data={"username": username, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@no_type_check
async def test_a_person_s_judgement_overrides_a_near_pair(database):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids = await people(m, ada=ADA, ada2=ADA)
    await factoid(m, "a birth", birth("Ada is born", ids["ada"], ids["mill"], 1815))
    await factoid(m, "another", birth("Ada is born, says another", ids["ada2"], ids["mill"], 1815))  # fmt: skip
    await built(database)
    one, other = stored(database, "Ada is born"), stored(database, "Ada is born, says another")  # fmt: skip

    async with client() as api:
        headers = await bearer(api, "ann")
        response = await api.post(
            "/api/StatementJudgement",
            json={
                "type": "StatementJudgement",
                "label": "two Adas",
                "verdict": "two_events",
                "note": "two people",
                # (in the other order: either is the pair)
                "statement": {"type": "Birth", "id": other},
                "other": {"type": "Birth", "id": one},
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        await one_turn(database)
        found = await asked(api, "Birth", one, **headers)

    (entry,) = found["pairs"]
    assert entry["found"] == "near"
    assert entry["relation"] == "two" and entry["judged"] == "two_events"
    assert entry["workedOut"]["relation"] == "agree"
    (judged,) = entry["judgements"]
    assert (
        judged["note"] == "two people" and judged["createdBy"][0]["username"] == "ann"
    )
    assert entry["superseded"] is False


@no_type_check
async def world(m) -> dict[str, str]:
    ids = await people(m, ada=ADA, ada2=ADA, ben="Ben Jonson")
    await factoid(m, "a birth", birth("Ada is born", ids["ada"], ids["mill"], 1815))
    await factoid(m, "another", birth("Ada is born, says another", ids["ada2"], ids["mill"], 1815))  # fmt: skip
    await factoid(m, "a gathering", activity("Ada met Ben", ids["ada"], ids["ben"], day(1840, 5, 1)))  # fmt: skip
    await factoid(m, "again", activity("Ada met Ben, says another", ids["ada2"], ids["ben"], day(1840, 5, 1)))  # fmt: skip
    return ids


ASKED = [("Birth", "Ada is born"), ("Activity", "Ada met Ben"), ("Birth", "Ada is born, says another")]  # fmt: skip


@no_type_check
async def test_nothing_is_written_and_without_near_the_answer_is_as_before(database):
    from pangloss_compare.compare import compare
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await world(m)
    await built(database)
    before = counts(database)

    async with client() as api:
        for kind, label in ASKED:
            id = stored(database, label)
            await asked(api, kind, id)
            plain = await api.get(f"/api/compare/{kind}/{id}")
            assert plain.status_code == 200
            # (the pairs by rule, as `compare` gives them, and `near` null)
            assert plain.json() == (await compare(id, False)).as_json()
            assert plain.json()["near"] is None
            assert all(e["found"] == "rule" for e in plain.json()["pairs"])
        assert (await api.get(f"/api/compare/Birth/{uuid4()}?near=true")).status_code == 404  # fmt: skip

    assert counts(database) == before


# What `compare_near` runs (measured 2026-11-27): three read transactions for a birth, a search between two. The
# first: the statement read (its node, the entities of its fields) and the labels and classes (3). The search,
# `nearest`'s own: the states, the survivor of the entity, its vectors, the scan, and the count of the classes (6).
# The second: the fit in use, the merges of the near entities and the pairs by rule, the statements naming them (one
# query: `pairs.naming`), the others read (their nodes, their entities), the judgements and the labels (7). A gathering
# has two identifying entities, so two searches, and nothing to read after: what it finds is a pair by rule (4 in the
# second). A change that adds a round trip fails here
COMPARE_NEAR_BUDGET = {
    "Ada is born": (3, 16),
    "Ada met Ben": (4, 19),
    "Ada is born, says another": (3, 16),
}


@no_type_check
async def test_compare_near_runs_its_budget_of_transactions_and_statements(database):
    from pangloss_testing.conformance.test_query_costs import recorded
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await world(m)
    await built(database)
    took = {}
    for _, label in ASKED:
        id = stored(database, label)
        with recorded() as r:
            await compare_near(id, True)
        took[label] = (r.transactions, len(r.statements))

    assert took == COMPARE_NEAR_BUDGET
