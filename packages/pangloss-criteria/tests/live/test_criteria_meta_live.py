"""A description offered by the entity's class (`CriteriaMeta(allowed=True)`), with no word of it in the annotation:
stored, evaluated and read as one the annotation writes out, in a relation of the document, inside a wrapper, and
with the properties of the relation; over the API too"""

import importlib
from typing import Annotated, no_type_check

import httpx2 as httpx
import pangloss_criteria.models
import pytest
from pangloss_api import create_app
from pangloss_criteria import CriteriaMeta, NoCriteria, run_pending
from pangloss_criteria.worker import is_pending
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    ReifiedRelation,
    Trait,
    ViaEdge,
    initialise,
)
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        _criteria_meta = CriteriaMeta(allowed=True)

    class Group(Entity, Agent):
        _criteria_meta = CriteriaMeta(allowed=True)

    class Certainty(EdgeModel):
        certainty: int = 100

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class HoldsOffice(Document):
        holder: Annotated[Person, NoCriteria()]
        employer: Annotated[Agent, NoCriteria()]

    class Activity(Document):
        carried_out_by: list[Agent]
        perhaps: list[ViaEdge[Person, Certainty]]
        in_role: list[InRole[Agent]]

    initialise()
    return Person, Group, HoldsOffice, Activity


def ref(item):
    return {"type": type(item)._owner.__name__, "id": item.id}


def employed_by(employer, type: str = "Person") -> dict:
    return {
        "type": type,
        "where": {
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "holder",
                    "where": {"employer": {"is": str(employer.id)}},
                }
            ]
        },
    }


@no_type_check
async def a_court():
    Person, Group, HoldsOffice, Activity = models()
    maximilian = await Person.Create(label="Maximilian").save()
    for name in ("Waldauf", "Serntein"):
        holder = await Person.Create(label=name).save()
        await HoldsOffice.Create(
            label=f"{name} serves", holder=ref(holder), employer=ref(maximilian)
        ).save()
    return Activity, maximilian


def labels(items) -> list[str]:
    return [item.label for item in items]


@no_type_check
async def test_a_description_given_by_the_setting_is_evaluated_as_any_other(
    clear_database,
):
    Activity, maximilian = await a_court()
    # (the documents of the court cannot hold a description: every field of theirs refuses it)
    assert await run_pending() == 0

    activity = await Activity.Create(
        label="A letter carried",
        carried_out_by=[
            ref(maximilian),
            {
                "type": "MatchesCriteria",
                "wording": "N. N., servitor",
                "criteria": employed_by(maximilian),
            },
        ],
        perhaps=[],
        in_role=[],
    ).save()

    assert await is_pending(activity.id)
    assert await run_pending() == 1
    read = await Activity.get(activity.id)
    named, described = sorted(
        read.carried_out_by, key=lambda item: item.type, reverse=True
    )
    assert named.label == "Maximilian"
    assert (
        described.type == "MatchesCriteria" and described.wording == "N. N., servitor"
    )
    assert labels(described.target) == ["Serntein", "Waldauf"]
    assert described.candidate_count == 2 and described.broken is None


@no_type_check
async def test_one_inside_a_wrapper_and_one_with_the_relations_properties(
    clear_database,
):
    Activity, maximilian = await a_court()
    activity = await Activity.Create(
        label="A letter written",
        carried_out_by=[],
        perhaps=[
            {
                "type": "MatchesCriteria",
                "wording": "perhaps the secretary",
                "criteria": employed_by(maximilian),
                "edge_properties": {"certainty": 60},
            }
        ],
        in_role=[
            {
                "type": "InRole",
                "role": "scribe",
                "target": [
                    {"type": "MatchesCriteria", "criteria": employed_by(maximilian)}
                ],
            }
        ],
    ).save()

    assert await run_pending() == 1

    read = await Activity.get(activity.id)
    (perhaps,) = read.perhaps
    assert perhaps.edge_properties.certainty == 60
    assert labels(perhaps.target) == ["Serntein", "Waldauf"]
    (in_role,) = read.in_role
    (described,) = in_role.target
    assert in_role.role == "scribe" and described.type == "MatchesCriteria"
    assert labels(described.target) == ["Serntein", "Waldauf"]

    # (an update that leaves them as they are keeps what was found)
    payload = read.model_dump(mode="json", by_alias=True)
    payload.pop("meta")
    await Activity.Update(**{**payload, "label": "A letter, written"}).save()
    again = await Activity.get(activity.id)
    assert labels(again.perhaps[0].target) == ["Serntein", "Waldauf"]
    assert labels(again.in_role[0].target[0].target) == ["Serntein", "Waldauf"]


@no_type_check
async def test_over_the_api_it_is_taken_where_the_class_allows_and_refused_where_the_field_says_no(
    clear_database,
):
    Activity, maximilian = await a_court()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await service.create_user("root", "root@example.com", PASSWORD, admin=True)
        token = await client.post(
            "/api/users/token", data={"username": "root", "password": PASSWORD}
        )
        admin = {"Authorization": f"Bearer {token.json()['access_token']}"}
        description = {
            "type": "MatchesCriteria",
            "wording": "N. N.",
            "criteria": employed_by(maximilian),
        }

        created = await client.post(
            "/api/Activity",
            json={
                "label": "A letter carried",
                "carriedOutBy": [description],
                "perhaps": [],
                "inRole": [],
            },
            headers=admin,
        )
        assert created.status_code == 201, created.text
        await run_pending()
        read = (
            await client.get(f"/api/Activity/{created.json()['id']}", headers=admin)
        ).json()
        (described,) = read["carriedOutBy"]
        assert [c["label"] for c in described["target"]] == ["Serntein", "Waldauf"]
        assert described["candidateCount"] == 2

        # (criteria of a class that is not of the relation: a group is not a person who is perhaps there)
        wrong = await client.post(
            "/api/Activity",
            json={
                "label": "A letter carried",
                "carriedOutBy": [],
                "perhaps": [
                    {**description, "criteria": {"type": "Group", "where": {}}}
                ],
                "inRole": [],
            },
            headers=admin,
        )
        assert wrong.status_code == 422, wrong.text
        assert "criteria" in wrong.text

        refused = await client.post(
            "/api/HoldsOffice",
            json={
                "label": "Someone serves",
                "holder": description,
                "employer": {"type": "Person", "id": str(maximilian.id)},
            },
            headers=admin,
        )
        assert refused.status_code == 422, refused.text
