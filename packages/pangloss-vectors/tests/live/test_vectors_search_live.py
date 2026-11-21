"""Search on the backend under test (implementation_docs/similarity-build-plan.md, step 2.4): the nearest by a
profile's weights, through its vector index, in the generation in use, cut to what the reader may see; asked again
while short."""

import importlib
import math
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_models import Document, Entity, ModelRegistry, initialise
from pangloss_testing.backends import under_test
from pangloss_vectors import (
    Nearest,
    NotAGroup,
    VectorRow,
    VectorsMeta,
    nearest,
    search,
    store,
)
from pangloss_vectors.class_part import PART
from vectors_live_support import (
    build,
    drop_vector_indexes,
    make_vector_indexes,
    write_and_combine,
)
from vectors_support import SizedPart

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def parts(parts_of_the_test):
    """Two parts, `a` (3 numbers, weight 1) and `b` (2, weight 0.25): the default profile is of dimension 5"""
    made = SimpleNamespace(
        a=SizedPart("a", 3, weight=1), b=SizedPart("b", 2, weight=0.25)
    )
    parts_of_the_test(made.a)
    parts_of_the_test(made.b)
    return made


@pytest.fixture
def vectors(db_driver, clear_database, parts):
    drop_vector_indexes(db_driver)
    yield parts
    drop_vector_indexes(db_driver)


@pytest.fixture
def asked(monkeypatch) -> list[int]:
    """The `fetch` of each query of the index a search makes"""
    fetched: list[int] = []
    ask = search._ask

    async def counted(tx, query, **parameters):
        fetched.append(parameters["fetch"])
        return await ask(tx, query, **parameters)

    monkeypatch.setattr(search, "_ask", counted)
    return fetched


@no_type_check
def declare(reviewed: bool = False) -> SimpleNamespace:
    ModelRegistry._reset()
    review_meta = {}
    if reviewed:
        review = pytest.importorskip("pangloss_review")
        import pangloss_review.models

        importlib.reload(pangloss_review.models)
        review_meta = {"_review_meta": review.ReviewMeta(reviewable=True)}

    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Saint(Person):
        pass

    Statement = type("Statement", (Document,), {"__module__": __name__, **review_meta})

    initialise()
    return SimpleNamespace(Person=Person, Saint=Saint, Statement=Statement)


def cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def score(a: tuple, b: tuple, weights=(1.0, 0.25)) -> float:
    """The weighted mean of the parts' cosines: what a hit's score is"""
    return (weights[0] * cosine(a[0], b[0]) + weights[1] * cosine(a[1], b[1])) / sum(
        weights
    )


async def saved(model, label: str):
    return await model.Create(label=label).save()


async def written(items: dict[str, tuple]) -> None:
    """Both parts built from vectors by item id, and the indexes made"""
    await build("a", [VectorRow(of, t, v[0]) for of, (t, *v) in items.items()])
    await build("b", [VectorRow(of, t, v[1]) for of, (t, *v) in items.items() if v[1]])


def ids(found: Nearest) -> list[str]:
    assert found.status == "ok", found
    return [hit.id for hit in found.hits]


async def people(m, vectors_by_label: dict[str, tuple]) -> dict[str, str]:
    """People saved and their vectors of both parts built: their ids by label"""
    made = {label: str((await saved(m.Person, label)).id) for label in vectors_by_label}
    await written(
        {made[label]: ("Person", *v) for label, v in vectors_by_label.items()}
    )
    return made


# ---------------------------------------------------------------------------
# The nearest
# ---------------------------------------------------------------------------


NEAR = {
    "q": ([1, 0, 0], [1, 0]),
    "near": ([1, 0.1, 0], [1, 0]),
    "middle": ([1, 1, 0], [0, 1]),
    "far": ([0, 1, 1], [1, 1]),
    "opposite": ([-1, 0, 0], [-1, 0]),
}


async def test_the_nearest_come_back_in_order_with_the_weighted_mean_of_the_parts_cosines_and_never_the_item_itself(
    vectors,
):
    m = declare()
    made = await people(m, NEAR)
    await make_vector_indexes()

    found = await nearest(made["q"], k=10)
    assert ids(found) == [made[n] for n in ("near", "middle", "far", "opposite")]
    for hit, name in zip(
        found.hits, ("near", "middle", "far", "opposite"), strict=True
    ):
        assert hit.score == pytest.approx(score(NEAR["q"], NEAR[name]), abs=1e-5)
        assert hit.type == "Person"
    assert found.hits[-1].score == pytest.approx(-1, abs=1e-5)

    # (k cuts)
    assert ids(await nearest(made["q"], k=2)) == [made["near"], made["middle"]]

    # (from a vector, by part: the item is not left out then)
    found = await nearest(vector={"a": [1, 0, 0], "b": [1, 0]}, k=2)
    assert ids(found) == [made["q"], made["near"]]
    assert found.hits[0].score == pytest.approx(1, abs=1e-5)


async def test_a_database_of_five_items_asks_the_index_once(vectors, asked):
    m = declare()
    made = await people(m, NEAR)
    await make_vector_indexes()
    found = await nearest(made["q"], k=10)
    assert len(found.hits) == 4
    # (k × VECTORS_OVERFETCH, and one for the item itself)
    assert asked == [41]


async def test_another_profile_weighs_the_parts_its_own_way(
    vectors, settings, monkeypatch
):
    monkeypatch.setattr(settings, "VECTORS_PROFILES", {"only_b": {"b": 1}})
    m = declare()
    made = await people(m, NEAR)
    await make_vector_indexes()
    found = await nearest(made["q"], profile="only_b", k=2)
    # (by `b` alone, `near` and `q` are the same)
    assert found.hits[0].id == made["near"]
    assert found.hits[0].score == pytest.approx(1, abs=1e-5)
    with pytest.raises(KeyError, match="no profile named 'nothing'"):
        await nearest(made["q"], profile="nothing")


# ---------------------------------------------------------------------------
# What the reader may see
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_deleted_item_is_not_found(vectors):
    m = declare()
    q = await saved(m.Statement, "q")
    gone = await saved(m.Statement, "gone")
    kept = await saved(m.Statement, "kept")
    await written(
        {
            str(q.id): ("Statement", [1, 0, 0], [1, 0]),
            str(gone.id): ("Statement", [1, 0, 0], [1, 0]),
            str(kept.id): ("Statement", [0, 1, 0], [1, 0]),
        }
    )
    await make_vector_indexes()
    assert ids(await nearest(str(q.id))) == [str(gone.id), str(kept.id)]
    # (its vectors are still there: the search leaves it out)
    await m.Statement.delete(gone.id)
    assert ids(await nearest(str(q.id))) == [str(kept.id)]


@no_type_check
async def test_an_unpublished_document_is_found_only_by_a_reader_who_may_see_it(
    vectors,
):
    m = declare(reviewed=True)
    q = await saved(m.Statement, "q")
    waiting = await saved(m.Statement, "waiting")
    await written(
        {
            str(q.id): ("Statement", [1, 0, 0], [1, 0]),
            str(waiting.id): ("Statement", [1, 0, 0], [1, 0]),
        }
    )
    await make_vector_indexes()
    assert ids(await nearest(str(q.id))) == []
    assert ids(await nearest(str(q.id), see_unpublished=True)) == [str(waiting.id)]


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_group_narrows_the_search_and_a_class_that_is_not_a_group_is_refused(
    vectors,
):
    m = declare()
    q = await saved(m.Person, "q")
    saint = await saved(m.Saint, "saint")
    statement = await saved(m.Statement, "statement")
    await written(
        {
            str(q.id): ("Person", [1, 0, 0], [1, 0]),
            str(statement.id): ("Statement", [1, 0, 0], [1, 0]),
            str(saint.id): ("Saint", [1, 1, 0], [1, 0]),
        }
    )
    await make_vector_indexes()
    assert ids(await nearest(str(q.id))) == [str(statement.id), str(saint.id)]
    found = await nearest(str(q.id), group="Person")
    # (a saint is a person: the group's index has it)
    assert ids(found) == [str(saint.id)]
    assert found.hits[0].type == "Saint"

    with pytest.raises(NotAGroup, match="'Statement' is not a group.*Person"):
        await nearest(str(q.id), group="Statement")
    # (a subclass of a group is in its parent's group, and is not one of its own)
    with pytest.raises(NotAGroup, match="'Saint'"):
        await nearest(str(q.id), group="Saint")


# ---------------------------------------------------------------------------
# Asked again while short
# ---------------------------------------------------------------------------


async def test_vectors_just_deleted_among_the_nearest_do_not_make_the_search_short(
    vectors, asked
):
    """(on Memgraph a node deleted keeps its place among the nearest until the database collects it, and is dropped
    after: the search asks again. On Neo4j it is not given at all, and the search asks once)"""
    m = declare()
    rows = {"q": ([1, 0, 0], [1, 0])}
    # (60 near the query, each a little further off; 10 far)
    for i in range(60):
        rows[f"n{i:02}"] = ([1, 0.01 * (i + 1), 0], [1, 0])
    for i in range(10):
        rows[f"f{i}"] = ([0, 1, 0.1 * (i + 1)], [0, 1])
    made = await people(m, rows)
    await make_vector_indexes()

    # (the 50 nearest have their vectors deleted, as a delete of the items will do it)
    await store.delete_for([made[f"n{i:02}"] for i in range(50)])
    found = await nearest(made["q"], k=5)
    assert ids(found) == [made[f"n{i:02}"] for i in range(50, 55)]
    if under_test().name == "memgraph":
        # (k × 4 and one, then four times as many)
        assert asked == [21, 84]
    else:
        assert asked == [21]


async def test_a_search_never_asks_for_more_than_twice_the_profile_s_vectors(
    vectors, asked
):
    m = declare()
    made = await people(m, NEAR)
    await make_vector_indexes()
    # (of the four others, all are gone: it cannot find k, and stops)
    await store.delete_for([made[n] for n in ("near", "middle", "far", "opposite")])
    found = await nearest(made["q"], k=1)
    assert found.hits == []
    # (5 vectors: never more than 11)
    assert asked == [5, 11]


async def test_during_a_rebuild_the_search_gives_only_the_generation_in_use_and_still_k_hits(
    vectors, asked
):
    m = declare()
    rows = {f"p{i:02}": ([1, 0.05 * i, 0], [1, 0]) for i in range(30)}
    made = await people(m, rows)
    await make_vector_indexes()
    expected = ids(await nearest(made["p00"], k=5))
    assert len(expected) == 5

    # (a new generation of `a` written and combined, not switched: every item the same as the query there, so
    # that the new generation's are all nearer than any of the old one's)
    await write_and_combine(
        "a", [VectorRow(of, "Person", [1, 0, 0]) for of in made.values()]
    )
    asked.clear()
    found = await nearest(made["p00"], k=5)
    assert ids(found) == expected
    assert len(asked) > 1


# ---------------------------------------------------------------------------
# Merged, pending, rebuild due
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_survivor_of_a_merge_answers_for_the_id_absorbed(vectors):
    m = declare()
    kept = await saved(m.Person, "kept")
    absorbed = await saved(m.Person, "absorbed")
    like_kept = await saved(m.Person, "like kept")
    like_absorbed = await saved(m.Person, "like absorbed")
    await written(
        {
            str(kept.id): ("Person", [1, 0, 0], [1, 0]),
            str(absorbed.id): ("Person", [0, 1, 0], [0, 1]),
            str(like_kept.id): ("Person", [1, 0.1, 0], [1, 0]),
            str(like_absorbed.id): ("Person", [0, 1, 0.1], [0, 1]),
        }
    )
    await make_vector_indexes()
    await m.Person.merge(absorbed.id, into=kept.id)

    found = await nearest(str(absorbed.id), k=3)
    # (by the survivor's vectors; neither the survivor nor the entity merged into it is a hit)
    assert ids(found) == [str(like_kept.id), str(like_absorbed.id)]
    assert ids(await nearest(str(kept.id), k=3)) == ids(found)


@no_type_check
async def test_an_item_with_no_vector_and_a_profile_not_built_answer_pending(vectors):
    m = declare()
    q = await saved(m.Person, "q")
    assert await nearest(str(q.id)) == Nearest("pending")
    other = await saved(m.Person, "other")
    await written({str(other.id): ("Person", [1, 0, 0], [1, 0])})
    await make_vector_indexes()
    assert await nearest(str(q.id)) == Nearest("pending")
    assert await nearest("no-such-item") == Nearest("pending")


@no_type_check
async def test_a_profile_whose_dimension_changed_answers_rebuild_due(vectors):
    m = declare()
    q = await saved(m.Person, "q")
    await written({str(q.id): ("Person", [1, 0, 0], [1, 0])})
    await make_vector_indexes()
    vectors.a.size = 4
    assert await nearest(str(q.id)) == Nearest("rebuild_due")
    assert await nearest(vector={"a": [1, 0, 0, 0]}) == Nearest("rebuild_due")


async def test_what_is_asked_for_is_checked(vectors):
    declare()
    with pytest.raises(ValueError, match="not both"):
        await nearest()
    with pytest.raises(ValueError, match="not both"):
        await nearest("x", vector={"a": [1, 0, 0]})
    with pytest.raises(ValueError, match="1 or more"):
        await nearest("x", k=0)


# ---------------------------------------------------------------------------
# With the class part
# ---------------------------------------------------------------------------


@no_type_check
async def test_with_the_class_part_alone_the_nearest_are_of_the_nearest_classes(
    db_driver, clear_database, parts_of_the_test
):
    parts_of_the_test(PART)
    drop_vector_indexes(db_driver)
    try:
        ModelRegistry._reset()

        class Statement(Document):
            pass

        class CreationOfPhysicalObject(Statement):
            pass

        class CreationOfArtwork(CreationOfPhysicalObject):
            pass

        class CreationOfPainting(CreationOfArtwork):
            pass

        class Birth(Statement):
            pass

        initialise()
        painting = await saved(CreationOfPainting, "painting")
        artwork = await saved(CreationOfArtwork, "artwork")
        birth = await saved(Birth, "birth")
        physical = await saved(CreationOfPhysicalObject, "physical")
        await build("class")
        await make_vector_indexes()

        found = await nearest(str(painting.id))
        assert ids(found) == [str(artwork.id), str(physical.id), str(birth.id)]
        assert found.hits[0].score == pytest.approx(
            cosine(PART.vector("CreationOfPainting"), PART.vector("CreationOfArtwork")),
            abs=1e-5,
        )
    finally:
        drop_vector_indexes(db_driver)
