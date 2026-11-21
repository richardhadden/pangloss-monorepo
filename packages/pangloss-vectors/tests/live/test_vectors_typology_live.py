"""A type of a typology is given as the real class only where the data uses it as one (step 7a.5 of
implementation_docs/similarity-build-plan.md), on the backend under test: `RoleType` is below `Role` and leaves the
label `Role` to its switch (`__labels_unmanaged__`), and a search narrowed to `Role` gives a type only where a relation
that takes a role points at it, from something the reader may look through. Read when the search is: nothing stored
changes, so a write is followed at once, with no turn of the worker and no rebuild."""

import importlib
from types import SimpleNamespace
from typing import no_type_check

import httpx2 as httpx
import pytest
import pytest_asyncio
from pangloss_models import Document, Entity, ModelRegistry, ReifiedRelation, initialise
from pangloss_vectors import Nearest, VectorRow, VectorsMeta, nearest, search
from pangloss_vectors.fields import field_types
from vectors_live_support import build, drop_vector_indexes, make_vector_indexes
from vectors_support import SizedPart

pytestmark = pytest.mark.asyncio(loop_scope="session")

typology = pytest.importorskip("pangloss_typology")


@pytest.fixture
def vectors(db_driver, clear_database, parts_of_the_test):
    """One part, `a`, of 3 numbers: the default profile is it"""
    parts_of_the_test(SizedPart("a", 3))
    typology.Typology.registry.clear()
    drop_vector_indexes(db_driver)
    yield
    drop_vector_indexes(db_driver)
    typology.Typology.registry.clear()


@no_type_check
def declare(searchable: bool) -> SimpleNamespace:
    """`Role`, a group if `searchable`, and its typology (`RoleType`, also a `Role`, switched on per type); people, who
    hold none; appointments, which name roles directly and through a wrapper; drafts (reviewed: saved unpublished),
    which name roles"""
    review = pytest.importorskip("pangloss_review")
    import pangloss_review.models

    Typed, Typology, TypologyMeta = (
        typology.Typed,
        typology.Typology,
        typology.TypologyMeta,
    )
    ModelRegistry._reset()
    importlib.reload(pangloss_review.models)

    class Role(Entity):
        _vectors_meta = VectorsMeta(searchable=searchable)

        has_type: list[Typed[RoleTypology]]

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType", also=Role)

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        pass

    class Office(Entity):
        """An entity that names roles through a wrapper"""

        filled_in: list[InRole[Role]]

    class Appointment(Document):
        held: list[Role]
        held_in: list[InRole[Role]]

    class Draft(Document):
        _review_meta = review.ReviewMeta(reviewable=True)

        held: list[Role]

    initialise()
    return SimpleNamespace(
        Role=Role,
        RoleTypology=RoleTypology,
        RoleType=RoleTypology.Type,
        Person=Person,
        Office=Office,
        Appointment=Appointment,
        Draft=Draft,
    )


def ref(id: str) -> dict:
    return {"type": "Role", "id": id}


@no_type_check
async def planted(m) -> dict[str, str]:
    """The role searched from (`q`), a real role (`Teller`, whose type is `Clerk`), two types switched on (`Banker`,
    `Clerk`), a person, all near `q`; `Banker` named as a role by an appointment. Their vectors built
    and the indexes made: ids by label"""
    made: dict[str, str] = {}
    for label in ("Banker", "Clerk"):
        made[label] = str((await m.RoleTypology.create(label)).id)
        await m.RoleTypology.set_concrete(made[label], True)
    made["q"] = str((await m.Role.Create(label="q", has_type=[]).save()).id)
    made["Teller"] = str(
        (
            await m.Role.Create(
                label="Teller", has_type=[{"type": "RoleType", "id": made["Clerk"]}]
            ).save()
        ).id
    )
    made["Ann"] = str((await m.Person.Create(label="Ann").save()).id)
    made["appointment"] = str(
        (
            await m.Appointment.Create(
                label="Ann as banker", held=[ref(made["Banker"])], held_in=[]
            ).save()
        ).id
    )
    rows = {
        "q": ("Role", [1, 0, 0]),
        "Teller": ("Role", [1, 0.1, 0]),
        "Banker": ("RoleType", [1, 0.2, 0]),
        "Clerk": ("RoleType", [1, 0.3, 0]),
        "Ann": ("Person", [1, 0.4, 0]),
    }
    await build("a", [VectorRow(made[label], t, v) for label, (t, v) in rows.items()])
    await make_vector_indexes()
    return made


def labels(found: Nearest, made: dict[str, str]) -> list[str]:
    assert found.status == "ok", found
    by_id = {v: k for k, v in made.items()}
    return [by_id.get(hit.id, hit.id) for hit in found.hits]


@pytest.fixture(params=[True, False], ids=["group", "scan"])
def searchable(request) -> bool:
    """`Role` a group (its index) or not (the exact scan): the same answers"""
    return request.param


@no_type_check
async def test_a_type_is_a_role_only_where_something_names_it_as_one(
    vectors, searchable
):
    m = declare(searchable)
    made = await planted(m)
    roles = await nearest(made["q"], types=["Role", "RoleType"], asked=["Role"])
    # (Clerk is only had as a type, by Teller: no use of it as a role)
    assert labels(roles, made) == ["Teller", "Banker"]
    # (asked as a type, and both: every type)
    types = await nearest(made["q"], types=["RoleType"], asked=["RoleType"])
    assert labels(types, made) == ["Banker", "Clerk"]
    both = await nearest(
        made["q"], types=["Role", "RoleType"], asked=["Role", "RoleType"]
    )
    assert labels(both, made) == ["Teller", "Banker", "Clerk"]
    # (the classes alone do not say which of the two was meant: refused, not guessed)
    with pytest.raises(ValueError, match="asked"):
        await nearest(made["q"], types=["Role", "RoleType"])
    # (not narrowed: all of them)
    assert labels(await nearest(made["q"]), made) == [
        "Teller",
        "Banker",
        "Clerk",
        "Ann",
    ]
    if searchable:
        group = await nearest(made["q"], group="Role")
        assert labels(group, made) == ["Teller", "Banker"]


@no_type_check
async def test_a_field_that_holds_roles_is_as_type_role(vectors, searchable):
    m = declare(searchable)
    made = await planted(m)
    for field in ("Appointment.held", "Appointment.held_in"):
        found = await nearest(made["q"], types=field_types(field), asked=[field])
        assert labels(found, made) == ["Teller", "Banker"], field


@no_type_check
async def test_a_use_written_counts_at_once_and_is_gone_when_its_document_is_deleted(
    vectors, searchable
):
    m = declare(searchable)
    made = await planted(m)

    async def roles() -> list[str]:
        return labels(
            await nearest(made["q"], types=["Role", "RoleType"], asked=["Role"]), made
        )

    # (directly)
    second = await m.Appointment.Create(
        label="Ann as clerk", held=[ref(made["Clerk"])], held_in=[]
    ).save()
    assert await roles() == ["Teller", "Banker", "Clerk"]
    await m.Appointment.delete(second.id)
    assert await roles() == ["Teller", "Banker"]

    # (through a wrapper: the edge onto the type is the wrapper's `target`)
    third = await m.Appointment.Create(
        label="Ann in the role of clerk",
        held=[],
        held_in=[{"type": "InRole", "target": [ref(made["Clerk"])]}],
    ).save()
    assert await roles() == ["Teller", "Banker", "Clerk"]
    await m.Appointment.delete(third.id)
    assert await roles() == ["Teller", "Banker"]


@no_type_check
async def test_what_an_entity_merged_into_another_names_through_a_wrapper_does_not_count(
    vectors, searchable
):
    """The absorbed entity keeps its own fields and edges; the wrapper below it has no `merged_into` of its own, and
    is judged by the entity it is of (found by the second reading of step 7a.5)"""
    m = declare(searchable)
    made = await planted(m)

    async def roles() -> list[str]:
        return labels(
            await nearest(made["q"], types=["Role", "RoleType"], asked=["Role"]), made
        )

    absorbed = await m.Office.Create(
        label="The old counting house",
        filled_in=[{"type": "InRole", "target": [ref(made["Clerk"])]}],
    ).save()
    kept = await m.Office.Create(label="The counting house", filled_in=[]).save()
    assert await roles() == ["Teller", "Banker", "Clerk"]
    # (the survivor is given none of it: the absorbed office alone goes on naming the clerk)
    await m.Office.merge(
        absorbed.id,
        into=kept.id,
        values={"label": "The counting house", "filled_in": []},
    )
    assert await roles() == ["Teller", "Banker"]


@no_type_check
async def test_an_unpublished_use_counts_for_a_reader_who_may_see_it_only(
    vectors, searchable
):
    m = declare(searchable)
    made = await planted(m)
    await m.Draft.Create(
        label="Ann as clerk, not yet published", held=[ref(made["Clerk"])]
    ).save()
    asked = {"types": ["Role", "RoleType"], "asked": ["Role"]}
    anyone = await nearest(made["q"], **asked)
    assert labels(anyone, made) == ["Teller", "Banker"]
    logged_in = await nearest(made["q"], see_unpublished=True, **asked)
    assert labels(logged_in, made) == ["Teller", "Banker", "Clerk"]


@no_type_check
async def test_without_a_type_given_only_by_use_the_query_is_as_it_was(
    vectors, monkeypatch
):
    m = declare(True)
    made = await planted(m)
    queries: list[str] = []
    ask = search._ask

    async def kept(tx, query, **parameters):
        queries.append(query)
        return await ask(tx, query, **parameters)

    monkeypatch.setattr(search, "_ask", kept)
    await nearest(made["q"], types=["RoleType"], asked=["RoleType"])
    await nearest(made["q"], types=["Person"])
    await nearest(made["q"])
    assert queries and not [q for q in queries if "by_use" in q]
    await nearest(made["q"], group="Role")
    assert "$by_use_types" in queries[-1]


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="session")
async def client(vectors):
    from pangloss_api import create_app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


@no_type_check
async def test_the_route_gives_a_type_as_a_role_only_where_it_is_used_as_one(client):
    m = declare(True)
    made = await planted(m)

    async def similar(query: str) -> list[str]:
        response = await client.get(f"/api/Role/{made['q']}/similar?{query}")
        assert response.status_code == 200, response.text
        return [item["label"] for item in response.json()["results"]]

    assert await similar("type=Role") == ["Teller", "Banker"]
    assert await similar("type=RoleType") == ["Banker", "Clerk"]
    assert await similar("type=Role&type=RoleType") == ["Teller", "Banker", "Clerk"]
    assert await similar("field=Appointment.held") == ["Teller", "Banker"]
    assert await similar("field=Appointment.held&type=RoleType") == [
        "Teller",
        "Banker",
        "Clerk",
    ]
    assert await similar("") == ["Teller", "Banker", "Clerk", "Ann"]
