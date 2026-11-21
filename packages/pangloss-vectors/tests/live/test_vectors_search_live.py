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


# ---------------------------------------------------------------------------
# Narrowed to classes (step 7a.4): through a group's index and by the exact scan, merged by score
# ---------------------------------------------------------------------------


@no_type_check
def declare_agents(reviewed: bool = False) -> SimpleNamespace:
    """`Person` (a group) above `Saint`; `Group` (a group); `Place` above `Building` (in no group); a `Report`, a
    document in no group (with `reviewed`, saved unpublished)"""
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

    class Group(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Place(Entity):
        pass

    class Building(Place):
        pass

    Report = type("Report", (Document,), {"__module__": __name__, **review_meta})

    initialise()
    return SimpleNamespace(
        Person=Person,
        Saint=Saint,
        Group=Group,
        Place=Place,
        Building=Building,
        Report=Report,
    )


# (the item searched from, a person, and items of each class at known places about it)
PLANTED = {
    "q": ("Person", [1, 0, 0], [1, 0]),
    "person 1": ("Person", [1, 0.3, 0], [1, 0.2]),
    "person 2": ("Person", [0.2, 1, 0], [0, 1]),
    "saint 1": ("Saint", [1, 0.1, 0.1], [0.5, 0.5]),
    "group 1": ("Group", [1, 0.05, 0], [1, 0]),
    "group 2": ("Group", [0.5, 0.5, 0.5], [1, 0.1]),
    "group 3": ("Group", [-1, 0.2, 0], [-1, 0]),
    "place 1": ("Place", [1, 0.2, 0.1], [1, 0.1]),
    "place 2": ("Place", [0, 0.3, 1], [0.3, 1]),
    "building 1": ("Building", [1, 0, 0.4], [1, 0]),
    "report 1": ("Report", [1, 0.15, 0], [1, 0.3]),
    "report 2": ("Report", [0.1, 1, 0.2], [0, 1]),
}


async def planted(m, rows: dict[str, tuple] = PLANTED) -> dict[str, str]:
    """The items of `rows` saved and both parts built from their vectors, and the indexes made: ids by label"""
    made = {}
    for label, (class_name, *_vectors) in rows.items():
        made[label] = str((await saved(getattr(m, class_name), label)).id)
    await written(
        {made[label]: (class_name, *v) for label, (class_name, *v) in rows.items()}
    )
    await make_vector_indexes()
    return made


async def cut_by_hand(of: str, classes: set[str], k: int, **asked) -> list:
    """The whole search with a large `k`, cut to the classes: what a search narrowed to them must give"""
    whole = await nearest(of, k=100, **asked)
    assert whole.status == "ok"
    return [hit for hit in whole.hits if hit.type in classes][:k]


def same_hits(found: Nearest, expected: list) -> None:
    assert found.status == "ok", found
    assert [hit.id for hit in found.hits] == [hit.id for hit in expected]
    for hit, wanted in zip(found.hits, expected, strict=True):
        assert hit.type == wanted.type
        assert hit.score == pytest.approx(wanted.score, abs=1e-6)


@pytest.mark.parametrize("k", [3, 10])
async def test_two_groups_give_both_in_the_order_of_their_scores_as_the_whole_search_cut_to_them(
    vectors, asked, k
):
    m = declare_agents()
    made = await planted(m)
    expected = await cut_by_hand(made["q"], {"Person", "Saint", "Group"}, k)
    asked.clear()

    found = await nearest(made["q"], types=["Group", "Person", "Saint"], k=k)

    same_hits(found, expected)
    assert {hit.type for hit in found.hits} >= {"Person", "Group"}
    # (each group's index, once each: nothing scanned)
    assert len(asked) == 2


async def test_a_group_and_a_class_in_no_group_are_an_index_and_a_scan_merged_by_score(
    vectors, asked
):
    m = declare_agents()
    made = await planted(m)
    classes = {"Group", "Place", "Building"}
    expected = await cut_by_hand(made["q"], classes, 5)
    asked.clear()

    found = await nearest(made["q"], types=sorted(classes), k=5)

    same_hits(found, expected)
    assert {hit.type for hit in found.hits} == classes
    # (the group's index, short of five, asked again up to twice the vectors and one; the scan, short too, once:
    # it has had every vector of its classes)
    assert asked == [21, 25, 21]


async def test_a_class_in_no_group_alone_is_scanned_and_gives_what_the_whole_search_gives_of_it(
    vectors, asked
):
    m = declare_agents()
    made = await planted(m)
    expected = await cut_by_hand(made["q"], {"Place"}, 10)
    asked.clear()

    found = await nearest(made["q"], types=["Place"], k=10)

    same_hits(found, expected)
    assert [hit.id for hit in found.hits] == [made["place 1"], made["place 2"]]
    assert asked == [41]
    # (from a vector too)
    by_vector = await nearest(vector={"a": [1, 0, 0], "b": [1, 0]}, types=["Place"])
    assert [hit.id for hit in by_vector.hits] == [made["place 1"], made["place 2"]]


async def test_part_of_a_group_is_scanned_and_a_class_without_vectors_is_never_found(
    vectors, settings, monkeypatch
):
    m = declare_agents()
    made = await planted(m)
    # (people but not saints: the group's index would give saints, so people are scanned)
    expected = await cut_by_hand(made["q"], {"Person"}, 10)
    same_hits(await nearest(made["q"], types=["Person"], k=10), expected)

    # (places left out since the vectors were built: still in the database, never found)
    monkeypatch.setattr(settings, "VECTORS_EXCLUDE", ["Place"])
    found = await nearest(made["q"], types=["Place", "Building", "Group"], k=10)
    assert {hit.type for hit in found.hits} == {"Group"}
    assert await nearest(made["q"], types=["Place"]) == Nearest("ok", [])


@no_type_check
async def test_an_unpublished_document_of_a_scanned_class_is_found_only_by_a_reader_who_may_see_it(
    vectors,
):
    m = declare_agents(reviewed=True)
    made = await planted(m)

    hidden = await nearest(made["q"], types=["Report"])
    seen = await nearest(made["q"], types=["Report"], see_unpublished=True)

    assert ids(hidden) == []
    assert ids(seen) == [made["report 1"], made["report 2"]]
    same_hits(seen, await cut_by_hand(made["q"], {"Report"}, 10, see_unpublished=True))


@no_type_check
async def test_an_entity_merged_into_another_is_no_hit_of_a_scanned_class(vectors):
    m = declare_agents()
    made = await planted(m)
    await m.Place.merge(made["place 1"], into=made["place 2"])

    found = await nearest(made["q"], types=["Place", "Building"])

    assert ids(found) == [made["building 1"], made["place 2"]]


async def test_during_a_rebuild_a_scanned_class_gives_each_item_once_of_the_generation_in_use(
    vectors,
):
    m = declare_agents()
    made = await planted(m)
    before = await nearest(made["q"], types=["Place", "Building"])
    assert len(before.hits) == 3

    # (a new generation of `a` written and combined, not switched to: every item the same as the query there)
    await write_and_combine(
        "a",
        [
            VectorRow(made[label], class_name, [1, 0, 0])
            for label, (class_name, *_v) in PLANTED.items()
        ],
    )
    during = await nearest(made["q"], types=["Place", "Building"])

    assert during == before


async def test_what_a_search_narrowed_to_types_is_given_is_checked(vectors):
    from pangloss_vectors.fields import NotAClass

    m = declare_agents()
    made = await planted(m)
    with pytest.raises(ValueError, match="a group or to types, not both"):
        await nearest(made["q"], group="Person", types=["Place"])
    with pytest.raises(ValueError, match="one or more classes"):
        await nearest(made["q"], types=[])
    with pytest.raises(ValueError, match="one or more classes"):
        await nearest(made["q"], types="Place")
    with pytest.raises(NotAClass, match="'Nothing' is not a class of documents"):
        await nearest(made["q"], types=["Place", "Nothing"])


# ---------------------------------------------------------------------------
# The scan's plan
# ---------------------------------------------------------------------------


def plan_of(db_driver, query: str, **parameters) -> list[str]:
    """The operators of the plan of a query (`EXPLAIN`), each with what it says of itself, from the top"""
    with db_driver.session(database=under_test().database) as session:
        if under_test().name == "neo4j":
            plan = session.run("EXPLAIN " + query, **parameters).consume().plan
            found: list[str] = []

            def walk(step: dict, depth: int) -> None:
                arguments = step.get("args") or step.get("arguments") or {}
                found.append(
                    f"{'  ' * depth}{step.get('operatorType', step.get('operator_type'))} "
                    f"{arguments.get('Details', '')}".rstrip()
                )
                for child in step.get("children", []):
                    walk(child, depth + 1)

            walk(plan, 0)
            return found
        rows = session.run("EXPLAIN " + query, **parameters).data()
        return [list(row.values())[0] for row in rows]


async def test_the_scan_finds_the_vectors_of_each_class_by_the_index_on_their_type(
    vectors, db_driver
):
    """(and not by `generation`, which on Memgraph reads the whole generation once for each class, nor by a scan of
    the index on `type`, which Neo4j plans on a nearly empty database: 8,000 vectors of 40 classes and two
    generations are planted, so that its planner has something to choose by)"""
    from pangloss_cypher.migrations import apply_changes
    from pangloss_models.migrations import changes as c
    from pangloss_models.migrations.files import EMPTY_SNAPSHOT
    from pangloss_testing.live import run
    from pangloss_testing.under_test.database import current
    from pangloss_vectors import structure

    await apply_changes(
        current(), EMPTY_SNAPSHOT, [c.AddIndex(index=e) for e in structure.INDEXES]
    )
    declare_agents()
    run(
        db_driver,
        f"CREATE (:{store.PROFILE_STATE} {{profile: 'default', generation: 1}})",
    )
    run(
        db_driver,
        f"UNWIND range(0, 7999) AS i CREATE (:{store.PROFILE_VECTOR} {{of: toString(i), profile: 'default', "
        "generation: i % 2, type: 'T' + toString(i % 40), vector: [1.0, 0.0, 0.0, 1.0, 0.0]})",
    )
    plan = plan_of(
        db_driver,
        search.scan_query(),
        profile="default",
        types=["T1", "T2"],
        fetch=41,
        vector=[0.0] * 5,
        of="x",
        k=10,
        see_unpublished=False,
    )
    print("\n" + "\n".join(plan))
    text = "\n".join(plan)
    if under_test().name == "memgraph":
        assert "ScanAllByLabelProperties (v :PGProfileVector {type})" in text, text
        assert not [s for s in plan if "ScanAll " in s or "ScanAllByLabel " in s], text
    else:
        assert (
            "NodeIndexSeek@neo4j RANGE INDEX v:PGProfileVector(type) WHERE type = t"
            in text
        ), text
        assert not [
            s
            for s in plan
            if "NodeByLabelScan" in s or "AllNodesScan" in s or "NodeIndexScan" in s
        ], text
    assert "PGProfileVector(generation)" not in text
    assert "(v :PGProfileVector {generation})" not in text
