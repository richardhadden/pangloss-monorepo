"""An entity made with its companions (implementation_docs/companion-documents.md): `save_with_companions` in Python and
`POST /api/NAME/with-companions` write the entity and each companion, with the entity in its parts, in one
transaction; what the declaration does not allow, or is not valid, is a 422 at its place, and nothing is written"""

from typing import no_type_check

import httpx2 as httpx
import pytest
from pangloss_api import create_app
from pangloss_models import (
    Companion,
    CompanionPart,
    CopyFromOuter,
    Document,
    Entity,
    PanglossWriteRefused,
    ReifiedRelation,
    Standalone,
    Within,
    initialise,
)
from pangloss_users import service

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


@no_type_check
def declare():
    class Source(Entity):
        pass

    class AtPage[T](ReifiedRelation[T]):
        page: str
        _meta = ReifiedRelation.Meta(label_template="{target}, p. {page}")

    class Person(Entity):
        _meta = Entity.Meta(
            companions=[
                Companion(
                    name="naming_and_gender",
                    document="Factoid",
                    field="statements",
                    parts=[
                        CompanionPart(type="Naming", entity_field="named"),
                        CompanionPart(type="Gendering", entity_field="gendered"),
                    ],
                    copies=[CopyFromOuter(field="source")],
                    offered=[Within(heads=["Factoid"]), Standalone()],
                )
            ]
        )

    class Naming(Document):
        named: Person
        first_name: str | None = None
        _meta = Document.Meta(label_template="{named} named {first_name}")

    class Gendering(Document):
        gendered: Person
        gender: str
        _meta = Document.Meta(label_template="{gendered}: {gender}")

    class Factoid(Document):
        source: AtPage[Source]
        statements: list[Naming | Gendering]
        _meta = Document.Meta(label_template='{source}: {statements|join("; ")}')

    initialise()
    return Source, Person, Factoid


def at_page(source) -> dict:
    return {
        "type": "AtPage",
        "page": "12",
        "target": [{"type": "Source", "id": str(source.id)}],
    }


def heads(db_driver) -> list[str]:
    return sorted(
        r["type"] for r in run(db_driver, "MATCH (n:HeadNode) RETURN n.type AS type")
    )


@no_type_check
async def test_an_entity_is_saved_with_its_companion_which_names_it(
    db_driver, clear_database
):
    Source, Person, Factoid = declare()
    chronicle = await Source.Create(label="Chronicle").save()

    person, (factoid,) = await Person.Create(
        label="John of Gaunt"
    ).save_with_companions(
        {
            "naming_and_gender": {
                "source": at_page(chronicle),
                "statements": [{"type": "Naming", "first_name": "John"}],
            }
        }
    )

    assert person.label == "John of Gaunt"
    assert factoid.type == "Factoid"
    assert factoid.label == "Chronicle, p. 12: John of Gaunt named John"
    read = await Factoid.get(factoid.id)
    assert read.statements[0].named.id == person.id
    assert (await Person.get(person.id)).named_reverse[
        0
    ].label == "John of Gaunt named John"


@no_type_check
async def test_with_no_companions_it_is_saved_alone(db_driver, clear_database):
    _, Person, _ = declare()

    person, companions = await Person.Create(label="Blanche").save_with_companions({})

    assert companions == []
    assert heads(db_driver) == ["Person"]
    assert (await Person.get(person.id)).label == "Blanche"


@no_type_check
async def test_a_companion_that_is_refused_leaves_nothing_written(
    db_driver, clear_database
):
    Source, Person, _ = declare()
    chronicle = await Source.Create(label="Chronicle").save()

    with pytest.raises(PanglossWriteRefused):
        await Person.Create(label="Blanche").save_with_companions(
            {"naming_and_gender": {"source": at_page(chronicle), "statements": []}}
        )

    assert heads(db_driver) == ["Source"]


def client_for(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def logged_in(client, username="john") -> dict:
    if await service.get_user(username) is None:
        await service.create_user(username, f"{username}@example.com", PASSWORD)
    response = await client.post(
        "/api/users/token", data={"username": username, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@no_type_check
async def test_the_route_makes_the_entity_and_its_companions_and_answers_both(
    db_driver, clear_database
):
    Source, Person, Factoid = declare()
    chronicle = await Source.Create(label="Chronicle").save()
    async with client_for(create_app()) as client:
        body = {
            "item": {"type": "Person", "label": "Katherine Swynford"},
            "companions": [
                {
                    "name": "naming_and_gender",
                    "document": {
                        "source": at_page(chronicle),
                        "statements": [
                            {"type": "Naming", "firstName": "Katherine"},
                            {"type": "Gendering", "gender": "female"},
                        ],
                    },
                }
            ],
        }
        assert (
            await client.post("/api/Person/with-companions", json=body)
        ).status_code == 401

        response = await client.post(
            "/api/Person/with-companions", json=body, headers=await logged_in(client)
        )

    assert response.status_code == 201, response.text
    answer = response.json()
    assert answer["item"]["type"] == "Person"
    assert answer["item"]["label"] == "Katherine Swynford"
    (factoid,) = answer["companions"]
    assert (
        factoid["label"]
        == "Chronicle, p. 12: Katherine Swynford named Katherine; Katherine Swynford: female"
    )
    naming, gendering = (await Factoid.get(factoid["id"])).statements
    assert str(naming.named.id) == str(gendering.gendered.id) == answer["item"]["id"]
    assert response.headers["ETag"] == '"1"'


@no_type_check
async def test_a_companion_not_valid_is_a_422_at_its_place_in_the_body_and_nothing_is_written(
    db_driver, clear_database
):
    Source, _, _ = declare()
    chronicle = await Source.Create(label="Chronicle").save()
    async with client_for(create_app()) as client:
        john = await logged_in(client)

        def sent(document, name="naming_and_gender"):
            return client.post(
                "/api/Person/with-companions",
                json={
                    "item": {"type": "Person", "label": "K"},
                    "companions": [{"name": name, "document": document}],
                },
                headers=john,
            )

        # (invalid for its model: a gendering without its gender)
        invalid = await sent(
            {"source": at_page(chronicle), "statements": [{"type": "Gendering"}]}
        )
        # (refused by the declaration: the entity's field is the server's)
        refused = await sent(
            {
                "source": at_page(chronicle),
                "statements": [
                    {
                        "type": "Naming",
                        "named": {"type": "Person", "id": str(chronicle.id)},
                    }
                ],
            }
        )
        unknown = await sent({}, name="other")
        bad_item = await client.post(
            "/api/Person/with-companions",
            json={
                "item": {"type": "Person", "label": "K", "nope": 1},
                "companions": [],
            },
            headers=john,
        )

    assert invalid.status_code == 422, invalid.text
    (problem,) = invalid.json()["detail"]
    assert problem["loc"][:6] == ["body", "companions", 0, "document", "statements", 0]
    assert problem["loc"][-1] == "gender"

    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"][0]["loc"] == [
        "body",
        "companions",
        0,
        "document",
        "statements",
        0,
        "named",
    ]

    assert unknown.status_code == 422
    assert "has no companion called 'other'" in unknown.json()["detail"][0]["msg"]

    assert bad_item.status_code == 422
    assert bad_item.json()["detail"][0]["loc"][:2] == ["body", "item"]

    assert heads(db_driver) == ["Source"]


@no_type_check
async def test_only_an_entity_with_companions_has_the_route(db_driver, clear_database):
    Source, _, _ = declare()
    async with client_for(create_app()) as client:
        response = await client.post(
            "/api/Source/with-companions",
            json={"item": {"type": "Source", "label": "S"}, "companions": []},
            headers=await logged_in(client),
        )
    assert response.status_code in (404, 405)
    assert heads(db_driver) == []
