# ruff: noqa: RUF059
"""Typologies on a real database: the hierarchy, the entities that have a type, and a type that is also another class"""

import asyncio
from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.entity import Entity
from pangloss_testing.live import run
from pangloss_typology import Typed, Typology, TypologyMeta, service
from pangloss_typology.service import NotFound, Refused

pytestmark = pytest.mark.asyncio(loop_scope="session")


def vocabulary():
    class Post(Entity):
        has_type: list[Typed[RoleTypology]]

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType", languages=["de"])

    initialise()
    return Post, RoleTypology


async def made(Role, label, *types):
    saved = await Role.Create(
        label=label, has_type=[{"type": "RoleType", "id": str(t)} for t in types]
    ).save()
    return saved.id


async def build(RoleTypology):
    """official > secretary > (private secretary), official > chancellor; bard"""
    official = await RoleTypology.create("Official")
    secretary = await RoleTypology.create("Secretary", supertype=official.id)
    private = await RoleTypology.create("Private secretary", supertype=secretary.id)
    chancellor = await RoleTypology.create("Chancellor", supertype=official.id)
    bard = await RoleTypology.create("Bard")
    return official, secretary, private, chancellor, bard


@no_type_check
async def test_a_hierarchy_is_made_and_read(clear_database):
    _, RoleTypology = vocabulary()
    official, secretary, private, chancellor, bard = await build(RoleTypology)
    assert secretary.supertype == official.id
    assert official.supertype is None

    tree = await RoleTypology.tree()
    assert [n["label"] for n in tree] == ["Bard", "Official"]
    assert [c["label"] for c in tree[1]["children"]] == ["Chancellor", "Secretary"]
    assert [c["label"] for c in tree[1]["children"][1]["children"]] == [
        "Private secretary"
    ]
    assert [t.label for t in await RoleTypology.path(private.id)] == [
        "Official",
        "Secretary",
        "Private secretary",
    ]
    assert [t.label for t in await RoleTypology.ancestors(private.id)] == [
        "Secretary",
        "Official",
    ]
    assert {t.label for t in await RoleTypology.descendants(official.id)} == {
        "Secretary",
        "Private secretary",
        "Chancellor",
    }


@no_type_check
async def test_the_edges_are_has_type_and_is_subtype_of(clear_database, db_driver):
    Post, RoleTypology = vocabulary()
    official, secretary, *_ = await build(RoleTypology)
    await made(Post, "Maximilian's secretary", secretary.id)
    # (a node has several labels, which Neo4j does not keep in any order: a label is looked for among them)
    edges = [
        (set(r["a"]), r["edge"], set(r["b"]), r["reverse"])
        for r in run(
            db_driver,
            "MATCH (a)-[r]->(b) RETURN labels(a) AS a, type(r) AS edge, labels(b) AS b, "
            "coalesce(r.reverse, false) AS reverse",
        )
    ]

    def has_edge(a: str, edge: str, b: str, reverse: bool) -> bool:
        return any(
            (a in labels_a, e, b in labels_b, r) == (True, edge, True, reverse)
            for labels_a, e, labels_b, r in edges
        )

    assert has_edge("RoleType", "is_subtype_of", "RoleType", False)
    assert has_edge("RoleType", "is_supertype_of", "RoleType", True)
    assert has_edge("Post", "has_type", "RoleType", False)
    assert has_edge("RoleType", "type_of", "Post", True)


@no_type_check
async def test_a_type_is_viewed_with_its_parents_subtypes_and_entities(clear_database):
    Post, RoleTypology = vocabulary()
    official, secretary, private, chancellor, bard = await build(RoleTypology)
    a = await made(Post, "Maximilian's secretary", secretary.id)
    b = await made(Post, "The Emperor's private secretary", private.id)
    await made(Post, "Chancellor of Austria", chancellor.id)
    await made(Post, "Court bard", bard.id)

    view = await RoleTypology.view(secretary.id)
    assert [p.label for p in view.parents] == ["Official"]
    assert [(s.label, s.subtype_count, s.entity_count) for s in view.subtypes] == [
        ("Private secretary", 0, 1)
    ]
    # (the subtypes' entities are included by default)
    assert view.entities.total == 2
    assert {e.id for e in view.entities.items} == {a, b}
    assert {e.type for e in view.entities.items} == {"Post"}

    exact = await RoleTypology.view(secretary.id, include_subtypes=False)
    assert [e.id for e in exact.entities.items] == [a]
    assert exact.entities.total == 1
    assert exact.subtypes[0].entity_count == 1

    top = await RoleTypology.view(official.id)
    assert top.entities.total == 3
    assert [(s.label, s.entity_count) for s in top.subtypes] == [
        ("Chancellor", 1),
        ("Secretary", 2),
    ]
    assert (await RoleTypology.view(bard.id)).parents == []


@no_type_check
async def test_the_entities_are_paged_by_label_and_can_be_limited_to_a_class(
    clear_database,
):
    Post, RoleTypology = vocabulary()

    class Seal(Entity):
        has_type: list[Typed[RoleTypology]]

    # (a second class that has the type: the models are made again with it)

    initialise()
    t = await RoleTypology.create("Secretary")
    for name in ("c", "a", "e", "b", "d"):
        await made(Post, f"post {name}", t.id)
    await Seal.Create(
        label="seal", has_type=[{"type": "RoleType", "id": str(t.id)}]
    ).save()

    first = await RoleTypology.view(t.id, limit=2)
    assert [e.label for e in first.entities.items] == ["post a", "post b"]
    assert first.entities.total == 6
    assert first.entities.next
    second = await RoleTypology.view(t.id, limit=2, after=first.entities.next)
    assert [e.label for e in second.entities.items] == ["post c", "post d"]
    last = await RoleTypology.view(t.id, limit=2, after=second.entities.next)
    assert [e.label for e in last.entities.items] == ["post e", "seal"]
    assert last.entities.next is None
    seals = await RoleTypology.view(t.id, entity_type="Seal")
    assert [e.label for e in seals.entities.items] == ["seal"]
    assert seals.entities.total == 1


@no_type_check
async def test_a_type_is_moved_and_a_loop_is_refused(clear_database):
    _, RoleTypology = vocabulary()
    official, secretary, private, chancellor, bard = await build(RoleTypology)

    moved = await RoleTypology.move(secretary.id, to=bard.id)
    assert moved.supertype == bard.id
    assert [t.label for t in await RoleTypology.path(private.id)] == [
        "Bard",
        "Secretary",
        "Private secretary",
    ]
    assert {t.label for t in await RoleTypology.descendants(official.id)} == {
        "Chancellor"
    }

    with pytest.raises(Refused, match="below itself"):
        await RoleTypology.move(bard.id, to=private.id)
    with pytest.raises(Refused, match="below itself"):
        await RoleTypology.move(bard.id, to=bard.id)
    with pytest.raises(NotFound):
        await RoleTypology.move(bard.id, to="0198cfd0-0000-7000-8000-000000000000")

    root = await RoleTypology.move(secretary.id, to=None)
    assert root.supertype is None
    # (still two edges for each, none left behind)
    assert [n["label"] for n in await RoleTypology.tree()] == [
        "Bard",
        "Official",
        "Secretary",
    ]


@no_type_check
async def test_each_type_has_one_supertype_after_many_moves(clear_database, db_driver):
    _, RoleTypology = vocabulary()
    official, secretary, private, chancellor, bard = await build(RoleTypology)
    for to in (bard.id, official.id, None, chancellor.id, bard.id):
        await RoleTypology.move(private.id, to=to)
    ups = run(
        db_driver,
        "MATCH (n:RoleType {label: 'Private secretary'})-[r:is_subtype_of]->() RETURN count(r) AS c",
    )[0]["c"]
    downs = run(
        db_driver,
        "MATCH (n:RoleType {label: 'Private secretary'})<-[r:is_supertype_of]-() RETURN count(r) AS c",
    )[0]["c"]
    assert (ups, downs) == (1, 1)


@no_type_check
async def test_labels_in_other_languages(clear_database):
    _, RoleTypology = vocabulary()
    made_type = await RoleTypology.create(
        "Secretary", labels={"de": "Sekretär"}, description="A writer of letters"
    )
    assert made_type.labels == {"de": "Sekretär"}
    assert made_type.description == "A writer of letters"
    with pytest.raises(Refused, match="no label in the language 'fr'"):
        await RoleTypology.create("Other", labels={"fr": "Autre"})


@no_type_check
async def test_merging_gives_the_entities_and_subtypes_to_the_other(clear_database):
    Post, RoleTypology = vocabulary()
    official, secretary, private, chancellor, bard = await build(RoleTypology)
    clerk = await RoleTypology.create("Clerk", supertype=official.id)
    mine = await made(Post, "Clerk of works", clerk.id)
    both = await made(Post, "Both", clerk.id, secretary.id)

    merged = await RoleTypology.merge(clerk.id, into=secretary.id)
    assert merged.id == secretary.id
    view = await RoleTypology.view(secretary.id, include_subtypes=False)
    assert {e.id for e in view.entities.items} == {mine, both}
    with pytest.raises(NotFound):
        await service.get(RoleTypology, clerk.id)


@no_type_check
async def test_merging_into_a_subtype_takes_its_place(clear_database):
    _, RoleTypology = vocabulary()
    official, secretary, private, chancellor, bard = await build(RoleTypology)
    await RoleTypology.merge(secretary.id, into=private.id)
    assert [t.label for t in await RoleTypology.path(private.id)] == [
        "Official",
        "Private secretary",
    ]
    with pytest.raises(Refused, match="into itself"):
        await RoleTypology.merge(bard.id, into=bard.id)


@no_type_check
async def test_a_type_in_use_or_with_subtypes_is_not_deleted(clear_database):
    Post, RoleTypology = vocabulary()
    official, secretary, private, chancellor, bard = await build(RoleTypology)
    await made(Post, "Court bard", bard.id)
    with pytest.raises(Refused, match="subtypes"):
        await RoleTypology.delete(official.id)
    with pytest.raises(Refused, match="in use by Court bard"):
        await RoleTypology.delete(bard.id)
    await RoleTypology.delete(private.id)
    with pytest.raises(NotFound):
        await service.get(RoleTypology, private.id)
    assert (await RoleTypology.view(secretary.id)).subtypes == []


# --- a type that is also another class ------------------------------------------------------------


def roles(concrete="per_type"):
    class Role(Entity):
        has_type: list[Typed[RoleTypology]]
        tenure: str

    class Person(Entity):
        has_role: list[Role]

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(
            name="RoleType",
            also=Role,
            concrete=concrete,
            defaults={"tenure": "unknown"},
        )

    initialise()
    return Role, Person, RoleTypology


@no_type_check
async def test_a_type_that_is_switched_on_is_a_role(clear_database, db_driver):
    Role, Person, RoleTypology = roles()
    secretary = await RoleTypology.create("Secretary")
    assert secretary.is_concrete is False
    node = run(
        db_driver, "MATCH (n:RoleType) RETURN labels(n) AS labels, n.tenure AS tenure"
    )[0]
    assert "Role" not in node["labels"]
    assert node["tenure"] == "unknown"

    # (not yet a role: a person cannot have it as one)
    with pytest.raises(Exception, match="not of an allowed type|allowed"):
        await Person.Create(
            label="Max", has_role=[{"type": "Role", "id": str(secretary.id)}]
        ).save()

    on = await RoleTypology.set_concrete(secretary.id, True)
    assert on.is_concrete is True
    labels = run(db_driver, "MATCH (n:RoleType) RETURN labels(n) AS labels")[0][
        "labels"
    ]
    assert "Role" in labels
    await Person.Create(
        label="Max", has_role=[{"type": "Role", "id": str(secretary.id)}]
    ).save()


@no_type_check
async def test_a_type_used_as_a_role_is_not_switched_off(clear_database):
    Role, Person, RoleTypology = roles()
    secretary = await RoleTypology.create("Secretary")
    await RoleTypology.set_concrete(secretary.id, True)
    await Person.Create(
        label="Max", has_role=[{"type": "Role", "id": str(secretary.id)}]
    ).save()
    with pytest.raises(Refused, match="Max"):
        await RoleTypology.set_concrete(secretary.id, False)


@no_type_check
async def test_an_ordinary_write_does_not_change_the_switch(clear_database, db_driver):
    Role, Person, RoleTypology = roles()
    secretary = await RoleTypology.create("Secretary")
    await RoleTypology.set_concrete(secretary.id, True)
    edit = await RoleTypology.Type.get_for_edit(secretary.id)
    await RoleTypology.Type.Update(
        **{**edit.model_dump(by_alias=False), "description": "changed"}
    ).save(expected_version=edit.meta.version)
    labels = run(db_driver, "MATCH (n:RoleType) RETURN labels(n) AS labels")[0][
        "labels"
    ]
    assert "Role" in labels


@no_type_check
async def test_always_is_a_role_from_the_start_and_has_no_switch(
    clear_database, db_driver
):
    Role, Person, RoleTypology = roles("always")
    secretary = await RoleTypology.create("Secretary")
    labels = run(db_driver, "MATCH (n:RoleType) RETURN labels(n) AS labels")[0][
        "labels"
    ]
    assert "Role" in labels
    await Person.Create(
        label="Max", has_role=[{"type": "Role", "id": str(secretary.id)}]
    ).save()
    with pytest.raises(Refused, match="always"):
        await RoleTypology.set_concrete(secretary.id, False)


# --- loading, dumping, and the routes --------------------------------------------------------------


FILE = [
    {
        "label": "Official",
        "label_de": "Beamter",
        "description": "Holds an office",
        "children": [
            {
                "label": "Secretary",
                "label_de": "Sekretär",
                "children": [{"label": "Private secretary"}],
            },
            {"label": "Chancellor"},
        ],
    },
    {"label": "Bard"},
]


@no_type_check
async def test_a_file_is_loaded_once_and_dumped_as_it_was_read(clear_database):
    _, RoleTypology = vocabulary()
    first = await service.load(RoleTypology, FILE)
    assert (first.created, first.existing) == (5, 0)
    again = await service.load(RoleTypology, FILE)
    assert (again.created, again.existing) == (0, 5)
    assert len(await service.rows_of(RoleTypology)) == 5

    dumped = await service.dump(RoleTypology)
    assert [n["label"] for n in dumped] == ["Bard", "Official"]
    official = dumped[1]
    assert official["label_de"] == "Beamter"
    assert official["description"] == "Holds an office"
    assert [c["label"] for c in official["children"]] == ["Chancellor", "Secretary"]
    # (what is dumped can be loaded: nothing new is made)
    assert (await service.load(RoleTypology, dumped)).created == 0


@no_type_check
async def test_a_file_in_a_language_the_typology_lacks_makes_nothing(clear_database):
    _, RoleTypology = vocabulary()
    with pytest.raises(Refused, match="label_fr"):
        await service.load(
            RoleTypology, [{"label": "A"}, {"label": "B", "label_fr": "B"}]
        )
    assert await service.rows_of(RoleTypology) == {}


@no_type_check
async def test_the_routes(clear_database):
    from types import SimpleNamespace

    import httpx2 as httpx
    from fastapi import FastAPI
    from pangloss_api.dependencies import get_current_user
    from pangloss_typology.api import router

    Post, RoleTypology = vocabulary()
    official, secretary, private, chancellor, bard = await build(RoleTypology)
    a = await made(Post, "Maximilian's secretary", secretary.id)
    await made(Post, "Court bard", bard.id)

    app = FastAPI()
    app.include_router(router)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    tree = (await client.get("/api/typology/RoleType/tree")).json()
    assert [n["label"] for n in tree] == ["Bard", "Official"]

    body = (await client.get(f"/api/typology/RoleType/{secretary.id}")).json()
    assert [p["label"] for p in body["parents"]] == ["Official"]
    assert [s["label"] for s in body["subtypes"]] == ["Private secretary"]
    assert body["entities"]["total"] == 1
    assert body["entities"]["items"][0]["id"] == str(a)
    assert body["entities"]["items"][0]["type"] == "Post"
    assert body["is_concrete"] is False
    assert body["entities"]["next"] is None
    exact = (
        await client.get(f"/api/typology/RoleType/{official.id}?include_subtypes=false")
    ).json()
    assert exact["entities"]["total"] == 0
    assert (
        await client.get(f"/api/typology/RoleType/{official.id}?limit=0")
    ).status_code == 422
    path = (await client.get(f"/api/typology/RoleType/{private.id}/path")).json()
    assert [p["label"] for p in path] == ["Official", "Secretary", "Private secretary"]

    assert (await client.get("/api/typology/NoSuchType/tree")).status_code == 404
    missing = "0198cfd0-0000-7000-8000-000000000000"
    assert (await client.get(f"/api/typology/RoleType/{missing}")).status_code == 404

    move = {"to": str(bard.id)}
    assert (
        await client.post(f"/api/typology/RoleType/{secretary.id}/move", json=move)
    ).status_code in (401, 403)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        username="someone"
    )
    moved = await client.post(f"/api/typology/RoleType/{secretary.id}/move", json=move)
    assert moved.status_code == 200
    assert moved.json()["supertype"] == str(bard.id)
    loop = await client.post(
        f"/api/typology/RoleType/{bard.id}/move", json={"to": str(private.id)}
    )
    assert loop.status_code == 409
    assert "below itself" in loop.json()["detail"]
    assert (
        await client.post(
            f"/api/typology/RoleType/{private.id}/move", json={"to": None}
        )
    ).json()["supertype"] is None
    plain = await client.put(
        f"/api/typology/RoleType/{bard.id}/concrete", json={"on": True}
    )
    assert plain.status_code == 409  # (this typology is not also anything)


@no_type_check
async def test_a_type_is_edited_and_stays_where_it_is(clear_database):
    from types import SimpleNamespace

    import httpx2 as httpx
    from fastapi import FastAPI
    from pangloss_api.dependencies import get_current_user
    from pangloss_typology.api import router

    Post, RoleTypology = vocabulary()
    official, secretary, private, chancellor, bard = await build(RoleTypology)
    await made(Post, "Maximilian's secretary", secretary.id)

    changed = await service.update(
        RoleTypology,
        secretary.id,
        label="Secretary (court)",
        labels={"de": "Sekretär"},
        description="Writes letters",
    )
    assert (changed.label, changed.labels, changed.description) == (
        "Secretary (court)",
        {"de": "Sekretär"},
        "Writes letters",
    )
    assert changed.supertype == official.id
    view = await RoleTypology.view(official.id)
    assert [s.label for s in view.subtypes] == ["Chancellor", "Secretary (court)"]
    assert (await RoleTypology.view(secretary.id)).entities.total == 1
    assert [t.label for t in await RoleTypology.path(private.id)] == [
        "Official",
        "Secretary (court)",
        "Private secretary",
    ]
    with pytest.raises(Refused, match="needs a label"):
        await service.update(RoleTypology, secretary.id, label="  ")
    with pytest.raises(Refused, match="'fr'"):
        await service.update(RoleTypology, secretary.id, labels={"fr": "x"})

    app = FastAPI()
    app.include_router(router)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    url = f"/api/typology/RoleType/{secretary.id}"
    assert (await client.patch(url, json={"label": "X"})).status_code in (401, 403)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        username="someone"
    )
    done = await client.patch(url, json={"labels": {"de": "Schreiber"}})
    assert done.status_code == 200
    assert done.json()["labels"] == {"de": "Schreiber"}
    assert done.json()["label"] == "Secretary (court)"  # (not given: not changed)


@no_type_check
async def test_racing_moves_never_make_a_loop(clear_database, db_driver):
    _, RoleTypology = vocabulary()
    loops = 0
    refusals = 0
    for _ in range(5):
        a = await RoleTypology.create("A")
        b = await RoleTypology.create("B")
        c = await RoleTypology.create("C")
        results = await asyncio.gather(
            RoleTypology.move(a.id, to=b.id),
            RoleTypology.move(b.id, to=c.id),
            RoleTypology.move(c.id, to=a.id),
            return_exceptions=True,
        )
        refusals += sum(isinstance(r, Exception) for r in results)
        loops += run(
            db_driver,
            "MATCH (n:RoleType)-[:is_subtype_of*1..]->(n) RETURN count(DISTINCT n) AS c",
        )[0]["c"]
        run(db_driver, "MATCH (n:RoleType) DETACH DELETE n")
    assert loops == 0
    assert refusals > 0
