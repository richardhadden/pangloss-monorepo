"""The routes the interface asks of descriptions (implementation_docs/matches-criteria.md, "The API"): what criteria
would find before they are saved (`POST /api/criteria/preview`), the candidates of a saved description in pages
(`GET /api/criteria/{id}/candidates`), whether a head's descriptions are worked (`GET /api/criteria/settled/{id}`);
and the same from Python, on the server and through the SDK"""

import importlib
import uuid
from typing import Annotated, no_type_check

import httpx2 as httpx
import pangloss_core.settings as core_settings
import pangloss_criteria.models
import pytest
import pytest_asyncio
from pangloss_api import create_app
from pangloss_core import storage_of
from pangloss_criteria import CriteriaMeta, NoCriteria, run_pending
from pangloss_models import Document, Entity, PanglossSearchError, initialise
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"

# (in the order they are made: not that of their labels)
SECRETARIES = ["Serntein", "Waldauf", "Fuchsmagen", "Lang", "Stürtzel", "Hölzl", "Dorn"]


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)

    class Person(Entity):
        _criteria_meta = CriteriaMeta(allowed=True)

    class Place(Entity):
        pass

    class HoldsOffice(Document):
        holder: Annotated[Person, NoCriteria()]
        employer: Annotated[Person, NoCriteria()]

    class Activity(Document):
        carried_out_by: list[Person]

    initialise()
    return Person, Place, HoldsOffice, Activity


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    models_made = models()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.models = models_made
        client.app = app
        yield client


async def bearer(client) -> dict:
    await service.create_user("root", "root@example.com", PASSWORD, admin=True)
    response = await client.post(
        "/api/users/token", data={"username": "root", "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def employed_by(employer_id) -> dict:
    return {
        "type": "Person",
        "where": {
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "holder",
                    "where": {"employer": {"is": str(employer_id)}},
                }
            ]
        },
    }


def lower_the_cap(monkeypatch, to: int) -> None:
    """`CRITERIA_MAX_CANDIDATES` of the settings (which have no such field: it is read with a default)"""
    monkeypatch.setitem(core_settings.SETTINGS.__dict__, "CRITERIA_MAX_CANDIDATES", to)


async def court(client, admin) -> dict[str, str]:
    """Maximilian and his secretaries: their ids, by label"""
    ids = {}
    for label in ["Maximilian", *SECRETARIES]:
        response = await client.post(
            "/api/Person", json={"label": label}, headers=admin
        )
        assert response.status_code == 201, response.text
        ids[label] = response.json()["id"]
    for holder in SECRETARIES:
        response = await client.post(
            "/api/HoldsOffice",
            json={
                "label": f"{holder} serves",
                "holder": {"type": "Person", "id": ids[holder]},
                "employer": {"type": "Person", "id": ids["Maximilian"]},
            },
            headers=admin,
        )
        assert response.status_code == 201, response.text
        ids[f"{holder} serves"] = response.json()["id"]
    return ids


async def described(client, admin, ids, label="A letter carried") -> tuple[str, str]:
    """An activity carried out by someone described as Maximilian's secretary: the ids of the activity and of the
    description"""
    response = await client.post(
        "/api/Activity",
        json={
            "label": label,
            "carriedOutBy": [
                {
                    "type": "MatchesCriteria",
                    "wording": "N. N., secretarius Maximiliani",
                    "criteria": employed_by(ids["Maximilian"]),
                }
            ],
        },
        headers=admin,
    )
    assert response.status_code == 201, response.text
    activity = response.json()["id"]
    read = (await client.get(f"/api/Activity/{activity}", headers=admin)).json()
    (description,) = read["carriedOutBy"]
    return activity, description["id"]


# --- the preview ------------------------------------------------------------------------------------------------------


@no_type_check
async def test_a_preview_gives_the_count_the_first_five_by_label_and_whether_too_broad(
    client, clear_database, monkeypatch
):
    admin = await bearer(client)
    ids = await court(client, admin)
    asked = {"criteria": employed_by(ids["Maximilian"])}

    response = await client.post("/api/criteria/preview", json=asked, headers=admin)
    assert response.status_code == 200, response.text
    found = response.json()
    assert set(found) == {"count", "candidates", "tooBroad"}
    assert found["count"] == 7
    first = sorted(SECRETARIES)[:5]
    assert [c["label"] for c in found["candidates"]] == first
    assert [c["id"] for c in found["candidates"]] == [ids[label] for label in first]
    assert {c["type"] for c in found["candidates"]} == {"Person"}
    assert set(found["candidates"][0]) == {"type", "id", "label"}
    assert found["tooBroad"] is False

    lower_the_cap(monkeypatch, 6)
    found = (
        await client.post("/api/criteria/preview", json=asked, headers=admin)
    ).json()
    assert found["tooBroad"] is True and found["count"] == 7
    lower_the_cap(monkeypatch, 7)
    found = (
        await client.post("/api/criteria/preview", json=asked, headers=admin)
    ).json()
    assert found["tooBroad"] is False

    # (as a logged-in reader: what rests on a document that is not published is counted)
    _, HoldsOffice, _ = client.models[1:]
    await storage_of().operations.set_published_in_db(
        HoldsOffice, ids["Dorn serves"], False
    )
    found = (
        await client.post("/api/criteria/preview", json=asked, headers=admin)
    ).json()
    assert found["count"] == 7 and found["candidates"][0]["label"] == "Dorn"


@no_type_check
async def test_a_preview_never_offers_what_the_document_names(client, clear_database):
    admin = await bearer(client)
    ids = await court(client, admin)
    response = await client.post(
        "/api/criteria/preview",
        json={
            "criteria": employed_by(ids["Maximilian"]),
            "named": [ids["Dorn"], ids["Fuchsmagen"]],
        },
        headers=admin,
    )
    assert response.status_code == 200, response.text
    found = response.json()
    assert found["count"] == 5
    assert [c["label"] for c in found["candidates"]] == [
        "Hölzl",
        "Lang",
        "Serntein",
        "Stürtzel",
        "Waldauf",
    ]


@no_type_check
async def test_a_preview_needs_a_login(client, clear_database):
    await bearer(client)
    response = await client.post(
        "/api/criteria/preview",
        json={"criteria": {"type": "Person", "where": {}}},
    )
    assert response.status_code == 401


@no_type_check
async def test_criteria_a_description_could_not_store_are_a_422_with_the_path(
    client, clear_database
):
    admin = await bearer(client)
    ids = await court(client, admin)

    async def refused(body) -> str:
        response = await client.post("/api/criteria/preview", json=body, headers=admin)
        assert response.status_code == 422, response.text
        answer = response.json()
        assert answer["error"] == "PanglossSearchError", answer
        return answer["detail"]

    # (a document; an entity class may be previewed whether or not it says CriteriaMeta: a field may name
    # MatchesCriteria[Place] itself)
    response = await client.post(
        "/api/criteria/preview",
        json={"criteria": {"type": "Place", "where": {}}},
        headers=admin,
    )
    assert response.status_code == 200, response.text
    assert "'HoldsOffice' is not a class that may be described" in await refused(
        {"criteria": {"type": "HoldsOffice", "where": {}}}
    )
    assert "type: " in await refused({"criteria": {"type": "Nothing", "where": {}}})
    # (a field the class does not have)
    assert "$incoming.salary: HoldsOffice has no field 'salary'" in await refused(
        {
            "criteria": {
                "type": "Person",
                "where": {
                    "$incoming": [
                        {"type": "HoldsOffice", "where": {"salary": {"gt": 3}}}
                    ]
                },
            }
        }
    )
    # (through another description)
    assert "'MatchesCriteria' is a wrapper the search leaves out" in await refused(
        {
            "criteria": {
                "type": "Person",
                "where": {
                    "$incoming": [
                        {
                            "type": "Activity",
                            "where": {
                                "carried_out_by": {
                                    "is": ids["Dorn"],
                                    "through": ["MatchesCriteria"],
                                }
                            },
                        }
                    ]
                },
            }
        }
    )
    # (what only a stored pattern may not hold)
    assert "'$same_as' cannot be in a stored pattern" in await refused(
        {"criteria": {"type": "Person", "where": {"$same_as": {"is": ids["Dorn"]}}}}
    )
    # (none)
    assert "criteria" in await refused({})
    assert "criteria" in await refused({"criteria": None})
    assert "criteria" in await refused({"criteria": {}})
    assert "criteria" in await refused({"criteria": "Person"})


# --- the candidates of a saved description ----------------------------------------------------------------------------


@no_type_check
async def test_the_candidates_of_a_description_are_in_pages_by_label(
    client, clear_database
):
    admin = await bearer(client)
    ids = await court(client, admin)
    activity, description = await described(client, admin, ids)
    path = f"/api/criteria/{description}/candidates"

    # (saved, and not yet worked)
    before = (await client.get(path, headers=admin)).json()
    assert before == {
        "count": 0,
        "tooBroad": False,
        "pending": True,
        "evaluatedWhen": None,
        "broken": None,
        "page": 1,
        "pageSize": 25,
        "candidates": [],
        # (what it is evaluated by: its own criteria; and it is the only place of the one it describes)
        "criteria": employed_by(ids["Maximilian"]),
        "places": 1,
    }
    settled = await client.get(f"/api/criteria/settled/{activity}", headers=admin)
    assert settled.json() == {"settled": False}

    await run_pending()
    after = (await client.get(path, headers=admin)).json()
    assert after["pending"] is False and after["count"] == 7
    assert after["tooBroad"] is False and after["broken"] is None
    assert after["evaluatedWhen"] is not None
    assert [c["label"] for c in after["candidates"]] == sorted(SECRETARIES)
    assert after["candidates"][0] == {
        "type": "Person",
        "id": ids["Dorn"],
        "label": "Dorn",
    }
    assert (
        await client.get(f"/api/criteria/settled/{activity}", headers=admin)
    ).json() == {"settled": True}

    pages = [
        (
            await client.get(path, params={"page": n, "pageSize": 3}, headers=admin)
        ).json()
        for n in (1, 2, 3, 4)
    ]
    assert [[c["label"] for c in p["candidates"]] for p in pages] == [
        sorted(SECRETARIES)[0:3],
        sorted(SECRETARIES)[3:6],
        sorted(SECRETARIES)[6:],
        [],
    ]
    assert {(p["page"], p["pageSize"], p["count"]) for p in pages} == {
        (1, 3, 7),
        (2, 3, 7),
        (3, 3, 7),
        (4, 3, 7),
    }
    assert (await client.get(path, params={"page": 0})).status_code == 422
    assert (await client.get(path, params={"page_size": 101})).status_code == 422


@no_type_check
async def test_candidates_past_the_cap_are_not_listed(
    client, clear_database, monkeypatch
):
    admin = await bearer(client)
    ids = await court(client, admin)
    lower_the_cap(monkeypatch, 3)
    _, description = await described(client, admin, ids)
    await run_pending()
    found = (
        await client.get(f"/api/criteria/{description}/candidates", headers=admin)
    ).json()
    assert found["count"] == 7 and found["tooBroad"] is True
    assert [c["label"] for c in found["candidates"]] == sorted(SECRETARIES)[:3]


@no_type_check
async def test_a_reader_who_is_not_logged_in_sees_only_the_candidates_everyone_may_see(
    client, clear_database
):
    admin = await bearer(client)
    ids = await court(client, admin)
    _, HoldsOffice, _ = client.models[1:]
    # (what makes Dorn and Lang candidates is not published)
    for hidden in ("Dorn serves", "Lang serves"):
        await storage_of().operations.set_published_in_db(
            HoldsOffice, ids[hidden], False
        )
    activity, description = await described(client, admin, ids)
    await run_pending()
    path = f"/api/criteria/{description}/candidates"

    logged_in = (await client.get(path, headers=admin)).json()
    assert logged_in["count"] == 7
    assert [c["label"] for c in logged_in["candidates"]] == sorted(SECRETARIES)

    public = (await client.get(path)).json()
    seen = sorted(set(SECRETARIES) - {"Dorn", "Lang"})
    assert public["count"] == 5 and public["tooBroad"] is False
    assert [c["label"] for c in public["candidates"]] == seen
    # (as the read of the document gives them)
    read = (await client.get(f"/api/Activity/{activity}")).json()
    (shown,) = read["carriedOutBy"]
    assert [c["label"] for c in shown["target"]] == seen
    assert shown["candidateCount"] == public["count"]

    assert (await client.get(f"/api/criteria/settled/{activity}")).status_code == 401


@no_type_check
async def test_a_description_that_is_not_there_or_not_seen_is_a_404(
    client, clear_database
):
    admin = await bearer(client)
    ids = await court(client, admin)
    Person, Place, HoldsOffice, Activity = client.models
    activity, description = await described(client, admin, ids)
    await run_pending()

    async def status(id, headers=None) -> int:
        return (
            await client.get(f"/api/criteria/{id}/candidates", headers=headers)
        ).status_code

    assert await status(description) == 200
    assert await status(uuid.uuid4(), admin) == 404
    # (a head, not a description)
    assert await status(activity, admin) == 404
    assert await status(ids["Dorn"], admin) == 404
    assert await status("not-an-id", admin) == 422

    # (in a document that is not published: for a reader who is logged in only)
    await storage_of().operations.set_published_in_db(Activity, activity, False)
    assert await status(description) == 404
    assert await status(description, admin) == 200

    # (in a deleted document: for no one)
    await storage_of().operations.set_published_in_db(Activity, activity, True)
    deleted = await client.delete(f"/api/Activity/{activity}", headers=admin)
    assert deleted.status_code in (200, 204), deleted.text
    assert await status(description) == 404
    assert await status(description, admin) == 404


@no_type_check
async def test_a_place_with_no_criteria_of_its_own_says_what_it_is_evaluated_by(
    client, clear_database
):
    admin = await bearer(client)
    ids = await court(client, admin)
    Person, Place, HoldsOffice, Activity = client.models
    mark = str(uuid.uuid4())
    criteria = employed_by(ids["Maximilian"])
    response = await client.post(
        "/api/Activity",
        json={
            "label": "A letter carried, and paid for",
            "carriedOutBy": [
                {"type": "MatchesCriteria", "sameOne": mark, "criteria": criteria},
                {"type": "MatchesCriteria", "sameOne": mark, "wording": "paid"},
                {"type": "MatchesCriteria", "sameOne": mark, "wording": "thanked"},
                {"type": "MatchesCriteria", "criteria": {"type": "Person"}},
            ],
        },
        headers=admin,
    )
    assert response.status_code == 201, response.text
    activity = response.json()["id"]
    await run_pending()
    read = (await client.get(f"/api/Activity/{activity}", headers=admin)).json()
    holder, bare, _, alone = (part["id"] for part in read["carriedOutBy"])

    async def page(id, headers=admin) -> dict:
        response = await client.get(f"/api/criteria/{id}/candidates", headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    found = await page(bare)
    # (the holder's criteria, and the three places of the mark; its own candidates, the holder's)
    assert found["criteria"] == criteria and found["places"] == 3
    assert [c["label"] for c in found["candidates"]] == sorted(SECRETARIES)
    assert found["count"] == 7
    assert {k: v for k, v in (await page(holder)).items() if k != "evaluatedWhen"} == {
        k: v for k, v in found.items() if k != "evaluatedWhen"
    }
    # (one with no mark: its own, and one place)
    lone = await page(alone)
    assert lone["criteria"] == {"type": "Person", "where": {}} and lone["places"] == 1
    # (a reader not logged in may see the document: and so the holder's criteria)
    assert (await page(bare, headers={}))["criteria"] == criteria
    # (not when the document is not published: no description at all)
    await storage_of().operations.set_published_in_db(Activity, activity, False)
    hidden = await client.get(f"/api/criteria/{bare}/candidates")
    assert hidden.status_code == 404


# --- from Python, and through the SDK ---------------------------------------------------------------------------------


@no_type_check
async def test_the_functions_on_the_server_give_what_the_routes_give(
    client, clear_database
):
    from pangloss_criteria import Preview, candidates, preview, settled

    admin = await bearer(client)
    ids = await court(client, admin)
    activity, description = await described(client, admin, ids)
    await run_pending()
    await settled(activity, timeout=1)

    found = await preview(employed_by(ids["Maximilian"]), named=[ids["Dorn"]])
    assert isinstance(found, Preview)
    assert found.count == 6 and found.too_broad is False
    assert [c.label for c in found.candidates] == sorted(set(SECRETARIES) - {"Dorn"})[
        :5
    ]
    with pytest.raises(PanglossSearchError, match="'HoldsOffice' is not a class"):
        await preview({"type": "HoldsOffice", "where": {}})

    page = await candidates(description, page=2, page_size=5)
    over_the_api = (
        await client.get(
            f"/api/criteria/{description}/candidates",
            params={"page": 2, "page_size": 5},
            headers=admin,
        )
    ).json()
    assert page.model_dump(by_alias=True, mode="json") == over_the_api
    assert await candidates(uuid.uuid4()) is None


async def sdk_settings():
    from pangloss_sdk import SdkSettings

    server_settings = core_settings.SETTINGS
    try:
        return SdkSettings(
            URL="http://test",  # type: ignore[arg-type]
            USERNAME="root",
            PASSWORD=PASSWORD,  # type: ignore[arg-type]
            USE_STORED_LOGIN=False,
        )
    finally:
        core_settings.SETTINGS = server_settings


@no_type_check
async def test_the_sdk_asks_the_routes_and_gives_the_same(
    client, clear_database, monkeypatch
):
    from pangloss_sdk import client as sdk_client

    from pangloss_criteria import access, candidates, preview, settled

    admin = await bearer(client)
    ids = await court(client, admin)
    activity, description = await described(client, admin, ids)
    await run_pending()
    direct_preview = await preview(employed_by(ids["Maximilian"]), [ids["Lang"]])
    direct_page = await candidates(description, 1, 4)

    sdk = sdk_client.AsyncClient(
        await sdk_settings(), httpx.ASGITransport(app=client.app)
    )
    sdk_client.install(sdk)
    monkeypatch.setattr(access, "storage_kind", lambda: "api")
    try:
        assert (
            await preview(employed_by(ids["Maximilian"]), [ids["Lang"]])
        ) == direct_preview
        # (as a logged-in reader: the SDK logs in for the preview, and the page is read as it then is)
        assert await candidates(description, 1, 4) == direct_page
        assert await candidates(uuid.uuid4()) is None
        with pytest.raises(PanglossSearchError, match="'HoldsOffice' is not a class"):
            await preview({"type": "HoldsOffice", "where": {}})
        await settled(activity, timeout=1)

        # (saved again: pending until the worker has run)
        edited = (
            await client.get(f"/api/Activity/{activity}/edit", headers=admin)
        ).json()
        edited["label"] = "A letter carried to Innsbruck"
        updated = await client.put(
            f"/api/Activity/{activity}",
            json=edited,
            headers={**admin, "If-Match": "1"},
        )
        assert updated.status_code in (200, 204), updated.text
        with pytest.raises(TimeoutError):
            await settled(activity, timeout=0.2)
        assert (await candidates(description)).pending is True
        await run_pending()
        await settled(activity, timeout=1)
    finally:
        await sdk.close()
        sdk_client.install(None)


@no_type_check
async def test_the_blocking_sdk_asks_the_same(client, clear_database, monkeypatch):
    """The blocking functions ask the same requests and give the same answers: the answers of the API, taken through
    the async client, are given back to a blocking client that does not run (the test's database is on this loop)"""
    from pangloss_sdk import client as sdk_client

    from pangloss_criteria import access, candidates, preview, settled

    admin = await bearer(client)
    ids = await court(client, admin)
    activity, description = await described(client, admin, ids)
    await run_pending()
    criteria = employed_by(ids["Maximilian"])
    direct_preview = await preview(criteria, [ids["Lang"]])
    direct_page = await candidates(description, 2, 3)

    answers = {
        ("POST", "/api/criteria/preview"): await client.post(
            "/api/criteria/preview",
            json={"criteria": criteria, "named": [ids["Lang"]]},
            headers=admin,
        ),
        ("POST", "/api/criteria/preview", "refused"): await client.post(
            "/api/criteria/preview",
            json={"criteria": {"type": "HoldsOffice", "where": {}}},
            headers=admin,
        ),
        ("GET", f"/api/criteria/{description}/candidates"): await client.get(
            f"/api/criteria/{description}/candidates",
            params={"page": 2, "page_size": 3},
        ),
        ("GET", f"/api/criteria/settled/{activity}"): await client.get(
            f"/api/criteria/settled/{activity}", headers=admin
        ),
    }
    sent = []

    class Canned(sdk_client.Client):
        def send(self, call):
            sent.append(call)
            if call.json and call.json["criteria"]["type"] == "HoldsOffice":
                return answers[(call.method, call.path, "refused")]
            return answers[(call.method, call.path)]

    sdk_client.install(Canned(await sdk_settings()))
    monkeypatch.setattr(access, "storage_kind", lambda: "api_sync")
    try:
        assert preview(criteria, [ids["Lang"]]) == direct_preview
        assert candidates(description, 2, 3) == direct_page
        assert settled(activity, timeout=1) is None
        with pytest.raises(PanglossSearchError, match="'HoldsOffice' is not a class"):
            preview({"type": "HoldsOffice", "where": {}})
    finally:
        sdk_client.install(None)
    asked = {(call.method, call.path): call for call in sent}
    assert asked[("POST", "/api/criteria/preview")].needs_login is True
    assert asked[("GET", f"/api/criteria/settled/{activity}")].needs_login is True
    assert asked[("GET", f"/api/criteria/{description}/candidates")].params == {
        "page": 2,
        "page_size": 3,
    }
