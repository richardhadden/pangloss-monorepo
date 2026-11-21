"""Similar by the graph, end to end, on the backend under test (implementation_docs/similarity-build-plan.md, step 3.4):
with `pangloss_fastrp` installed the default profile is the graph part at 1 and the class part at 0.1; after a rebuild,
`GET /api/Person/{id}/similar` answers people of a person's own family (200 places of 200 when written, on both
backends), and a factoid's similar factoids are led by those of its family (31 or 32 of 32, in six runs). Planted data: 40 people in 4 families, written as documents through `InRole` and
`Identification[WeightedAlternative[Person]]` (membership and kinship within a family, a few mentions across)."""

import importlib
import random
from types import SimpleNamespace
from typing import no_type_check

import httpx2 as httpx
import pytest
from pangloss_api import create_app
from pangloss_vectors.parts import profiles
from pangloss_vectors.rebuild import rebuild

from fastrp_live_support import drop_vector_indexes, make_vector_indexes

pytestmark = pytest.mark.asyncio(loop_scope="session")

FAMILIES = 4
PER_FAMILY = 10


@pytest.fixture
def database(db_driver, clear_database):
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


@no_type_check
def declare() -> SimpleNamespace:
    import pangloss_criteria.models
    import pangloss_library.models
    from pangloss_models import (
        Document,
        Entity,
        ModelRegistry,
        ReifiedRelation,
        initialise,
    )
    from pangloss_vectors import VectorsMeta

    ModelRegistry._reset()
    importlib.reload(pangloss_library.models)
    importlib.reload(pangloss_criteria.models)
    Identification = pangloss_library.models.Identification
    WeightedAlternative = pangloss_library.models.WeightedAlternative

    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=False)

    class Membership(Statement):
        members: list[InRole[Person]]

    class Kinship(Statement):
        person: Identification[WeightedAlternative[Person]]
        relative: InRole[Person]

    class Mention(Statement):
        people: list[Person]

    class Factoid(Document):
        _vectors_meta = VectorsMeta(searchable=True)
        statements: list[Statement]

    initialise()
    return SimpleNamespace(Person=Person, Factoid=Factoid)


def ref(id: str) -> dict:
    return {"type": "Person", "id": id}


def in_role(id: str, role: str) -> dict:
    return {"type": "InRole", "role": role, "target": [ref(id)]}


def one_of(first: str, second: str, percent: int) -> dict:
    return {
        "type": "Identification",
        "target": [
            {
                "type": "WeightedAlternative",
                "alternatives": [
                    {**ref(first), "edge_properties": {"percent": percent}},
                    {**ref(second), "edge_properties": {"percent": 100 - percent}},
                ],
            }
        ],
    }


@no_type_check
async def planted(m) -> tuple[dict[str, int], dict[str, int]]:
    """The people and the factoids written: the family of each, by id"""
    r = random.Random(20261121)
    family_of: dict[str, int] = {}
    families: list[list[str]] = []
    for f in range(FAMILIES):
        members = []
        for n in range(PER_FAMILY):
            person = await m.Person.Create(label=f"person {f}.{n}").save()
            members.append(str(person.id))
            family_of[str(person.id)] = f
        families.append(members)
    factoid_family: dict[str, int] = {}
    for f, members in enumerate(families):
        for n in range(8):
            group = r.sample(members, 4)
            first, second, relative = r.sample(members, 3)
            factoid = await m.Factoid.Create(
                label=f"family {f}, record {n}",
                statements=[
                    {
                        "type": "Membership",
                        "label": f"members of family {f}",
                        "members": [in_role(p, "member") for p in group],
                    },
                    {
                        "type": "Kinship",
                        "label": f"kin in family {f}",
                        "person": one_of(first, second, r.choice([60, 70, 80])),
                        "relative": in_role(relative, "parent"),
                    },
                ],
            ).save()
            factoid_family[str(factoid.id)] = f
    # (a few mentions across the families)
    for n in range(4):
        a, b = r.sample(range(FAMILIES), 2)
        await m.Factoid.Create(
            label=f"a mention {n}",
            statements=[
                {
                    "type": "Mention",
                    "label": f"a mention {n}",
                    "people": [ref(r.choice(families[a])), ref(r.choice(families[b]))],
                }
            ],
        ).save()
    return family_of, factoid_family


@no_type_check
async def test_the_similar_people_of_a_person_are_of_their_family_and_a_factoid_s_lead_with_its_family(
    database,
):
    m = declare()
    assert profiles()["default"] == {"class": 0.1, "graph": 1.0}
    family_of, factoid_family = await planted(m)
    done = await rebuild()
    assert {p.part for p in done.parts} == {"class", "graph"}
    await make_vector_indexes()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        places = same = 0
        for person, family in family_of.items():
            response = await client.get(
                f"/api/Person/{person}/similar", params={"type": "Person", "limit": 5}
            )
            assert response.status_code == 200, response.text
            answer = response.json()
            assert answer["status"] == "ok"
            found = [item["id"] for item in answer["results"]]
            assert len(found) == 5 and person not in found
            places += len(found)
            same += sum(1 for other in found if family_of[other] == family)
        assert places == 200
        assert same >= 180, f"{same} of {places} places are of the person's family"

        led = places = same = 0
        for factoid, family in factoid_family.items():
            response = await client.get(
                f"/api/Factoid/{factoid}/similar",
                params={"type": "Factoid", "limit": 3},
            )
            assert response.status_code == 200, response.text
            found = [item["id"] for item in response.json()["results"]]
            assert len(found) == 3
            led += factoid_family.get(found[0]) == family
            places += len(found)
            same += sum(1 for f in found if factoid_family.get(f) == family)
        # (a factoid's vector is random in part, from the ids: one led by a mention across families was seen once in
        # six runs, and two places of 96)
        assert led >= 0.9 * len(factoid_family), (
            f"{led} of {len(factoid_family)} factoids are led by one of their family"
        )
        assert same >= 0.9 * places, f"{same} of {places} places are of its family"
