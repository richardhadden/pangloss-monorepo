"""A description resolved, "This is…" (`POST /api/criteria/{id}/resolve`, `pangloss_criteria.resolve`): the entity chosen
takes its place in its document, which is written again as an update, as reconciling an `Unreconciled` does
(implementation_docs/matches-criteria.md, "In a view", and Q9)"""

import contextlib
import datetime
import importlib
import uuid
from typing import no_type_check

import httpx2 as httpx
import pangloss_core.settings as core_settings
import pangloss_criteria.models
import pytest
import pytest_asyncio
from pangloss_api import create_app
from pangloss_criteria import CriteriaMeta, run_pending
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    PanglossNotFoundError,
    PanglossVersionConflictError,
    PanglossWriteRefused,
    ViaEdge,
    hooks,
    initialise,
)
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"

PEOPLE = ["Lang", "Serntein", "Stürtzel", "Dorn"]


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)

    class Person(Entity):
        _criteria_meta = CriteriaMeta(allowed=True)

    class Place(Entity):
        pass

    class Certainty(EdgeModel):
        certainty: int

    class Activity(Document):
        carried_out_by: list[Person]

    class Witnessing(Document):
        witnesses: list[ViaEdge[Person, Certainty]]

    class Official(Person):
        pass

    class Letter(Document):
        """Carried by someone, and signed by an official"""

        carried_out_by: list[Person]
        signed_by: list[Official]

    initialise()
    return Person, Place, Activity, Witnessing


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    made = models()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.models = made
        client.app = app
        yield client


async def bearer(client) -> dict:
    await service.create_user("root", "root@example.com", PASSWORD, admin=True)
    response = await client.post(
        "/api/users/token", data={"username": "root", "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def people(client, admin) -> dict[str, str]:
    """Some people and a place: their ids, by label"""
    ids = {}
    for kind, label in [*(("Person", label) for label in PEOPLE), ("Place", "Ghent")]:
        response = await client.post(
            f"/api/{kind}", json={"label": label}, headers=admin
        )
        assert response.status_code == 201, response.text
        ids[label] = response.json()["id"]
    return ids


# (whoever has an S in the label)
CRITERIA = {"type": "Person", "where": {"label": {"contains": "S"}}}


def description(**more) -> dict:
    return {
        "type": "MatchesCriteria",
        "wording": "N. N., a scribe",
        "criteria": CRITERIA,
        **more,
    }


async def activity_with_a_description(client, admin, ids) -> tuple[str, str]:
    """An activity carried out by Lang, someone described, and Dorn: the ids of the activity and of the
    description, once the worker has found its candidates"""
    response = await client.post(
        "/api/Activity",
        json={
            "label": "A letter carried",
            "carriedOutBy": [
                {"type": "Person", "id": ids["Lang"]},
                description(),
                {"type": "Person", "id": ids["Dorn"]},
            ],
        },
        headers=admin,
    )
    assert response.status_code == 201, response.text
    activity = response.json()["id"]
    await run_pending()
    read = (await client.get(f"/api/Activity/{activity}", headers=admin)).json()
    assert [c["label"] for c in read["carriedOutBy"][1]["target"]] == [
        "Serntein",
        "Stürtzel",
    ]
    return activity, read["carriedOutBy"][1]["id"]


def resolving(id, entity_id, kind="Person", **more) -> tuple[str, dict]:
    return f"/api/criteria/{id}/resolve", {
        "entity": {"type": kind, "id": str(entity_id)},
        **more,
    }


@no_type_check
async def test_a_description_is_resolved_in_its_place_as_a_new_version(
    client, clear_database
):
    admin = await bearer(client)
    ids = await people(client, admin)
    activity, described = await activity_with_a_description(client, admin, ids)

    path, body = resolving(described, ids["Serntein"])
    response = await client.post(path, json=body, headers=admin)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "head": {"type": "Activity", "id": activity, "label": "A letter carried"},
        "entity": {"type": "Person", "id": ids["Serntein"], "label": None},
        "version": 2,
    }

    # (the entity in its place, between the two it was between; the description gone)
    read = (await client.get(f"/api/Activity/{activity}", headers=admin)).json()
    assert [(c["type"], c["id"]) for c in read["carriedOutBy"]] == [
        ("Person", ids["Lang"]),
        ("Person", ids["Serntein"]),
        ("Person", ids["Dorn"]),
    ]
    assert read["meta"]["version"] == 2
    gone = await client.get(f"/api/criteria/{described}/candidates", headers=admin)
    assert gone.status_code == 404
    # (resolved once: it is no longer there to be resolved)
    again = await client.post(path, json=body, headers=admin)
    assert again.status_code == 404, again.text


@no_type_check
async def test_whoever_the_field_takes_may_be_chosen_not_only_a_candidate(
    client, clear_database
):
    admin = await bearer(client)
    ids = await people(client, admin)
    activity, described = await activity_with_a_description(client, admin, ids)
    # (Lang is no candidate, and is in the document already: the server does not check candidacy)
    path, body = resolving(described, ids["Lang"])
    response = await client.post(path, json=body, headers=admin)
    assert response.status_code == 200, response.text
    read = (await client.get(f"/api/Activity/{activity}", headers=admin)).json()
    assert [c["id"] for c in read["carriedOutBy"]] == [
        ids["Lang"],
        ids["Lang"],
        ids["Dorn"],
    ]


@no_type_check
async def test_the_properties_of_the_relation_are_kept(client, clear_database):
    admin = await bearer(client)
    ids = await people(client, admin)
    response = await client.post(
        "/api/Witnessing",
        json={
            "label": "Witnessed",
            "witnesses": [
                {
                    "type": "Person",
                    "id": ids["Dorn"],
                    "edgeProperties": {"certainty": 90},
                },
                description(edgeProperties={"certainty": 60}),
            ],
        },
        headers=admin,
    )
    assert response.status_code == 201, response.text
    witnessing = response.json()["id"]
    read = (await client.get(f"/api/Witnessing/{witnessing}", headers=admin)).json()
    described = read["witnesses"][1]["id"]

    path, body = resolving(described, ids["Stürtzel"])
    response = await client.post(path, json=body, headers=admin)
    assert response.status_code == 200, response.text
    read = (await client.get(f"/api/Witnessing/{witnessing}", headers=admin)).json()
    assert [(c["id"], c["edgeProperties"]["certainty"]) for c in read["witnesses"]] == [
        (ids["Dorn"], 90),
        (ids["Stürtzel"], 60),
    ]


@no_type_check
async def test_what_cannot_be_resolved_is_refused_and_nothing_is_written(
    client, clear_database
):
    admin = await bearer(client)
    ids = await people(client, admin)
    Person, Place, Activity, Witnessing = client.models
    activity, described = await activity_with_a_description(client, admin, ids)

    async def status(path, body, headers=admin) -> tuple[int, dict]:
        response = await client.post(path, json=body, headers=headers)
        return response.status_code, response.json()

    # (not logged in)
    assert (await status(*resolving(described, ids["Lang"]), headers={}))[0] == 401
    # (no description of that id: none, or a head, or a person)
    for id in (uuid.uuid4(), activity, ids["Dorn"]):
        code, answer = await status(*resolving(id, ids["Lang"]))
        assert code == 404, answer
    assert (await status(*resolving("not-an-id", ids["Lang"])))[0] == 422

    # (what the field does not take there: a place in a person's place)
    code, answer = await status(*resolving(described, ids["Ghent"], kind="Place"))
    assert code == 422, answer
    assert answer["error"] == "PanglossWriteRefused"
    # (a person who is not there)
    code, answer = await status(*resolving(described, uuid.uuid4()))
    assert code == 422, answer
    assert answer["error"] == "PanglossReferenceError"

    # (based on a version that is not the latest: someone has saved it since)
    edited = (await client.get(f"/api/Activity/{activity}/edit", headers=admin)).json()
    edited["label"] = "A letter carried to Innsbruck"
    updated = await client.put(
        f"/api/Activity/{activity}", json=edited, headers={**admin, "If-Match": "1"}
    )
    assert updated.status_code in (200, 204), updated.text
    code, answer = await status(*resolving(described, ids["Lang"], version=1))
    assert code == 412, answer
    assert answer["error"] == "PanglossVersionConflictError"

    # (none of it was written)
    read = await Activity.get(uuid.UUID(activity))
    assert read.meta.version == 2
    assert [c.type for c in read.carried_out_by] == [
        "Person",
        "MatchesCriteria",
        "Person",
    ]
    # (on the version it is now, it goes through)
    code, answer = await status(*resolving(described, ids["Lang"], version=2))
    assert code == 200, answer
    assert answer["version"] == 3


@no_type_check
async def test_a_description_in_a_document_the_reader_cannot_see_is_not_there(
    client, clear_database
):
    admin = await bearer(client)
    ids = await people(client, admin)
    activity, described = await activity_with_a_description(client, admin, ids)
    deleted = await client.delete(f"/api/Activity/{activity}", headers=admin)
    assert deleted.status_code in (200, 204), deleted.text
    path, body = resolving(described, ids["Lang"])
    response = await client.post(path, json=body, headers=admin)
    assert response.status_code == 404, response.text


# --- from Python, and through the SDK ---------------------------------------------------------------------------------


@no_type_check
async def test_the_function_on_the_server_resolves_as_the_route_does(
    client, clear_database
):
    from pangloss_criteria import Resolved, resolve

    admin = await bearer(client)
    ids = await people(client, admin)
    Person, Place, Activity, Witnessing = client.models
    activity, described = await activity_with_a_description(client, admin, ids)

    with pytest.raises(PanglossNotFoundError):
        await resolve(uuid.uuid4(), {"type": "Person", "id": ids["Lang"]})
    with pytest.raises(PanglossWriteRefused):
        await resolve(described, {"type": "Place", "id": ids["Ghent"]})
    with pytest.raises(PanglossVersionConflictError):
        await resolve(described, {"type": "Person", "id": ids["Lang"]}, version=7)

    # (an entity as read will do)
    stürtzel = await Person.get(uuid.UUID(ids["Stürtzel"]))
    done = await resolve(described, stürtzel)
    assert isinstance(done, Resolved)
    assert (done.head.type, str(done.head.id), done.version) == (
        "Activity",
        activity,
        2,
    )
    assert (done.entity.type, str(done.entity.id)) == ("Person", ids["Stürtzel"])
    read = await Activity.get(uuid.UUID(activity))
    assert [str(c.id) for c in read.carried_out_by] == [
        ids["Lang"],
        ids["Stürtzel"],
        ids["Dorn"],
    ]


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
async def test_the_sdk_resolves_through_the_route(client, clear_database, monkeypatch):
    from pangloss_sdk import client as sdk_client

    from pangloss_criteria import access, resolve

    admin = await bearer(client)
    ids = await people(client, admin)
    activity, described = await activity_with_a_description(client, admin, ids)

    sdk = sdk_client.AsyncClient(
        await sdk_settings(), httpx.ASGITransport(app=client.app)
    )
    sdk_client.install(sdk)
    monkeypatch.setattr(access, "storage_kind", lambda: "api")
    try:
        # (the server's refusals are raised again as they were)
        with pytest.raises(PanglossNotFoundError):
            await resolve(uuid.uuid4(), {"type": "Person", "id": ids["Lang"]})
        with pytest.raises(PanglossVersionConflictError):
            await resolve(described, {"type": "Person", "id": ids["Lang"]}, version=7)
        done = await resolve(described, {"type": "Person", "id": ids["Serntein"]})
        assert (str(done.head.id), done.version) == (activity, 2)
    finally:
        await sdk.close()
        sdk_client.install(None)
    read = (await client.get(f"/api/Activity/{activity}", headers=admin)).json()
    assert read["carriedOutBy"][1]["id"] == ids["Serntein"]


@no_type_check
async def test_the_blocking_sdk_asks_the_same(client, clear_database, monkeypatch):
    """The blocking function asks the same request, and gives the same answer (the API's answer, taken through the
    async client, given back to a blocking client that does not run: the test's database is on this loop)"""
    from pangloss_sdk import client as sdk_client

    from pangloss_criteria import Resolved, access, resolve

    admin = await bearer(client)
    ids = await people(client, admin)
    activity, described = await activity_with_a_description(client, admin, ids)
    path, body = resolving(described, ids["Serntein"], version=1)
    answered = await client.post(path, json=body, headers=admin)
    assert answered.status_code == 200, answered.text
    sent = []

    class Canned(sdk_client.Client):
        def send(self, call):
            sent.append(call)
            return answered

    sdk_client.install(Canned(await sdk_settings()))
    monkeypatch.setattr(access, "storage_kind", lambda: "api_sync")
    try:
        done = resolve(described, {"type": "Person", "id": ids["Serntein"]}, version=1)
    finally:
        sdk_client.install(None)
    assert isinstance(done, Resolved) and done.version == 2
    (call,) = sent
    assert (call.method, call.path, call.needs_login) == ("POST", path, True)
    assert call.json == body


# --- the same one in several places (`same_one`) ----------------------------------------------------------------------


@no_type_check
async def test_resolving_one_place_of_a_mark_fills_every_place_in_one_update(
    client, clear_database
):
    admin = await bearer(client)
    ids = await people(client, admin)
    mark = str(uuid.uuid4())
    response = await client.post(
        "/api/Witnessing",
        json={
            "label": "Witnessed",
            "witnesses": [
                description(sameOne=mark, edgeProperties={"certainty": 60}),
                {
                    "type": "Person",
                    "id": ids["Dorn"],
                    "edgeProperties": {"certainty": 90},
                },
                {
                    "type": "MatchesCriteria",
                    "sameOne": mark,
                    "wording": "the same",
                    "edgeProperties": {"certainty": 30},
                },
                # (another, with the same criteria and no mark: not the same one)
                description(edgeProperties={"certainty": 10}),
            ],
        },
        headers=admin,
    )
    assert response.status_code == 201, response.text
    witnessing = response.json()["id"]
    await run_pending()
    read = (await client.get(f"/api/Witnessing/{witnessing}", headers=admin)).json()
    bare = read["witnesses"][2]["id"]

    # (from the place with no criteria of its own)
    path, body = resolving(bare, ids["Stürtzel"])
    response = await client.post(path, json=body, headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2

    read = (await client.get(f"/api/Witnessing/{witnessing}", headers=admin)).json()
    assert read["meta"]["version"] == 2
    assert [
        (
            c["type"],
            c.get("id") if c["type"] == "Person" else None,
            c["edgeProperties"]["certainty"],
        )
        for c in read["witnesses"]
    ] == [
        ("Person", ids["Stürtzel"], 60),
        ("Person", ids["Dorn"], 90),
        ("Person", ids["Stürtzel"], 30),
        ("MatchesCriteria", None, 10),
    ]


@no_type_check
async def test_a_place_whose_field_does_not_take_the_entity_refuses_the_whole(
    client, clear_database
):
    admin = await bearer(client)
    ids = await people(client, admin)
    mark = str(uuid.uuid4())
    official = await client.post(
        "/api/Official", json={"label": "Sigmund Official"}, headers=admin
    )
    assert official.status_code == 201, official.text
    official = official.json()["id"]
    response = await client.post(
        "/api/Letter",
        json={
            "label": "A letter",
            "carriedOutBy": [
                {"type": "MatchesCriteria", "sameOne": mark, "wording": "carried"}
            ],
            "signedBy": [
                {
                    "type": "MatchesCriteria",
                    "sameOne": mark,
                    "criteria": {"type": "Official"},
                }
            ],
        },
        headers=admin,
    )
    assert response.status_code == 201, response.text
    letter = response.json()["id"]
    await run_pending()
    read = (await client.get(f"/api/Letter/{letter}", headers=admin)).json()
    carried = read["carriedOutBy"][0]["id"]
    assert [c["label"] for c in read["carriedOutBy"][0]["target"]] == [
        "Sigmund Official"
    ]

    # (a person who is no official: the place where he signs does not take him)
    path, body = resolving(carried, ids["Lang"])
    response = await client.post(path, json=body, headers=admin)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "PanglossWriteRefused"
    read = (await client.get(f"/api/Letter/{letter}", headers=admin)).json()
    assert read["meta"]["version"] == 1
    assert read["carriedOutBy"][0]["type"] == "MatchesCriteria"
    assert read["signedBy"][0]["type"] == "MatchesCriteria"

    path, body = resolving(carried, official, kind="Official")
    response = await client.post(path, json=body, headers=admin)
    assert response.status_code == 200, response.text
    read = (await client.get(f"/api/Letter/{letter}", headers=admin)).json()
    assert [(c["type"], c["id"]) for c in read["carriedOutBy"] + read["signedBy"]] == [
        ("Official", official),
        ("Official", official),
    ]


# --- `hooks.resolved`: one event for each place filled ------------------------------------------------------------------


@contextlib.contextmanager
def listening():
    told = []

    async def listen(resolution):
        told.append(resolution)

    hooks.resolved.append(listen)
    try:
        yield told
    finally:
        hooks.resolved.remove(listen)


@no_type_check
async def test_a_resolve_tells_of_the_description_resolved(client, clear_database):
    admin = await bearer(client)
    ids = await people(client, admin)
    activity, described = await activity_with_a_description(client, admin, ids)
    path, body = resolving(described, ids["Serntein"])
    before = datetime.datetime.now(datetime.UTC)
    with listening() as told:
        response = await client.post(path, json=body, headers=admin)
    assert response.status_code == 200, response.text
    (resolution,) = told
    assert resolution == hooks.Resolution(
        stand_in_id=uuid.UUID(described),
        stand_in_type="MatchesCriteria",
        head_id=uuid.UUID(activity),
        head_type="Activity",
        entity_id=uuid.UUID(ids["Serntein"]),
        entity_type="Person",
        user="root",
        at=resolution.at,
        direct=True,
    )
    assert before <= resolution.at <= datetime.datetime.now(datetime.UTC)


@no_type_check
async def test_a_resolve_of_the_same_one_in_two_places_tells_of_each(
    client, clear_database
):
    admin = await bearer(client)
    ids = await people(client, admin)
    mark = str(uuid.uuid4())
    response = await client.post(
        "/api/Activity",
        json={
            "label": "Carried twice",
            "carriedOutBy": [
                description(sameOne=mark),
                {"type": "MatchesCriteria", "sameOne": mark, "wording": "the same"},
            ],
        },
        headers=admin,
    )
    assert response.status_code == 201, response.text
    activity = response.json()["id"]
    await run_pending()
    read = (await client.get(f"/api/Activity/{activity}", headers=admin)).json()
    first, bare = (part["id"] for part in read["carriedOutBy"])

    path, body = resolving(bare, ids["Stürtzel"])
    with listening() as told:
        response = await client.post(path, json=body, headers=admin)
    assert response.status_code == 200, response.text
    assert sorted((str(r.stand_in_id), r.direct) for r in told) == sorted(
        [(first, False), (bare, True)]
    )
    assert {(str(r.head_id), str(r.entity_id), r.label) for r in told} == {
        (activity, ids["Stürtzel"], None)
    }


@no_type_check
async def test_a_refused_resolve_tells_nothing(client, clear_database):
    from pangloss_criteria import resolve

    admin = await bearer(client)
    ids = await people(client, admin)
    activity, described = await activity_with_a_description(client, admin, ids)
    with listening() as told:
        with pytest.raises(PanglossVersionConflictError):
            await resolve(described, {"type": "Person", "id": ids["Lang"]}, version=7)
        with pytest.raises(PanglossWriteRefused):
            await resolve(described, {"type": "Place", "id": ids["Ghent"]})
    assert told == []
