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
        empty = await client.get("/api/Person")
        assert empty.status_code == 200
        assert empty.json()["results"] == []
        assert empty.json()["count"] == 0

        # ... but not changed
        person_url = "/api/Person"
        some_id = uuid7()
        for method, url, body in (
            ("POST", person_url, {"type": "Person", "label": "x"}),
            ("GET", f"{person_url}/{some_id}/edit", None),
            ("PUT", f"{person_url}/{some_id}", {"type": "Person", "id": str(some_id)}),
            ("DELETE", f"{person_url}/{some_id}", None),
            ("POST", f"{person_url}/{some_id}/undelete", None),
            ("POST", "/api/Statement", {"type": "Statement"}),
            ("DELETE", f"/api/Statement/{some_id}", None),
        ):
            response = await client.request(method, url, json=body)
            assert response.status_code == 401, (method, url)

        # Creating
        place = await client.post(
            "/api/Place", json={"type": "Place", "label": "Paris"}, headers=john
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
            "/api/Statement",
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
        statement_url = f"/api/Statement/{statement_id}"
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
        listed = (await client.get("/api/Statement")).json()
        assert listed["count"] == 1
        assert listed["results"][0]["id"] == statement_id
        found = (await client.get("/api/Person", params={"q": "smith"})).json()
        assert [p["id"] for p in found["results"]] == [person_id]
        none = (await client.get("/api/Person", params={"q": "nobody"})).json()
        assert none["results"] == []
        assert (await client.get("/api/Person", params={"page": 0})).status_code == 422

        # Updating (a full replacement, which the edit view can be sent back as)
        changes = edit.json()
        changes["label"] = "John Q. Smith"
        # (an update says which version of the edit view it is based on)
        assert edit.headers["etag"] == '"1"'
        assert edit.json()["meta"]["version"] == 1
        based_on = {**john, "If-Match": edit.headers["etag"]}
        response = await client.put(
            f"{person_url}/{person_id}", json=changes, headers=based_on
        )
        assert response.status_code == 200, response.text
        assert response.json()["label"] == "John Q. Smith"
        assert response.headers["etag"] == '"2"'  # (to go on from)
        after = (await client.get(f"{person_url}/{person_id}")).json()
        assert after["label"] == "John Q. Smith"
        assert after["bornIn"]["id"] == place_id
        assert [s["id"] for s in after["aboutReverse"]] == [statement_id]

        response = await client.put(
            f"{person_url}/{person_id}",
            params={"detail": "true"},
            json=changes,
            headers={**john, "If-Match": '"2"'},
        )
        assert "aboutReverse" in response.json()
        assert response.json()["meta"]["version"] == 3
        assert response.headers["etag"] == '"3"'

        # ... the id in the body must be the one in the path, and exist
        any_version = {**john, "If-Match": "*"}
        response = await client.put(
            f"{person_url}/{some_id}", json=changes, headers=any_version
        )
        assert response.status_code == 400
        response = await client.put(
            f"{person_url}/{some_id}",
            json={**changes, "id": str(some_id)},
            headers=any_version,
        )
        assert response.status_code == 404

        # Things that are not right
        assert (
            await client.post(person_url, json={"type": "Person"}, headers=john)
        ).status_code == 422
        assert (
            await client.post(
                "/api/Statement",
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
        assert (await client.get("/api/Nothing")).status_code == 404

        # Deleting an entity that is referred to is refused (and says by what)
        response = await client.delete(f"{person_url}/{person_id}", headers=john)
        assert response.status_code == 409
        assert response.json()["referencedBy"][0]["id"] == statement_id

        # Deleting a document, undeleting it, and then the entity can go
        assert (await client.delete(statement_url, headers=john)).status_code == 204
        assert (await client.get(statement_url)).status_code == 404
        assert (await client.get("/api/Statement")).json()["count"] == 0

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
                "/api/Place", json={"type": "Place", "label": "P"}, headers=headers
            )
        ).json()
        person = (
            await client.post(
                "/api/Person",
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
            "/api/Statement",
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
            "person": (await client.get(f"/api/Person/{person['id']}")).json(),
            "statement": (await client.get(f"/api/Statement/{statement_id}")).json(),
            "edit": (
                await client.get(f"/api/Person/{person['id']}/edit", headers=headers)
            ).json(),
            "list": (await client.get("/api/Statement")).json(),
            "conflict": (
                await client.delete(f"/api/Person/{person['id']}", headers=headers)
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
            "/api/Statement",
            params={"detail": "true"},
            json={
                "type": "Statement",
                "label": "S",
                "action": {"type": "Action", "label": "A"},
            },
            headers=headers,
        )
        action_id = saved.json()["action"]["id"]
        response = await client.delete(f"/api/Action/{action_id}", headers=headers)
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
            "/api/Person", json={"type": "Person", "label": "x"}, headers=headers
        )
        assert response.status_code == 401
        assert (await client.get("/api/Person")).status_code == 200


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
    assert "/api/Person" in paths
    assert "/api/Poet/{ref}" in paths
    assert "/api/Statement/{id}/undelete" in paths
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
                f"/api/{kind}",
                json={"type": kind, "label": label},
                headers=headers,
            )
            assert response.status_code == 201, response.text

        listed = (await client.get("/api/Person")).json()
        assert {(r["type"], r["label"]) for r in listed["results"]} == {
            ("Person", "A person"),
            ("Poet", "A poet"),
        }
        only = (await client.get("/api/Poet")).json()
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
        assert "/api/Statement/{id}" in schema["paths"]
        assert "/api/Person/{ref}/edit" in schema["paths"]
        operations = [
            op["operationId"]
            for path in schema["paths"].values()
            for op in path.values()
        ]
        assert len(operations) == len(set(operations))

        docs = await client.get("/docs")
        assert docs.status_code == 200


@no_type_check
async def test_an_entity_is_found_by_its_url(db_driver, clear_database):
    class Place(Entity):
        _meta = Entity.Meta(create_with_id=True)

    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)
        born_in: Place

    class Statement(Document):
        about: Person

    app = create_app()
    async with client_for(app) as client:
        headers = await logged_in(client)
        person_url = "http://example.com/people/john-smith"
        place_url = "http://example.com/places/paris?id=5"

        place = await client.post(
            "/api/Place",
            json={
                "type": "Place",
                "id": place_url,
                "createNew": True,
                "label": "Paris",
            },
            headers=headers,
        )
        assert place.status_code == 201, place.text
        # (the url is not the id: the entity is given one)
        assert place.json()["id"] != place_url

        person = await client.post(
            "/api/Person",
            json={
                "type": "Person",
                "id": person_url,
                "createNew": True,
                "label": "John Smith",
                "bornIn": {"type": "Place", "id": place_url},
            },
            headers=headers,
        )
        assert person.status_code == 201, person.text
        person_id = person.json()["id"]

        # Found by the URL, as it is: the same HeadView as by the id
        by_id = await client.get(f"/api/Person/{person_id}")
        found = await client.get(f"/api/Person/{person_url}")
        assert found.status_code == 200, found.text
        assert found.json()["id"] == person_id
        assert found.json() == by_id.json()
        assert found.json()["bornIn"]["id"] == place.json()["id"]
        assert found.json()["urls"] == [person_url]

        # The URLs are edited with the rest: the edit view is sent back changed
        anyversion = {**headers, "If-Match": "*"}
        other_url = "http://example.org/p/john"
        edit = await client.get(f"/api/Person/{person_id}/edit", headers=headers)
        assert edit.json()["urls"] == [person_url]
        changes = {**edit.json(), "urls": [other_url]}
        updated = await client.put(
            f"/api/Person/{person_id}", json=changes, headers=anyversion
        )
        assert updated.status_code == 200, updated.text
        assert (await client.get(f"/api/Person/{person_id}")).json()["urls"] == [
            other_url
        ]
        assert (await client.get(f"/api/Person/{person_url}")).status_code == 404
        taken = await client.put(
            f"/api/Place/{place.json()['id']}",
            json={
                "type": "Place",
                "id": place.json()["id"],
                "label": "Paris",
                "urls": [other_url],
            },
            headers=anyversion,
        )
        assert taken.status_code == 409, taken.text
        # (put back, for the rest)
        await client.put(
            f"/api/Person/{person_id}",
            json={**changes, "urls": [person_url]},
            headers=anyversion,
        )

        # ... also with the slashes merged, as a proxy may
        merged = await client.get("/api/Person/http:/example.com/people/john-smith")
        assert merged.json()["id"] == person_id

        # ... and a URL with a query string
        with_query = await client.get(f"/api/Place/{place_url}")
        assert with_query.status_code == 200, with_query.text
        assert with_query.json()["id"] == place.json()["id"]

        # The URL refers to the entity in a document too
        statement = await client.post(
            "/api/Statement",
            params={"detail": "true"},
            json={
                "type": "Statement",
                "label": "S",
                "about": {"type": "Person", "id": person_url},
            },
            headers=headers,
        )
        assert statement.status_code == 201, statement.text
        assert statement.json()["about"]["id"] == person_id
        found = await client.get(f"/api/Person/{person_url}")
        assert [s["id"] for s in found.json()["aboutReverse"]] == [
            statement.json()["id"]
        ]

        # Not found: a URL nothing has, or that something of another type has
        for url in ("http://example.com/people/nobody", place_url):
            response = await client.get(f"/api/Person/{url}")
            assert response.status_code == 404, url
        # Not an id or a URL
        for bad in ("john-smith", "ftp://example.com/x"):
            response = await client.get(f"/api/Person/{bad}")
            assert response.status_code == 422, bad

        # Loading to edit, and changes, are only at an id
        url_path = f"/api/Person/{person_url}"
        edit = await client.get(f"/api/Person/{person_id}/edit", headers=headers)
        assert edit.status_code == 200, edit.text
        assert "aboutReverse" not in edit.json()
        for response in (
            await client.get(f"{url_path}/edit", headers=headers),
            await client.put(url_path, json=edit.json(), headers=headers),
            await client.delete(url_path, headers=headers),
            await client.post(f"{url_path}/undelete", headers=headers),
        ):
            assert response.status_code == 400
        assert (await client.get(url_path)).status_code == 200  # (not deleted)
        put = await client.put(
            f"/api/Person/{person_id}",
            json=edit.json(),
            headers={**headers, "If-Match": edit.headers["etag"]},
        )
        assert put.status_code == 200, put.text

        # A document is found by its id only
        assert (await client.get(f"/api/Statement/{person_url}")).status_code == 404

        # Deleting is at the id; the URL finds it only while it is not deleted
        id_path = f"/api/Person/{person_id}"
        assert (await client.delete(id_path, headers=headers)).status_code == 409
        await client.delete(f"/api/Statement/{statement.json()['id']}", headers=headers)
        assert (await client.delete(id_path, headers=headers)).status_code == 204
        assert (await client.get(url_path)).status_code == 404

        # ... and when it is undeleted, it is found again
        assert (
            await client.post(f"{id_path}/undelete", headers=headers)
        ).status_code == 204
        assert (await client.get(url_path)).json()["id"] == person_id


@no_type_check
async def test_an_update_of_a_version_that_is_no_longer_the_latest_is_refused(
    db_driver, clear_database
):
    class Place(Entity):
        pass

    class Statement(Document):
        text: str
        at: Place

    app = create_app()
    async with client_for(app) as client:
        headers = await logged_in(client)
        place = (
            await client.post(
                "/api/Place", json={"type": "Place", "label": "P"}, headers=headers
            )
        ).json()
        created = await client.post(
            "/api/Statement",
            json={
                "type": "Statement",
                "label": "S",
                "text": "one",
                "at": {"type": "Place", "id": place["id"]},
            },
            headers=headers,
        )
        assert created.headers["etag"] == '"1"'
        url = f"/api/Statement/{created.json()['id']}"

        # Two people load the same version to edit
        alice = await client.get(f"{url}/edit", headers=headers)
        bob = await client.get(f"{url}/edit", headers=headers)
        assert alice.headers["etag"] == bob.headers["etag"] == '"1"'

        # Alice saves first
        response = await client.put(
            url,
            json={**alice.json(), "text": "alice"},
            headers={**headers, "If-Match": alice.headers["etag"]},
        )
        assert response.status_code == 200, response.text
        assert response.headers["etag"] == '"2"'

        # Bob's is refused, says what the version is now, and changes nothing
        response = await client.put(
            url,
            json={**bob.json(), "text": "bob"},
            headers={**headers, "If-Match": bob.headers["etag"]},
        )
        assert response.status_code == 412
        assert response.json()["currentVersion"] == 2
        assert response.headers["etag"] == '"2"'
        assert (await client.get(url)).json()["text"] == "alice"

        # He loads again, to see what has changed, and saves from there
        again = await client.get(f"{url}/edit", headers=headers)
        assert again.json()["text"] == "alice"
        response = await client.put(
            url,
            json={**again.json(), "text": "alice and bob"},
            headers={**headers, "If-Match": again.headers["etag"]},
        )
        assert response.status_code == 200
        assert (await client.get(url)).json()["meta"]["version"] == 3

        # Not saying which version is refused; `*` is not
        blind = await client.put(
            url, json={**again.json(), "text": "x"}, headers=headers
        )
        assert blind.status_code == 428
        assert (await client.get(url)).json()["text"] == "alice and bob"
        forced = await client.put(
            url,
            json={**again.json(), "text": "forced"},
            headers={**headers, "If-Match": "*"},
        )
        assert forced.status_code == 200
        assert "etag" not in forced.headers
        assert (await client.get(url)).json()["meta"]["version"] == 4

        # (the same for an entity: the version goes up with an update of it)
        place_edit = await client.get(f"/api/Place/{place['id']}/edit", headers=headers)
        assert place_edit.headers["etag"] == '"1"'
        stale = await client.put(
            f"/api/Place/{place['id']}",
            json=place_edit.json(),
            headers={**headers, "If-Match": '"7"'},
        )
        assert stale.status_code == 412
        assert stale.json()["currentVersion"] == 1
