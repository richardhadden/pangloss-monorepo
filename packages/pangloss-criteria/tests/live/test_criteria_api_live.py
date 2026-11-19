"""A description over the API: written in a document as any reified relation is, read with its candidates as the
reader may see them, and refused with the path in its criteria when they do not fit"""

import importlib
from typing import no_type_check

import httpx2 as httpx
import pangloss_criteria.models
import pytest
import pytest_asyncio
from pangloss_api import create_app
from pangloss_core import storage_of
from pangloss_criteria import run_pending
from pangloss_models import Document, Entity, initialise
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


def models():
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Person(Entity):
        pass

    class HoldsOffice(Document):
        holder: Person
        employer: Person

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]

    initialise()
    return Person, HoldsOffice, Activity


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    Person, HoldsOffice, Activity = models()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.models = (Person, HoldsOffice, Activity)
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


async def people(client, admin, *labels):
    made = {}
    for label in labels:
        response = await client.post(
            "/api/Person", json={"label": label}, headers=admin
        )
        assert response.status_code == 201, response.text
        made[label] = response.json()["id"]
    return made


@no_type_check
async def test_a_description_is_written_read_and_updated_over_the_api(
    client, clear_database
):
    admin = await bearer(client)
    Person, HoldsOffice, Activity = client.models
    ids = await people(client, admin, "Maximilian", "Waldauf", "Serntein")
    for holder in ("Waldauf", "Serntein"):
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
        hidden = response.json()["id"]
    # (what makes Serntein a candidate is not published)
    await storage_of().operations.set_published_in_db(HoldsOffice, hidden, False)
    await run_pending()

    created = await client.post(
        "/api/Activity",
        json={
            "label": "A letter carried",
            "carriedOutBy": [
                {
                    "type": "MatchesCriteria",
                    "wording": "N. N., servitor Maximiliani",
                    "criteria": employed_by(ids["Maximilian"]),
                }
            ],
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    activity = created.json()["id"]
    await run_pending()

    read = (await client.get(f"/api/Activity/{activity}", headers=admin)).json()
    (described,) = read["carriedOutBy"]
    assert described["type"] == "MatchesCriteria"
    assert described["wording"] == "N. N., servitor Maximiliani"
    assert described["criteria"] == employed_by(ids["Maximilian"])
    assert [(c["type"], c["label"]) for c in described["target"]] == [
        ("Person", "Serntein"),
        ("Person", "Waldauf"),
    ]
    assert described["candidateCount"] == 2
    assert described["evaluatedWhen"] is not None and described["broken"] is None
    assert read["meta"]["version"] == 1
    # (what the worker keeps of the criteria is not part of what is read)
    assert {"criteriaHash", "dependsOn", "names", "candidateCountEveryone"} & set(
        described
    ) == set()

    # (not logged in: the candidates everyone may see, and their count)
    public = (await client.get(f"/api/Activity/{activity}")).json()
    (seen,) = public["carriedOutBy"]
    assert [c["label"] for c in seen["target"]] == ["Waldauf"]
    assert seen["candidateCount"] == 1

    # (what was read is sent back as it is, with a change of the head: the computed fields are ignored there)
    edited = (await client.get(f"/api/Activity/{activity}/edit", headers=admin)).json()
    edited["label"] = "A letter carried to Innsbruck"
    edited["carriedOutBy"][0]["target"] = []
    edited["carriedOutBy"][0]["candidateCount"] = 99
    updated = await client.put(
        f"/api/Activity/{activity}", json=edited, headers={**admin, "If-Match": "1"}
    )
    assert updated.status_code in (200, 204), updated.text
    again = (await client.get(f"/api/Activity/{activity}", headers=admin)).json()
    assert again["label"] == "A letter carried to Innsbruck"
    assert again["meta"]["version"] == 2
    # (kept meanwhile, since the description says the same)
    assert [c["label"] for c in again["carriedOutBy"][0]["target"]] == [
        "Serntein",
        "Waldauf",
    ]
    assert again["carriedOutBy"][0]["candidateCount"] == 2

    # (a candidate's page lists the document it may be in)
    waldauf = (await client.get(f"/api/Person/{ids['Waldauf']}", headers=admin)).json()
    held = [
        item["label"]
        for value in waldauf.values()
        if isinstance(value, list)
        for item in value
        if isinstance(item, dict) and item.get("type") == "Activity"
    ]
    assert held == ["A letter carried to Innsbruck"]


@no_type_check
async def test_criteria_that_do_not_fit_are_a_422_that_names_the_path(
    client, clear_database
):
    admin = await bearer(client)
    ids = await people(client, admin, "Maximilian")

    async def post(description):
        return await client.post(
            "/api/Activity",
            json={"label": "X", "carriedOutBy": [description]},
            headers=admin,
        )

    wrong_field = await post(
        {
            "type": "MatchesCriteria",
            "criteria": {
                "type": "Person",
                "where": {
                    "$incoming": [
                        {"type": "HoldsOffice", "where": {"salary": {"gt": 3}}}
                    ]
                },
            },
        }
    )
    assert wrong_field.status_code == 422, wrong_field.text
    assert "$incoming.salary: HoldsOffice has no field 'salary'" in wrong_field.text
    # (at the description, as a 422 of a field is: a form shows it there)
    (detail,) = wrong_field.json()["detail"]
    assert detail["loc"] == ["body", "carriedOutBy", 0]
    assert detail["msg"].startswith("criteria: $incoming.salary")
    assert wrong_field.json()["error"] == "PanglossWriteRefused"

    wrong_type = await post(
        {"type": "MatchesCriteria", "criteria": {"type": "HoldsOffice"}}
    )
    assert wrong_type.status_code == 422
    assert "'HoldsOffice' is not what is described here (Person)" in wrong_type.text

    none = await post({"type": "MatchesCriteria", "wording": "N. N."})
    assert none.status_code == 422
    assert "a description needs the criteria it is of" in none.text

    refused_key = await post(
        {
            "type": "MatchesCriteria",
            "criteria": {
                "type": "Person",
                "where": {"$same_as": {"is": ids["Maximilian"]}},
            },
        }
    )
    assert refused_key.status_code == 422
    assert "'$same_as' cannot be in a stored pattern" in refused_key.text

    not_a_pattern = await post({"type": "MatchesCriteria", "criteria": "Person"})
    assert not_a_pattern.status_code == 422

    listed = (await client.get("/api/Activity", headers=admin)).json()
    assert listed["count"] == 0


@no_type_check
async def test_the_server_runs_the_worker_unless_told_not_to(client, monkeypatch):
    from pangloss_criteria import api
    from pangloss_criteria.worker import worker

    class App:
        class state:
            background_tasks: list = []

    api.configure_app(App, type("Settings", (), {})())
    assert [task.name for task in App.state.background_tasks] == ["criteria"]
    assert App.state.background_tasks[0].run == worker.run

    App.state.background_tasks.clear()
    api.configure_app(App, type("Settings", (), {"CRITERIA_WORKER_IN_SERVER": False})())
    assert App.state.background_tasks == []
