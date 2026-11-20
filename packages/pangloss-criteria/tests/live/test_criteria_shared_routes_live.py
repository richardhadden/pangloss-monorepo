"""The routes of shared descriptions (implementation_docs/matches-criteria.md, "Shared descriptions", step 11): the
preview of criteria with a description, `shared` in the answer of candidates, the list of shared descriptions, their
mentions, the mentions with the same criteria (`similar`), and `share`, over the API and from Python"""

import importlib
from typing import no_type_check

import httpx2 as httpx
import pangloss_criteria
import pangloss_criteria.models
import pytest
import pytest_asyncio
from criteria_court_support import secretary_of
from pangloss_api import create_app
from pangloss_core import storage_of
from pangloss_criteria import run_pending, sharing
from pangloss_criteria.pattern import SearchPattern
from pangloss_models import Document, Entity, initialise
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

NAME = "MatchesCriteria"
PASSWORD = "correct horse"


def models():
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria
    Description = pangloss_criteria.models.Description

    class Person(Entity):
        pass

    class Monk(Person):
        pass

    class Group(Entity):
        pass

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        holder: list[Person]
        office: Office
        employer: Person

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]
        ordered_by: list[Group | MatchesCriteria[Group]]

    initialise()
    return {
        "Description": Description,
        "Person": Person,
        "Group": Group,
        "Office": Office,
        "HoldsOffice": HoldsOffice,
        "Activity": Activity,
    }


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    made = models()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        client.m = made
        yield client


async def bearer(client) -> dict:
    await service.create_user("root", "root@example.com", PASSWORD, admin=True)
    response = await client.post(
        "/api/users/token", data={"username": "root", "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class Court:
    def __init__(self, m):
        self.m = m
        self.people: dict = {}

    async def person(self, label):
        if label not in self.people:
            self.people[label] = await self.m["Person"].Create(label=label).save()
        return self.people[label]

    async def set_up(self):
        self.secretary = await self.m["Office"].Create(label="Secretary").save()
        for holder in ("Waldauf", "Serntein"):
            await (
                self.m["HoldsOffice"]
                .Create(
                    label=f"{holder} serves",
                    holder=[{"type": "Person", "id": (await self.person(holder)).id}],
                    office={"type": "Office", "id": self.secretary.id},
                    employer={
                        "type": "Person",
                        "id": (await self.person("Maximilian")).id,
                    },
                )
                .save()
            )
        await run_pending()
        return self

    def of(self, employer="Maximilian") -> dict:
        return secretary_of(self.secretary, self.people[employer])

    async def activity(self, label, *mentions, ordered=()):
        return (
            await self.m["Activity"]
            .Create(
                label=label, carried_out_by=list(mentions), ordered_by=list(ordered)
            )
            .save()
        )


def own(criteria) -> dict:
    return {"type": NAME, "wording": "N. N.", "criteria": criteria}


def citing(description, criteria=None) -> dict:
    return {
        "type": NAME,
        "wording": "N. N.",
        "description": {"type": "Description", "id": str(description.id)},
        **({"criteria": criteria} if criteria else {}),
    }


async def a_court(client) -> Court:
    return await Court(client.m).set_up()


# --- the preview and the candidates ---------------------------------------------------------------------------------


@no_type_check
async def test_the_preview_is_of_the_shared_criteria_and_its_own(
    clear_database, client
):
    admin = await bearer(client)
    court = await a_court(client)
    shared = (
        await client.m["Description"]
        .Create(label="Secretary", criteria=court.of())
        .save()
    )
    asked = {"criteria": {"type": "Person", "where": {}}, "description": str(shared.id)}
    response = await client.post("/api/criteria/preview", json=asked, headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 2
    # (no criteria of its own at all)
    response = await client.post(
        "/api/criteria/preview", json={"description": str(shared.id)}, headers=admin
    )
    assert response.json()["count"] == 2
    named = {"description": str(shared.id), "named": [str(court.people["Waldauf"].id)]}
    response = await client.post("/api/criteria/preview", json=named, headers=admin)
    assert [c["label"] for c in response.json()["candidates"]] == ["Serntein"]
    # (of a class that is not the shared one's, nor below it; a description that is not there)
    wrong = {"criteria": {"type": "Group", "where": {}}, "description": str(shared.id)}
    response = await client.post("/api/criteria/preview", json=wrong, headers=admin)
    assert (
        response.status_code == 422
        and response.json()["error"] == "PanglossSearchError"
    )
    response = await client.post(
        "/api/criteria/preview",
        json={"description": str(court.secretary.id)},
        headers=admin,
    )
    assert response.status_code == 422
    # from Python, on the server
    found = await pangloss_criteria.preview(None, (), shared.id)
    assert found.count == 2


@no_type_check
async def test_the_candidates_say_which_shared_description_is_cited(
    clear_database, client
):
    court = await a_court(client)
    shared = (
        await client.m["Description"]
        .Create(label="Secretary", criteria=court.of())
        .save()
    )
    mine = {"type": "Person", "where": {"label": {"contains": "Wal"}}}
    activity = await court.activity("A letter", citing(shared, mine))
    await run_pending()
    read = await client.m["Activity"].get(activity.id)
    mention = read.carried_out_by[0]
    page = (await client.get(f"/api/criteria/{mention.id}/candidates")).json()
    assert page["criteria"] == SearchPattern(mine).data
    assert page["shared"] == {
        "id": str(shared.id),
        "label": "Secretary",
        "criteria": SearchPattern(court.of()).data,
    }
    assert [c["label"] for c in page["candidates"]] == ["Waldauf"]


# --- the list of shared descriptions, and their mentions -----------------------------------------------------------


@no_type_check
async def test_shared_descriptions_are_listed_by_type_label_and_in_pages(
    clear_database, client
):
    # (no login: anyone who may read documents may read them)
    court = await a_court(client)
    Description = client.m["Description"]
    made = {}
    for label, criteria in (
        ("B secretary", court.of()),
        ("A monk", {"type": "Monk", "where": {}}),
        ("C company", {"type": "Group", "where": {}}),
    ):
        made[label] = await Description.Create(label=label, criteria=criteria).save()
    await court.activity("One", citing(made["B secretary"]))
    await court.activity("Two", citing(made["B secretary"]), citing(made["A monk"]))

    listed = (await client.get("/api/criteria/shared")).json()
    assert listed["count"] == 3 and listed["page"] == 1 and listed["pageSize"] == 25
    assert [(r["label"], r["mentions"]) for r in listed["results"]] == [
        ("A monk", 1),
        ("B secretary", 2),
        ("C company", 0),
    ]
    assert listed["results"][1]["criteria"] == SearchPattern(court.of()).data
    assert set(listed["results"][0]) == {"id", "label", "criteria", "mentions"}
    # (a class, and those below it)
    people = (await client.get("/api/criteria/shared?types=Person")).json()
    assert [r["label"] for r in people["results"]] == ["A monk", "B secretary"]
    both = (await client.get("/api/criteria/shared?types=Monk,Group")).json()
    assert [r["label"] for r in both["results"]] == ["A monk", "C company"]
    assert (await client.get("/api/criteria/shared?q=secr")).json()["count"] == 1
    paged = (await client.get("/api/criteria/shared?page=2&page_size=2")).json()
    assert paged["count"] == 3 and [r["label"] for r in paged["results"]] == [
        "C company"
    ]
    assert (await client.get("/api/criteria/shared?types=Nobody")).status_code == 422
    # a deleted one is not listed
    await Description.delete(made["C company"].id)
    assert (await client.get("/api/criteria/shared")).json()["count"] == 2
    # from Python
    assert (await pangloss_criteria.shared(["Monk"])).count == 1


@no_type_check
async def test_the_mentions_of_a_shared_description_are_in_pages_and_hidden_heads_left_out(
    clear_database, client
):
    admin = await bearer(client)
    court = await a_court(client)
    Activity = client.m["Activity"]
    shared = (
        await client.m["Description"]
        .Create(label="Secretary", criteria=court.of())
        .save()
    )
    mine = {"type": "Person", "where": {"label": {"contains": "S"}}}
    c = await court.activity("C letter", citing(shared))
    a = await court.activity("A letter", citing(shared, mine))
    hidden = await court.activity("B letter", citing(shared))
    await storage_of().operations.set_published_in_db(Activity, hidden.id, False)
    path = f"/api/criteria/shared/{shared.id}/mentions"

    seen = (await client.get(path)).json()
    assert seen["count"] == 2
    assert [r["head"]["label"] for r in seen["results"]] == ["A letter", "C letter"]
    first = seen["results"][0]
    assert first["criteria"] == SearchPattern(mine).data and first["wording"] == "N. N."
    assert first["head"] == {"id": str(a.id), "type": "Activity", "label": "A letter"}
    assert seen["results"][1]["criteria"] is None
    # (logged in, the unpublished one is there)
    logged = (await client.get(path, headers=admin)).json()
    assert [r["head"]["label"] for r in logged["results"]] == [
        "A letter",
        "B letter",
        "C letter",
    ]
    paged = (await client.get(f"{path}?page=2&page_size=2", headers=admin)).json()
    assert paged["count"] == 3 and [r["head"]["id"] for r in paged["results"]] == [
        str(c.id)
    ]
    assert (
        await client.get(f"/api/criteria/shared/{court.secretary.id}/mentions")
    ).status_code == 404
    # (from Python on the server, outside a request: as a reader who is not logged in)
    found = await pangloss_criteria.shared_mentions(shared.id)
    assert found.count == 2


# --- the same criteria, and making them one -------------------------------------------------------------------------


@no_type_check
async def test_similar_counts_mentions_with_exactly_these_criteria_and_description(
    clear_database, client
):
    admin = await bearer(client)
    court = await a_court(client)
    shared = (
        await client.m["Description"]
        .Create(label="Secretary", criteria=court.of())
        .save()
    )
    mine = {"type": "Person", "where": {"label": {"contains": "S"}}}
    first = await court.activity("A", own(court.of()), own(court.of()))
    await court.activity("B", own(court.of()))
    await court.activity("C", own(court.of("Waldauf")), citing(shared))
    await court.activity("D", citing(shared), citing(shared, mine))
    body = {**court.of(), "description": None, "except": None}

    assert (await client.post("/api/criteria/similar", json=body)).status_code == 401
    found = (
        await client.post("/api/criteria/similar", json=body, headers=admin)
    ).json()
    assert found["count"] == 3
    assert [d["label"] for d in found["documents"]] == ["A", "B"]
    assert set(found["documents"][0]) == {"id", "type", "label"}
    other = {**body, "except": str(first.id)}
    found = (
        await client.post("/api/criteria/similar", json=other, headers=admin)
    ).json()
    assert found["count"] == 1 and [d["label"] for d in found["documents"]] == ["B"]
    cited = {
        "type": "Person",
        "where": {},
        "description": str(shared.id),
        "except": None,
    }
    found = (
        await client.post("/api/criteria/similar", json=cited, headers=admin)
    ).json()
    assert found["count"] == 2 and [d["label"] for d in found["documents"]] == [
        "C",
        "D",
    ]
    narrowed = {**mine, "description": str(shared.id), "except": None}
    found = (
        await client.post("/api/criteria/similar", json=narrowed, headers=admin)
    ).json()
    assert found["count"] == 1
    assert (await pangloss_criteria.similar("Person", {}, shared.id)).count == 2


@no_type_check
async def test_share_makes_a_description_and_documents_that_hold_the_criteria_cite_it(
    clear_database, client, db_driver, monkeypatch
):
    admin = await bearer(client)
    court = await a_court(client)
    Activity = client.m["Activity"]
    mark = "01a1c564-7def-70f0-bd21-410a35c82ab9"
    a = await court.activity("A", own(court.of()), own(court.of("Waldauf")))
    b = await court.activity(
        "B", {**own(court.of()), "same_one": mark}, {"type": NAME, "same_one": mark}
    )
    stale = await court.activity("C", own(court.of()))
    open_in_form = await court.activity("D", own(court.of()))
    await run_pending()

    # (one changes after it is found: its update is refused, and said)
    read_view = sharing.read_view

    async def changed_meanwhile(model, id):
        view = await read_view(model, id)
        if str(id) == str(stale.id):
            await Activity.Update(**view.model_dump()).save()
        return view

    monkeypatch.setattr(sharing, "read_view", changed_meanwhile)
    body = {
        "label": "Maximilian's secretary",
        **court.of(),
        "except": str(open_in_form.id),
    }
    assert (await client.post("/api/criteria/share", json=body)).status_code == 401
    response = await client.post("/api/criteria/share", json=body, headers=admin)
    assert response.status_code == 200, response.text
    done = response.json()
    assert done["description"]["type"] == "Description"
    assert done["description"]["label"] == "Maximilian's secretary"
    assert done["updated"] == 2
    (failed,) = done["failed"]
    assert failed["head"]["id"] == str(stale.id)
    assert "PanglossVersionConflictError" in failed["detail"]

    shared_id = done["description"]["id"]
    read = await Activity.get(a.id)
    assert str(read.carried_out_by[0].description.target_id) == shared_id
    assert read.carried_out_by[0].criteria is None
    # (other criteria are left as they are)
    assert read.carried_out_by[1].description is None
    assert read.carried_out_by[1].criteria == SearchPattern(court.of("Waldauf"))
    assert read.meta.version == 2
    read = await Activity.get(b.id)
    assert str(read.carried_out_by[0].description.target_id) == shared_id
    assert read.carried_out_by[1].description is None
    # (the document open in the form is not updated)
    assert (await Activity.get(open_in_form.id)).meta.version == 1
    await run_pending()
    assert [p.label for p in (await Activity.get(b.id)).carried_out_by[1].target] == [
        "Serntein",
        "Waldauf",
    ]


@no_type_check
async def test_share_is_refused_past_the_limit_of_the_route_but_not_from_python(
    clear_database, client, monkeypatch
):
    admin = await bearer(client)
    court = await a_court(client)
    for label in ("A", "B", "C"):
        await court.activity(label, own(court.of()))
    monkeypatch.setattr(sharing, "MAX_DOCUMENTS", 2)
    body = {"label": "Secretary", **court.of()}
    response = await client.post("/api/criteria/share", json=body, headers=admin)
    assert response.status_code == 422
    assert "pangloss_criteria.share" in response.json()["detail"]
    assert (await client.get("/api/criteria/shared")).json()["count"] == 0
    done = await pangloss_criteria.share("Secretary", court.of())
    assert done.updated == 3 and done.failed == []


# --- through the SDK ------------------------------------------------------------------------------------------------


async def sdk_settings():
    import pangloss_core.settings as core_settings
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
async def test_the_sdk_asks_the_routes_of_shared_descriptions_and_gives_the_same(
    clear_database, client, monkeypatch
):
    from pangloss_criteria import access
    from pangloss_sdk import client as sdk_client

    # (the user the SDK logs in as)
    await bearer(client)
    court = await a_court(client)
    shared = (
        await client.m["Description"]
        .Create(label="Secretary", criteria=court.of())
        .save()
    )
    await court.activity("A", citing(shared), own(court.of()))
    await court.activity("B", own(court.of()))
    direct = (
        await pangloss_criteria.shared(["Person"]),
        await pangloss_criteria.shared_mentions(shared.id),
        await pangloss_criteria.preview(None, (), shared.id),
    )

    sdk = sdk_client.AsyncClient(
        await sdk_settings(), httpx.ASGITransport(app=create_app())
    )
    sdk_client.install(sdk)
    monkeypatch.setattr(access, "storage_kind", lambda: "api")
    try:
        assert await pangloss_criteria.shared(["Person"]) == direct[0]
        assert await pangloss_criteria.shared_mentions(shared.id) == direct[1]
        assert await pangloss_criteria.shared_mentions(court.secretary.id) is None
        assert await pangloss_criteria.preview(None, (), shared.id) == direct[2]
        similar = await pangloss_criteria.similar("Person", court.of()["where"])
        assert similar.count == 2
        done = await pangloss_criteria.share("Maximilian's secretary", court.of())
        assert done.updated == 2 and done.failed == []
    finally:
        await sdk.close()
        sdk_client.install(None)
