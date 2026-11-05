"""`/api/derived`, and `_derived` on the view of a person and of a factoid"""

from typing import no_type_check

import httpx2 as httpx
import pytest
from pangloss_api import create_app
from pangloss_models import Document, Entity, initialise

from pangloss_derived import Derived, RuleType, Var, rule
from pangloss_derived.worker import run_pending_derivations

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models():
    class Person(Entity):
        pass

    class Group(Entity):
        pass

    class MemberOf(Document):
        member: Person
        group: Group

    class Factoid(Document):
        statements: list[MemberOf]

    family = RuleType("family", "Ties of family")

    class SameFamily(Derived):
        """Members of the same family"""

        _meta = Derived.Meta(symmetric=True)
        first: Person
        second: Person
        family: Group

    @rule(types=[family])
    def same_family(a: Var[Person], b: Var[Person], f: Var[Group]):
        """Two people said to be members of one family"""
        return SameFamily.Derive(first=a, second=b, family=f).when(
            MemberOf.Where(member=a, group=f),
            MemberOf.Where(member=b, group=f),
        )

    initialise()
    return Person, Group, Factoid


def member(person, group):
    return {
        "type": "MemberOf",
        "label": "m",
        "member": {"type": "Person", "id": person.id},
        "group": {"type": "Group", "id": group.id},
    }


@no_type_check
async def test_the_routes_and_the_derived_section_of_a_view(clear_database):
    Person, Group, Factoid = models()
    a = await Person.Create(label="A").save()
    b = await Person.Create(label="B").save()
    g = await Group.Create(label="G").save()
    f = await Factoid.Create(label="F", statements=[member(a, g), member(b, g)]).save()
    await run_pending_derivations()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        schema = (await client.get("/api/derived")).json()
        assert schema["classes"]["SameFamily"]["ends"] == ["first", "second"]
        assert schema["types"]["family"]["rules"] == ["same_family"]
        assert "SameFamily(a, b, f) :-" in schema["rules"]["same_family"]["datalog"]

        response = await client.get(
            "/api/derived/SameFamily", params={"entity": str(a.id)}
        )
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["count"] == 1
        (fact,) = page["results"]
        assert {fact["first"]["label"], fact["second"]["label"]} == {"A", "B"}
        assert fact["qualifiedOnly"] is False

        # (a filter by a field)
        assert (
            await client.get("/api/derived/SameFamily", params={"family": str(g.id)})
        ).json()["count"] == 1

        why = (await client.get(f"/api/derived/SameFamily/{fact['id']}")).json()
        (justification,) = why["justifications"]
        assert (
            justification["description"]
            == "Two people said to be members of one family"
        )
        assert [e["label"] for e in justification["evidence"]] == ["F"]

        graph = (await client.get("/api/derived/graph/family")).json()
        assert graph["count"] == 1

        person = (await client.get(f"/api/Person/{a.id}")).json()
        assert person["label"] == "A"
        (item,) = person["_derived"]["SameFamily"]["items"]
        assert item["other"]["label"] == "B"
        assert item["otherField"] in ("first", "second")
        assert item["fields"]["family"]["label"] == "G"

        # (a document's view does not show what it is evidence of; `evidence=` gives it)
        factoid = (await client.get(f"/api/Factoid/{f.id}")).json()
        assert "_derived" not in factoid
        by_evidence = (
            await client.get(
                "/api/derived/SameFamily",
                params={"evidence": str(f.id), "page_size": 1},
            )
        ).json()
        assert (
            by_evidence["count"] == 1 and by_evidence["results"][0]["id"] == fact["id"]
        )
        assert (
            await client.get("/api/derived/SameFamily", params={"rule_type": "nothing"})
        ).json()["count"] == 0

        # (a person with nothing derived has no `_derived`)
        c = await Person.Create(label="C").save()
        assert "_derived" not in (await client.get(f"/api/Person/{c.id}")).json()

        assert (await client.get("/api/derived/Nothing")).status_code == 404
        assert (await client.get("/api/derived/graph/nothing")).status_code == 404
        status = (await client.get("/api/derived/status")).json()
        assert status["rules"]["same_family"]["state"] == "ready"


@no_type_check
async def test_the_sdk_reads_what_the_database_reads(clear_database, monkeypatch):
    from pangloss_core import settings as core_settings
    from pangloss_sdk import SdkSettings
    from pangloss_sdk import client as sdk_client

    from pangloss_derived import access, graph

    Person, Group, Factoid = models()
    from pangloss_derived.registry import DerivedRegistry

    SameFamily = DerivedRegistry.classes["SameFamily"]
    a = await Person.Create(label="A").save()
    b = await Person.Create(label="B").save()
    g = await Group.Create(label="G").save()
    await Factoid.Create(label="F", statements=[member(a, g), member(b, g)]).save()
    await run_pending_derivations()

    direct = await SameFamily.list(entity=a)
    (fact,) = direct.results
    detail = await SameFamily.get(fact.id)
    edges = await graph("family")

    app = create_app()
    server_settings = core_settings.SETTINGS
    try:
        settings = SdkSettings(URL="http://test")  # type: ignore[arg-type]
    finally:
        core_settings.SETTINGS = server_settings
    client = sdk_client.AsyncClient(settings, httpx.ASGITransport(app=app))
    sdk_client.install(client)
    monkeypatch.setattr(access, "storage_kind", lambda: "api")
    try:
        through = await SameFamily.list(SameFamily.Where(family=g), entity=a)
        assert through.model_dump() == direct.model_dump()
        assert (await SameFamily.get(fact.id)).model_dump() == detail.model_dump()
        assert await graph("family") == edges
        assert await SameFamily.get("nothing") is None
    finally:
        await client.close()
        sdk_client.install(None)


@no_type_check
async def test_the_blocking_sdk_reads_the_same(clear_database, monkeypatch):
    """The blocking functions ask the same requests and give the same views: the answers of the API, taken through the
    async client, are given back to a blocking client that does not run (the test's database is on this loop)"""
    from pangloss_core import settings as core_settings
    from pangloss_sdk import SdkSettings
    from pangloss_sdk import client as sdk_client

    from pangloss_derived import access, graph
    from pangloss_derived.registry import DerivedRegistry

    Person, Group, Factoid = models()
    SameFamily = DerivedRegistry.classes["SameFamily"]
    a = await Person.Create(label="A").save()
    b = await Person.Create(label="B").save()
    g = await Group.Create(label="G").save()
    f = await Factoid.Create(label="F", statements=[member(a, g), member(b, g)]).save()
    await run_pending_derivations()
    direct = await SameFamily.list(entity=a)
    assert (await SameFamily.list(evidence=f)).model_dump() == direct.model_dump()
    (fact,) = direct.results
    detail = await SameFamily.get(fact.id)
    edges = await graph("family")

    app = create_app()
    server_settings = core_settings.SETTINGS
    try:
        settings = SdkSettings(URL="http://test")  # type: ignore[arg-type]
    finally:
        core_settings.SETTINGS = server_settings
    answers = {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path, params in (
            (
                "/api/derived/SameFamily",
                {"page": 1, "page_size": 25, "entity": str(a.id)},
            ),
            (
                "/api/derived/SameFamily",
                {"page": 1, "page_size": 25, "evidence": str(f.id)},
            ),
            (f"/api/derived/SameFamily/{fact.id}", None),
            ("/api/derived/graph/family", {"plain": "false"}),
        ):
            response = await client.get(path, params=params)
            answers[(path, tuple(sorted((params or {}).items())))] = response

    class Canned(sdk_client.Client):
        def send(self, call):
            return answers[(call.path, tuple(sorted((call.params or {}).items())))]

    sdk_client.install(Canned(settings))
    monkeypatch.setattr(access, "storage_kind", lambda: "api_sync")
    access.bind_reads()
    try:
        assert SameFamily.list(entity=a).model_dump() == direct.model_dump()
        assert SameFamily.list(evidence=f).model_dump() == direct.model_dump()
        assert SameFamily.get(fact.id).model_dump() == detail.model_dump()
        assert graph("family") == edges
    finally:
        sdk_client.install(None)
        monkeypatch.undo()
        access.bind_reads()
