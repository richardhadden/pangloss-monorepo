"""The routes made from the models, with the data in Memgraph"""

import datetime
from enum import Enum
from typing import no_type_check
from uuid import uuid7

import httpx2 as httpx
import pytest
from pangloss_api.app import create_app
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


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
async def test_crud_flow(db_driver, clear_database):
    class Place(Entity):
        pass

    class Person(Entity):
        born_in: Place

    class Statement(Document):
        text: str
        about: Person

    app = create_app()
    async with client_for(app) as client:
        john = await logged_in(client)

        # Everything can be looked at, by anyone
        empty = await client.get("/api/entities/Person")
        assert empty.status_code == 200
        assert empty.json()["results"] == []
        assert empty.json()["count"] == 0

        # ... but not changed
        person_url = "/api/entities/Person"
        some_id = uuid7()
        for method, url, body in (
            ("POST", person_url, {"type": "Person", "label": "x"}),
            ("GET", f"{person_url}/{some_id}/edit", None),
            ("PUT", f"{person_url}/{some_id}", {"type": "Person", "id": str(some_id)}),
            ("DELETE", f"{person_url}/{some_id}", None),
            ("POST", f"{person_url}/{some_id}/undelete", None),
            ("POST", "/api/documents/Statement", {"type": "Statement"}),
            ("DELETE", f"/api/documents/Statement/{some_id}", None),
        ):
            response = await client.request(method, url, json=body)
            assert response.status_code == 401, (method, url)

        # Creating
        place = await client.post(
            "/api/entities/Place", json={"type": "Place", "label": "Paris"}, headers=john
        )
        assert place.status_code == 201, place.text
        place_id = place.json()["id"]
        assert place.json()["label"] == "Paris"
        assert place.json()["type"] == "Place"

        response = await client.post(
            person_url,
            json={
                "type": "Person",
                "label": "John Smith",
                "bornIn": {"type": "Place", "id": place_id},
            },
            headers=john,
        )
        assert response.status_code == 201, response.text
        person_id = response.json()["id"]

        response = await client.post(
            "/api/documents/Statement",
            params={"detail": "true"},
            json={
                "type": "Statement",
                "label": "A Statement",
                "text": "John was born",
                "about": {"type": "Person", "id": person_id},
            },
            headers=john,
        )
        assert response.status_code == 201, response.text
        statement = response.json()
        statement_id = statement["id"]
        assert statement["text"] == "John was born"
        assert statement["about"]["id"] == person_id
        assert "meta" in statement  # (a HeadView)

        # Reading, by anyone
        statement_url = f"/api/documents/Statement/{statement_id}"
        read = await client.get(statement_url)
        assert read.status_code == 200
        assert read.json()["text"] == "John was born"

        person = (await client.get(f"{person_url}/{person_id}")).json()
        # (the user who made the request is recorded as the creator)
        assert person["meta"]["createdBy"] == "john"
        assert statement["meta"]["createdBy"] == "john"
        assert person["bornIn"]["label"] == "Paris"
        assert [s["id"] for s in person["aboutReverse"]] == [statement_id]

        # The entity to edit has no incoming relations
        edit = await client.get(f"{person_url}/{person_id}/edit", headers=john)
        assert edit.status_code == 200
        assert "aboutReverse" not in edit.json()
        assert edit.json()["bornIn"]["id"] == place_id
        # ... and a document to edit is its whole HeadView
        doc_edit = await client.get(f"{statement_url}/edit", headers=john)
        assert doc_edit.json()["text"] == "John was born"

        # Listing and searching
        listed = (await client.get("/api/documents/Statement")).json()
        assert listed["count"] == 1
        assert listed["results"][0]["id"] == statement_id
        found = (await client.get("/api/entities/Person", params={"q": "smith"})).json()
        assert [p["id"] for p in found["results"]] == [person_id]
        none = (await client.get("/api/entities/Person", params={"q": "nobody"})).json()
        assert none["results"] == []
        assert (
            await client.get("/api/entities/Person", params={"page": 0})
        ).status_code == 422

        # Updating (a full replacement, which the edit view can be sent back as)
        changes = edit.json()
        changes["label"] = "John Q. Smith"
        response = await client.put(
            f"{person_url}/{person_id}", json=changes, headers=john
        )
        assert response.status_code == 200, response.text
        assert response.json()["label"] == "John Q. Smith"
        after = (await client.get(f"{person_url}/{person_id}")).json()
        assert after["label"] == "John Q. Smith"
        assert after["bornIn"]["id"] == place_id
        assert [s["id"] for s in after["aboutReverse"]] == [statement_id]

        response = await client.put(
            f"{person_url}/{person_id}",
            params={"detail": "true"},
            json=changes,
            headers=john,
        )
        assert "aboutReverse" in response.json()

        # ... the id in the body must be the one in the path, and exist
        response = await client.put(
            f"{person_url}/{some_id}", json=changes, headers=john
        )
        assert response.status_code == 400
        response = await client.put(
            f"{person_url}/{some_id}", json={**changes, "id": str(some_id)}, headers=john
        )
        assert response.status_code == 404

        # Things that are not right
        assert (
            await client.post(person_url, json={"type": "Person"}, headers=john)
        ).status_code == 422
        assert (
            await client.post(
                "/api/documents/Statement",
                json={
                    "type": "Statement",
                    "label": "x",
                    "text": "x",
                    "about": {"type": "Person", "id": str(some_id)},
                },
                headers=john,
            )
        ).status_code == 422
        assert (await client.get(f"{person_url}/{some_id}")).status_code == 404
        assert (await client.get(f"{person_url}/not-an-id")).status_code == 422
        assert (await client.get("/api/entities/Nothing")).status_code == 404

        # Deleting an entity that is referred to is refused (and says by what)
        response = await client.delete(f"{person_url}/{person_id}", headers=john)
        assert response.status_code == 409
        assert response.json()["referencedBy"][0]["id"] == statement_id

        # Deleting a document, undeleting it, and then the entity can go
        assert (await client.delete(statement_url, headers=john)).status_code == 204
        assert (await client.get(statement_url)).status_code == 404
        assert (await client.get("/api/documents/Statement")).json()["count"] == 0

        assert (
            await client.post(f"{statement_url}/undelete", headers=john)
        ).status_code == 204
        assert (await client.get(statement_url)).status_code == 200
        # (not deleted now)
        assert (
            await client.post(f"{statement_url}/undelete", headers=john)
        ).status_code == 409

        assert (await client.delete(statement_url, headers=john)).status_code == 204
        assert (await client.delete(statement_url, headers=john)).status_code == 404
        assert (
            await client.delete(f"{person_url}/{person_id}", headers=john)
        ).status_code == 204
        assert (await client.get(f"{person_url}/{person_id}")).status_code == 404


def snake_case_keys(value) -> list[str]:
    if isinstance(value, dict):
        found = [key for key in value if "_" in key]
        return found + [k for item in value.values() for k in snake_case_keys(item)]
    if isinstance(value, list):
        return [k for item in value for k in snake_case_keys(item)]
    return []


@no_type_check
async def test_the_json_is_camel_case_throughout(db_driver, clear_database):
    class Place(Entity):
        pass

    class Date(Embedded):
        start_date: datetime.date

    class Person(Entity):
        born_in: Place
        nick_name: str

    class Statement(Document):
        about_person: Person
        written_on: Date

    app = create_app()
    async with client_for(app) as client:
        headers = await logged_in(client)
        place = (
            await client.post(
                "/api/entities/Place", json={"type": "Place", "label": "P"}, headers=headers
            )
        ).json()
        person = (
            await client.post(
                "/api/entities/Person",
                json={
                    "type": "Person",
                    "label": "J",
                    "nickName": "j",
                    "bornIn": {"type": "Place", "id": place["id"]},
                },
                headers=headers,
            )
        ).json()
        # (names are accepted too)
        statement = await client.post(
            "/api/documents/Statement",
            params={"detail": "true"},
            json={
                "type": "Statement",
                "label": "S",
                "about_person": {"type": "Person", "id": person["id"]},
                "written_on": {"type": "Date", "start_date": "2020-01-01"},
            },
            headers=headers,
        )
        assert statement.status_code == 201, statement.text
        statement_id = statement.json()["id"]

        responses = {
            "created person": person,
            "created statement": statement.json(),
            "person": (await client.get(f"/api/entities/Person/{person['id']}")).json(),
            "statement": (
                await client.get(f"/api/documents/Statement/{statement_id}")
            ).json(),
            "edit": (
                await client.get(
                    f"/api/entities/Person/{person['id']}/edit", headers=headers
                )
            ).json(),
            "list": (await client.get("/api/documents/Statement")).json(),
            "conflict": (
                await client.delete(f"/api/entities/Person/{person['id']}", headers=headers)
            ).json(),
        }
        for name, body in responses.items():
            assert snake_case_keys(body) == [], name

        assert responses["person"]["nickName"] == "j"
        assert responses["person"]["aboutPersonReverse"][0]["id"] == statement_id
        assert responses["statement"]["writtenOn"]["startDate"] == "2020-01-01"
        assert "referencedBy" in responses["conflict"]

        # ... and so is the OpenAPI document's description of it
        schema = (await client.get("/openapi.json")).json()
        properties = {
            name
            for component in schema["components"]["schemas"].values()
            for name in component.get("properties", {})
        }
        assert {"nickName", "bornIn", "aboutPersonReverse", "writtenOn"} <= properties
        assert not {"nick_name", "born_in", "about_person_reverse"} & properties


@no_type_check
async def test_a_nested_document_is_not_deleted_on_its_own(db_driver, clear_database):
    class Action(Document):
        pass

    class Statement(Document):
        action: Action

    app = create_app()
    async with client_for(app) as client:
        headers = await logged_in(client)
        saved = await client.post(
            "/api/documents/Statement",
            params={"detail": "true"},
            json={
                "type": "Statement",
                "label": "S",
                "action": {"type": "Action", "label": "A"},
            },
            headers=headers,
        )
        action_id = saved.json()["action"]["id"]
        response = await client.delete(
            f"/api/documents/Action/{action_id}", headers=headers
        )
        assert response.status_code == 400


@no_type_check
async def test_a_disabled_user_cannot_change_things(db_driver, clear_database):
    class Person(Entity):
        pass

    app = create_app()
    async with client_for(app) as client:
        headers = await logged_in(client)
        await service.set_disabled("john", True)
        response = await client.post(
            "/api/entities/Person", json={"type": "Person", "label": "x"}, headers=headers
        )
        assert response.status_code == 401
        assert (await client.get("/api/entities/Person")).status_code == 200


@no_type_check
async def test_routes_are_made_for_concrete_models_only(db_driver, clear_database):
    class Person(Entity):
        pass

    class Poet(Person):
        pass

    class Base(Document):
        _meta = Document.Meta(abstract=True)

    class Statement(Base):
        pass

    app = create_app()
    paths = set(app.openapi()["paths"])
    assert "/api/entities/Person" in paths
    assert "/api/entities/Poet/{id}" in paths
    assert "/api/documents/Statement/{id}/undelete" in paths
    assert not any("/Base" in path for path in paths)


@no_type_check
async def test_listing_a_parent_type_includes_subtypes(db_driver, clear_database):
    class Person(Entity):
        pass

    class Poet(Person):
        pass

    app = create_app()
    async with client_for(app) as client:
        headers = await logged_in(client)
        for kind, label in (("Person", "A person"), ("Poet", "A poet")):
            response = await client.post(
                f"/api/entities/{kind}",
                json={"type": kind, "label": label},
                headers=headers,
            )
            assert response.status_code == 201, response.text

        listed = (await client.get("/api/entities/Person")).json()
        assert {(r["type"], r["label"]) for r in listed["results"]} == {
            ("Person", "A person"),
            ("Poet", "A poet"),
        }
        only = (await client.get("/api/entities/Poet")).json()
        assert [r["type"] for r in only["results"]] == ["Poet"]


@no_type_check
async def test_openapi_for_models_using_most_features(db_driver, clear_database):
    class Colour(Enum):
        RED = "red"
        BLUE = "blue"

    class Place(Entity):
        pass

    class Person(Entity):
        born: datetime.date
        favourite: Colour
        born_in: Place

    class Date(Embedded):
        when: datetime.date

    class DateRange(Embedded):
        start: datetime.date
        end: datetime.date

    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Identification[T](ReifiedRelation[T]):
        certainty: int

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        detail: str

    class Statement(Document):
        name: WithCertainty[str]
        date: Date | DateRange
        action: Action
        who: Identification[Person]
        maybe: list[Person | Negative[Person]]

    app = create_app()
    async with client_for(app) as client:
        response = await client.get("/openapi.json")
        assert response.status_code == 200, response.text[:500]
        schema = response.json()
        assert "/api/documents/Statement/{id}" in schema["paths"]
        assert "/api/entities/Person/{id}/edit" in schema["paths"]
        operations = [
            op["operationId"]
            for path in schema["paths"].values()
            for op in path.values()
        ]
        assert len(operations) == len(set(operations))

        docs = await client.get("/docs")
        assert docs.status_code == 200
