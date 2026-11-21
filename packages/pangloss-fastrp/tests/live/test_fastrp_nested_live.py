"""Documents nested in others (a statement in a factoid) have vectors of every part and are found, on the backend
under test (the mending after step 3.5 of implementation_docs/similarity-build-plan.md): the class part gives them
vectors as the graph part does; a search from one finds the statements of other documents, by what their heads let
the reader see; the similar route answers for a nested document's id, and gives a nested document's reference view
as the core's search does; the group of an abstract parent finds its nested subclasses."""

import importlib
from types import SimpleNamespace
from typing import no_type_check

import httpx2 as httpx
import pytest
import pytest_asyncio
from pangloss_api import create_app
from pangloss_cypher.migrations import apply_changes
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT
from pangloss_testing.live import run
from pangloss_testing.similar_models import declare as declare_shapes
from pangloss_testing.under_test.database import current
from pangloss_users import service
from pangloss_vectors import Changed, Item, nearest, store, structure
from pangloss_vectors import class_part as class_part_module
from pangloss_vectors.class_part import PART as CLASS_PART
from pangloss_vectors.rebuild import rebuild
from pangloss_vectors.search import search_query

from fastrp_live_support import (
    drop_vector_indexes,
    existing_indexes,
    make_model_indexes,
    make_vector_indexes,
    plan_of,
    scans_in,
    write_shapes,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


@pytest.fixture
def database(db_driver, clear_database):
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


@pytest_asyncio.fixture(loop_scope="session")
async def client(database):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


@no_type_check
def declare(reviewed: bool = False) -> SimpleNamespace:
    """People, and factoids of statements: `Statement` abstract and a group, `Gift` and `Meeting` below it, nested in
    a `Factoid` (reviewed, with `reviewed`)"""
    import pangloss_criteria.models
    import pangloss_library.models
    from pangloss_models import Document, Entity, ModelRegistry, initialise
    from pangloss_vectors import VectorsMeta

    ModelRegistry._reset()
    importlib.reload(pangloss_library.models)
    importlib.reload(pangloss_criteria.models)
    if reviewed:
        import pangloss_review.models

        importlib.reload(pangloss_review.models)
        from pangloss_review import ReviewMeta

        review_meta = ReviewMeta(reviewable=True)

    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=False)
        _vectors_meta = VectorsMeta(searchable=True)

    class Gift(Statement):
        giver: Person
        receiver: Person

    class Meeting(Statement):
        people: list[Person]

    class Factoid(Document):
        statements: list[Statement]
        if reviewed:
            _review_meta = review_meta

    initialise()
    return SimpleNamespace(Person=Person, Gift=Gift, Meeting=Meeting, Factoid=Factoid)


def ref(id: str) -> dict:
    return {"type": "Person", "id": id}


# (who gives to whom, and who meets, in each factoid: one statement in each)
GIFTS = [("0", "1"), ("0", "2"), ("1", "2"), ("3", "4"), ("3", "5")]
MEETINGS = [("0", "1", "2"), ("3", "4", "5")]


@no_type_check
async def written(m, unpublished: tuple[int, ...] = ()) -> dict[str, dict[str, str]]:
    """Six people and a factoid for each gift and meeting; the gifts `unpublished` (by their place) saved
    unpublished (with `declare(reviewed=True)`). Gives the ids of the people, factoids and statements"""
    people = {
        str(n): str((await m.Person.Create(label=f"P{n}").save()).id) for n in range(6)
    }
    factoids: dict[str, str] = {}
    statements: dict[str, str] = {}

    async def factoid(name: str, statement: dict, published: bool | None) -> None:
        saved = {} if published is None else {"published": published}
        made = await m.Factoid.Create(label=name, statements=[statement]).save(**saved)
        factoids[name] = str(made.id)
        read = await m.Factoid.get(made.id)
        statements[name] = str(read.statements[0].id)

    reviewed = hasattr(m.Factoid, "_review_meta")
    for n, (giver, receiver) in enumerate(GIFTS):
        await factoid(
            f"gift {n}",
            {
                "type": "Gift",
                "label": f"P{giver} gave to P{receiver}",
                "giver": ref(people[giver]),
                "receiver": ref(people[receiver]),
            },
            (n not in unpublished) if reviewed else None,
        )
    for n, met in enumerate(MEETINGS):
        await factoid(
            f"meeting {n}",
            {
                "type": "Meeting",
                "label": f"a meeting of {', '.join(met)}",
                "people": [ref(people[p]) for p in met],
            },
            True if reviewed else None,
        )
    return {"people": people, "factoids": factoids, "statements": statements}


async def built() -> None:
    await rebuild()
    await make_vector_indexes()


def ids_of(db_driver, part: str) -> set[str]:
    return {
        row["of"]
        for row in run(
            db_driver,
            "MATCH (v:PGVector {part: $part}) RETURN v.of AS of",
            part=part,
        )
    }


async def bearer(client) -> dict:
    await service.create_user("root", "root@example.com", PASSWORD, admin=True)
    response = await client.post(
        "/api/users/token", data={"username": "root", "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ---------------------------------------------------------------------------
# The class part
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_class_part_gives_nested_documents_their_vectors_and_none_to_citations_wrappers_or_what_is_deleted(
    database,
):
    m = declare_shapes()
    ids = await write_shapes(m, database)
    await m.Factoid.delete(ids["meeting"])

    await rebuild("class")

    have = ids_of(database, "class")
    for name in ["transfer", "denied", "member transfer", "inference statement"]:
        assert ids[name] in have, name
    stored = {
        row["of"]: row["vector"]
        for row in run(
            database,
            "MATCH (v:PGVector {part: 'class'}) RETURN v.of AS of, v.vector AS vector",
        )
    }
    assert stored[ids["transfer"]] == pytest.approx(CLASS_PART.vector("Transfer"))
    assert stored[ids["fay member"]] == pytest.approx(CLASS_PART.vector("MemberOf"))
    # (a statement of a deleted factoid is deleted with it)
    assert ids["meeting"] not in have and ids["activity"] not in have
    # (a reified relation that is a document, the wrappers and the citations have none)
    assert ids["same"] not in have
    others = run(
        database,
        "MATCH (n:PGIndexableNode) WHERE n:ReifiedRelation OR n:Conjunction OR n:SemanticSpace "
        "OR n:PGCitation OR n:PGUnprotectedCitation RETURN n.id AS id",
    )
    assert others and not ({row["id"] for row in others} & have)
    assert "PGCitedBasis" in class_part_module.left_out()


@no_type_check
async def test_a_rebuild_of_both_parts_gives_the_same_items_vectors_but_for_those_joined_to_nothing(
    database,
):
    from pangloss_fastrp import maths
    from pangloss_fastrp.cypher_reader import load_all
    from pangloss_fastrp.maps import graph_maps

    m = declare_shapes()
    await write_shapes(m, database)
    await rebuild()

    classes, graph = ids_of(database, "class"), ids_of(database, "graph")
    found = maths.joins(await load_all(graph_maps()), graph_maps())
    joined = {i for key in found for i in key}
    assert graph <= classes
    assert graph == classes & joined
    # (what has a class vector and no graph vector: the derived document and the statement in it, out of the graph,
    # and nothing else)
    left = run(
        database,
        "UNWIND $ids AS id MATCH (n:PGIndexableNode {id: id}) RETURN n.type AS type",
        ids=sorted(classes - graph),
    )
    assert sorted(row["type"] for row in left) == ["DerivedFactoid", "Sibling"]


@no_type_check
async def test_a_refresh_of_a_written_head_gives_the_documents_nested_in_it_their_class_vectors(
    database,
):
    m = declare()
    await rebuild()
    made = await written(m)
    head, statement = made["factoids"]["gift 0"], made["statements"]["gift 0"]

    async def write(rows) -> None:
        await store.set_vectors("class", rows)

    refreshed = await CLASS_PART.refresh(
        Changed(written=(Item(head, "Factoid"),)), write
    )

    assert refreshed.written == 2
    assert (await store.read(statement))["class"] == pytest.approx(
        CLASS_PART.vector("Gift")
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_search_from_a_nested_statement_finds_nested_statements_of_other_documents_by_the_group_of_their_parent(
    database,
):
    m = declare()
    made = await written(m)
    await built()
    statements = made["statements"]
    asked = statements["gift 0"]

    found = await nearest(asked, group="Statement", k=4)

    assert found.status == "ok"
    hits = [hit.id for hit in found.hits]
    assert len(hits) == 4 and asked not in hits
    assert set(hits) <= set(statements.values())
    assert {hit.type for hit in found.hits} <= {"Gift", "Meeting"}
    # (the nearest is a statement of P0, P1 or P2, as P0's gift to P1 is, not one of the others: the graph part is
    # random in part, from the ids, so not which of them)
    assert hits[0] in {
        statements["gift 1"],
        statements["gift 2"],
        statements["meeting 0"],
    }
    # (the vector of a nested statement has the label of its parent's group)
    _, labels = await store.read_profile(asked, "default")
    lay = store.layout("default")
    assert lay.group_label("Statement") in labels
    # (and a search with no group finds statements among the heads)
    everything = await nearest(asked, k=20)
    assert {hit.type for hit in everything.hits} >= {"Gift", "Meeting", "Factoid"}


@no_type_check
async def test_an_unpublished_head_hides_its_nested_statements_from_a_reader_who_is_not_logged_in(
    database, graph_sees
):
    graph_sees("logged_in")
    m = declare(reviewed=True)
    made = await written(m, unpublished=(1,))
    await built()
    statements = made["statements"]
    hidden = statements["gift 1"]
    assert hidden in ids_of(database, "graph") and hidden in ids_of(database, "class")

    seen = await nearest(statements["gift 0"], group="Statement", k=10)
    logged_in = await nearest(
        statements["gift 0"], group="Statement", k=10, see_unpublished=True
    )

    assert hidden not in {hit.id for hit in seen.hits}
    assert len(seen.hits) == len(statements) - 2
    assert hidden in {hit.id for hit in logged_in.hits}
    assert len(logged_in.hits) == len(statements) - 1


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_route_answers_for_a_nested_document_and_gives_nested_results_as_the_core_s_search_does(
    client,
):
    m = declare()
    made = await written(m)
    await built()
    statements, factoids = made["statements"], made["factoids"]
    asked = statements["gift 0"]

    response = await client.get(
        f"/api/Gift/{asked}/similar", params={"type": "Statement", "limit": 3}
    )

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["status"] == "ok"
    results = answer["results"]
    assert len(results) == 3
    head_of = {statements[name]: factoids[name] for name in statements}
    for result in results:
        assert result["id"] in head_of
        assert result["type"] in {"Gift", "Meeting"}
        assert result["label"]
        assert result["similarity"] <= 1
        assert result["meta"]["isHeadNode"] is False
        assert result["meta"]["headNodeId"] == head_of[result["id"]]
        assert result["meta"]["headNodeType"] == "Factoid"
        assert result["meta"]["published"] is True
    # (by the class above it, too; not by a class it is not of)
    assert (
        await client.get(f"/api/Statement/{asked}/similar", params={"limit": 3})
    ).status_code == 200
    assert (await client.get(f"/api/Factoid/{asked}/similar")).status_code == 404
    # (a head's results are heads, as before)
    head = await client.get(
        f"/api/Factoid/{factoids['gift 0']}/similar", params={"limit": 20}
    )
    assert head.status_code == 200, head.text
    heads = [r for r in head.json()["results"] if r["type"] == "Factoid"]
    assert heads and all(r["meta"]["isHeadNode"] is True for r in heads)
    assert all(r["meta"]["headNodeId"] is None for r in heads)


@no_type_check
async def test_the_route_for_a_statement_of_an_unpublished_head_is_a_404_to_a_reader_who_is_not_logged_in(
    client, graph_sees
):
    graph_sees("logged_in")
    m = declare(reviewed=True)
    made = await written(m, unpublished=(1,))
    await built()
    hidden = made["statements"]["gift 1"]

    assert (await client.get(f"/api/Gift/{hidden}/similar")).status_code == 404
    seen = await client.get(
        f"/api/Gift/{made['statements']['gift 0']}/similar",
        params={"type": "Statement", "limit": 10},
    )
    assert hidden not in {r["id"] for r in seen.json()["results"]}

    headers = await bearer(client)
    response = await client.get(f"/api/Gift/{hidden}/similar", headers=headers)
    assert response.status_code == 200, response.text
    logged_in = await client.get(
        f"/api/Gift/{made['statements']['gift 0']}/similar",
        params={"type": "Statement", "limit": 10},
        headers=headers,
    )
    found = {r["id"]: r for r in logged_in.json()["results"]}
    assert hidden in found
    assert found[hidden]["meta"]["published"] is False


# ---------------------------------------------------------------------------
# The plans
# ---------------------------------------------------------------------------


async def make_vectors_indexes(db_driver) -> None:
    """The plain indexes of `pangloss-vectors` (its migration `0001`), those there already left"""
    there = existing_indexes(db_driver)
    wanted = [
        entry
        for entry in structure.INDEXES
        if (entry["label"], tuple(entry["properties"])) not in there
    ]
    if wanted:
        await apply_changes(
            current(), EMPTY_SNAPSHOT, [c.AddIndex(index=entry) for entry in wanted]
        )


@no_type_check
async def test_the_class_part_s_queries_and_the_search_read_from_indexes(database):
    from pangloss_core import backend

    m = declare()
    made = await written(m)
    await make_model_indexes(database)
    await make_vectors_indexes(database)
    await built()
    fragments = backend.current().fragments
    lay = store.layout("default")
    given = {"kinds": ["Document", "Entity"], "left_out": ["PGCitation"]}
    queries = {
        "class page": (
            class_part_module._page_query(fragments),
            {"after": "", "limit": 10, **given},
        ),
        "class items": (
            class_part_module._items_query(fragments),
            {"ids": ["a", "b"], **given},
        ),
        "class below": (class_part_module.BELOW_QUERY, {"ids": ["a", "b"], **given}),
        "search": (
            search_query(lay.group_index_name("Statement")),
            {
                "profile": "default",
                "fetch": 10,
                "vector": [0.0] * lay.dimension,
                "of": made["statements"]["gift 0"],
                "k": 5,
                "see_unpublished": False,
            },
        ),
    }
    for name, (query, parameters) in queries.items():
        plan = plan_of(database, query, **parameters)
        print(f"\n== {name}\n" + "\n".join(plan))
        assert scans_in(plan) == [], (name, plan)
