"""The vectors in the graph (implementation_docs/similarity-build-plan.md, step 2.2), on the backend under test:
written and read by item, generations and the switch, `set_vectors` in place, the labels of groups, deletes, and the
vector indexes that follow the project's models through its migrations."""

from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_models import Document, Entity, ModelRegistry, initialise
from pangloss_models.migrations import build_snapshot
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import MigrationGraph
from pangloss_models.migrations.planner import plan
from pangloss_testing.backends import under_test
from pangloss_testing.live import run
from pangloss_testing.under_test import migration_backend as backend
from pangloss_vectors import VectorRow, VectorsMeta, store
from pangloss_vectors.store import Built, Layout, RebuildDue, VectorLengthError
from vectors_support import SizedPart

pytestmark = pytest.mark.asyncio(loop_scope="session")

PROJECT = "pgv_live_project"

SOURCE = """
class Person(Entity):
    {person}

class Saint(Person):
    pass

class Statement(Document):
    pass
"""


@no_type_check
def declare(searchable: bool = True) -> SimpleNamespace:
    """The models of the tests, as if in the project's app (`pgv_live_project.models`)"""
    ModelRegistry._reset()
    namespace = {
        "__name__": f"{PROJECT}.models",
        "Document": Document,
        "Entity": Entity,
        "VectorsMeta": VectorsMeta,
    }
    exec(
        SOURCE.format(
            person="_vectors_meta = VectorsMeta(searchable=True)"
            if searchable
            else "pass"
        ),
        namespace,
    )
    initialise()
    return SimpleNamespace(
        **{n: namespace[n] for n in ("Person", "Saint", "Statement")}
    )


def vector_indexes(db_driver) -> dict[str, tuple[str, int]]:
    """The vector indexes of the database, by name: (label, dimension)"""
    # (not in a transaction: Memgraph refuses its list in one)
    with db_driver.session(database=under_test().database) as session:
        if under_test().name == "neo4j":
            rows = session.run(
                "SHOW INDEXES YIELD name, type, labelsOrTypes, options WHERE type = 'VECTOR' RETURN *"
            ).data()
            return {
                r["name"]: (
                    r["labelsOrTypes"][0],
                    r["options"]["indexConfig"]["vector.dimensions"],
                )
                for r in rows
            }
        rows = session.run("SHOW VECTOR INDEX INFO").data()
    return {
        r["index_name"]: (r["label"].removeprefix(":"), r["dimension"]) for r in rows
    }


def drop_vector_indexes(db_driver) -> None:
    """(the tests' own, by their names: the database is emptied between tests, its indexes are not)"""
    with db_driver.session(database=under_test().database) as session:
        for name in vector_indexes(db_driver):
            if name.startswith("pgv_"):
                drop = (
                    f"DROP INDEX {name} IF EXISTS"
                    if under_test().name == "neo4j"
                    else f"DROP VECTOR INDEX {name}"
                )
                session.run(drop).consume()
        if under_test().name == "memgraph":
            # (Memgraph keeps deleted nodes in a vector index, and refuses an index of a label where one of them has
            # the property at another length, until it collects them)
            session.run("FREE MEMORY").consume()


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


def row(of: str, type_name: str, *vector: float) -> VectorRow:
    return VectorRow(of=of, type=type_name, vector=list(vector))


A1 = [
    row("p1", "Person", 1, 0, 0),
    row("s1", "Saint", 0, 1, 0),
    row("t1", "Statement", 0, 0, 1),
]
B1 = [row("p1", "Person", 3, 4), row("s1", "Saint", 0, 2)]


async def build(part: str, rows: list[VectorRow]) -> int:
    """A rebuild of a part as 2.5 will do it: a new generation, each profile that weighs it combined from it, the
    switch, the old generation dropped. Gives the new generation"""
    before = await store.states()
    generation = await store.next_generation()
    count = await store.write_generation(part, generation, rows)
    combined = []
    for name in store.profiles_weighing(part):
        combined.append(
            await store.combine(
                name, await store.next_generation(), using={part: generation}
            )
        )
    await store.switch(
        Built(part, generation, count, signature="s", graph_sees="everyone"), combined
    )
    if part in before.parts:
        await store.drop_generation(part, before.parts[part].generation)
    for made in combined:
        if made.profile in before.profiles:
            await store.drop_profile_generation(
                made.profile, before.profiles[made.profile].generation
            )
    return generation


async def profile_vector(of: str) -> tuple[list[float], list[str]]:
    """The item's vector of the default profile in use, and its labels: it must have one"""
    found = await store.read_profile(of, "default")
    assert found is not None, f"{of} has no vector of the default profile"
    return found


def default_layout() -> Layout:
    return store.layout("default")


# ---------------------------------------------------------------------------
# Written, read, generations
# ---------------------------------------------------------------------------


async def test_vectors_are_written_and_read_by_item_and_the_profile_s_vector_is_made_from_them(
    vectors,
):
    declare()
    await build("a", A1)
    await build("b", B1)
    assert await store.read("p1") == {"a": [1.0, 0.0, 0.0], "b": [3.0, 4.0]}
    assert await store.read("t1") == {"a": [0.0, 0.0, 1.0]}
    assert await store.read("nobody") == {}

    lay = default_layout()
    assert lay.dimension == 5
    vector, labels = await profile_vector("p1")
    assert vector == pytest.approx(lay.combine({"a": [1, 0, 0], "b": [3, 4]}))
    assert labels == ["PGV_default_5", "PGV_default_5_Person"]
    vector, _ = await profile_vector("t1")
    assert vector == pytest.approx([0, 0, 1, 0, 0])

    found = await store.states()
    assert set(found.parts) == {"a", "b"} and found.parts["a"].count == 3
    state = found.profiles["default"]
    assert (state.dimension, state.count, state.signature) == (5, 3, lay.signature())
    assert (
        found.parts["b"].built_at is not None
        and found.parts["b"].graph_sees == "everyone"
    )


async def test_a_second_generation_is_not_read_until_the_switch_and_the_first_goes_after_it(
    db_driver, vectors
):
    declare()
    first = await build("a", A1)
    generation = await store.next_generation()
    assert generation > first
    await store.write_generation("a", generation, [row("p1", "Person", 0, 0, 7)])
    combined = await store.combine(
        "default", await store.next_generation(), using={"a": generation}
    )
    # (written beside the one in use, which is still what is read)
    assert await store.read("p1") == {"a": [1.0, 0.0, 0.0]}
    vector, _ = await profile_vector("p1")
    assert vector[:3] == pytest.approx([1, 0, 0])

    with pytest.raises(ValueError, match="'default' weighs the a part"):
        await store.switch(Built("a", generation, 1, "s", "everyone"))
    old_profile = (await store.states()).profiles["default"].generation
    await store.switch(Built("a", generation, 1, "s", "everyone"), [combined])
    assert await store.read("p1") == {"a": [0.0, 0.0, 7.0]}
    vector, _ = await profile_vector("p1")
    assert vector[:3] == pytest.approx([0, 0, 1])
    # (an item that is not in the new generation has none)
    assert (
        await store.read("s1") == {}
        and await store.read_profile("s1", "default") is None
    )

    with pytest.raises(ValueError, match="in use"):
        await store.drop_generation("a", generation)
    assert await store.drop_generation("a", first, page=2) == 3
    assert await store.drop_profile_generation("default", old_profile) == 3
    left = run(db_driver, "MATCH (v:PGVector) RETURN v.generation AS g")
    assert [r["g"] for r in left] == [generation]
    with pytest.raises(ValueError, match="the one of the a part in use"):
        await store.write_generation("a", generation, A1)


async def test_set_vectors_changes_the_generation_in_use_in_place_and_the_profile_s_vector_follows(
    db_driver, vectors
):
    declare()
    generation = await build("a", A1)
    await build("b", B1)
    profile_generation = (await store.states()).profiles["default"].generation

    assert (
        await store.set_vectors(
            "a", [row("p1", "Person", 0, 2, 0), row("n1", "Statement", 1, 1, 0)]
        )
        == 2
    )
    assert await store.read("p1") == {"a": [0.0, 2.0, 0.0], "b": [3.0, 4.0]}
    assert await store.read("n1") == {"a": [1.0, 1.0, 0.0]}
    vector, _ = await profile_vector("p1")
    assert vector == pytest.approx(
        default_layout().combine({"a": [0, 1, 0], "b": [3, 4]})
    )
    assert (await store.read_profile("n1", "default")) is not None

    # (in place: no new generation, and one vector of each)
    found = await store.states()
    assert found.parts["a"].generation == generation
    assert found.profiles["default"].generation == profile_generation
    rows = run(
        db_driver, "MATCH (v:PGVector {of: 'p1', part: 'a'}) RETURN count(v) AS n"
    )
    assert rows[0]["n"] == 1
    rows = run(db_driver, "MATCH (v:PGProfileVector {of: 'p1'}) RETURN count(v) AS n")
    assert rows[0]["n"] == 1


async def test_set_vectors_before_a_part_is_built_is_refused(vectors):
    declare()
    with pytest.raises(RebuildDue, match="has no vectors in use"):
        await store.set_vectors("a", A1)


async def test_set_vectors_is_refused_when_a_profile_in_use_is_of_another_dimension(
    vectors,
):
    declare()
    await build("a", A1)
    vectors.b.size = 3
    with pytest.raises(RebuildDue, match="dimension 5.*make 6"):
        await store.set_vectors("a", A1)


# ---------------------------------------------------------------------------
# Groups, what is left out, what is refused, deletes
# ---------------------------------------------------------------------------


async def test_the_labels_of_groups_follow_the_item_s_class_and_the_classes_above_it(
    vectors,
):
    declare()
    await build("a", A1)
    assert (await profile_vector("s1"))[1] == [
        "PGV_default_5",
        "PGV_default_5_Person",
    ]
    assert (await profile_vector("t1"))[1] == ["PGV_default_5"]

    # (an item whose class changed: the labels follow it, in place)
    await store.set_vectors(
        "a", [row("s1", "Statement", 0, 1, 0), row("t1", "Saint", 0, 0, 1)]
    )
    assert (await profile_vector("s1"))[1] == ["PGV_default_5"]
    assert (await profile_vector("t1"))[1] == [
        "PGV_default_5",
        "PGV_default_5_Person",
    ]


@no_type_check
async def test_the_items_of_a_class_left_out_get_no_vectors(vectors):
    ModelRegistry._reset()

    class Person(Entity):
        pass

    class Note(Document):
        _vectors_meta = VectorsMeta(include=False)

    initialise()
    await build("a", [row("p1", "Person", 1, 0, 0), row("n1", "Note", 0, 1, 0)])
    assert await store.read("n1") == {}
    assert await store.read_profile("n1", "default") is None
    assert (await store.states()).parts["a"].count == 1
    await store.set_vectors("a", [row("n2", "Note", 1, 1, 1)])
    assert await store.read("n2") == {}


async def test_a_vector_of_the_wrong_length_is_refused_before_anything_is_written(
    db_driver, vectors
):
    declare()
    generation = await store.next_generation()
    with pytest.raises(VectorLengthError, match="The a vector of p2 has 2 numbers"):
        await store.write_generation(
            "a", generation, [row("p1", "Person", 1, 0, 0), row("p2", "Person", 1, 0)]
        )
    assert run(db_driver, "MATCH (v:PGVector) RETURN count(v) AS n")[0]["n"] == 0
    await build("a", A1)
    with pytest.raises(VectorLengthError):
        await store.set_vectors("a", [row("p1", "Person", 1, 0, 0, 0)])
    assert await store.read("p1") == {"a": [1.0, 0.0, 0.0]}


async def test_delete_for_takes_every_vector_of_the_items(db_driver, vectors):
    declare()
    await build("a", A1)
    await build("b", B1)
    # (and those of a generation not in use)
    await store.write_generation(
        "a", await store.next_generation(), [row("p1", "Person", 1, 1, 1)]
    )
    assert await store.delete_for(["p1", "s1", "nobody"]) == 7
    assert (
        await store.read("p1") == {}
        and await store.read_profile("s1", "default") is None
    )
    assert await store.read("t1") == {"a": [0.0, 0.0, 1.0]}
    left = run(
        db_driver, "MATCH (v) WHERE v:PGVector OR v:PGProfileVector RETURN v.of AS of"
    )
    assert {r["of"] for r in left} == {"t1"}
    assert await store.delete_for([]) == 0


# ---------------------------------------------------------------------------
# The vector indexes, by the project's migrations
# ---------------------------------------------------------------------------


@pytest.fixture
def project_installed(monkeypatch, settings):
    """The project's app installed beside this package (its models are declared in `pgv_live_project.models`)"""
    monkeypatch.setattr(settings, "INSTALLED_APPS", ["pangloss_vectors", PROJECT])
    return ["pangloss_vectors", PROJECT]


def snapshot() -> dict:
    return build_snapshot(backend.structure())


def vector_changes(migration) -> list:
    return [
        change
        for change in migration.changes
        if isinstance(change, (c.AddIndex, c.RemoveIndex))
        and change.index["kind"] == "vector"
    ]


async def made_by_migrations(apps: list[str], *versions) -> tuple[MigrationGraph, list]:
    """The migrations of the models each version declares, planned and applied one after the other, as
    `makemigrations` and `migrate` would: the graph, and the migrations of each step"""
    await backend.ensure_ready()
    graph = MigrationGraph()
    steps = []
    for version in versions:
        version()
        planned = plan(graph, snapshot(), apps)
        await backend.apply(planned.migrations, graph.state())
        graph = MigrationGraph.of([*graph.migrations.values(), *planned.migrations])
        steps.append(planned.migrations)
    return graph, steps


async def test_a_class_made_searchable_is_a_migration_of_the_project_s_app_that_makes_its_indexes(
    db_driver, vectors, project_installed
):
    graph, (first, second) = await made_by_migrations(
        project_installed,
        lambda: declare(searchable=False),
        lambda: declare(searchable=True),
    )
    # (the profile's own index came with the project's first migration)
    (project_first,) = [m for m in first if m.app == PROJECT]
    assert [ch.index["name"] for ch in vector_changes(project_first)] == [
        "pgv_default_5"
    ]

    # the class made searchable: one migration, the project's, with the group's index
    assert [m.app for m in second] == [PROJECT]
    assert second[0].changes == (
        c.AddIndex(
            index={
                "kind": "vector",
                "name": "pgv_default_5_person",
                "label": "PGV_default_5_Person",
                "properties": ["vector"],
                "dimension": 5,
                "metric": "cos",
                "quantization": False,
            }
        ),
    )
    indexes = vector_indexes(db_driver)
    assert indexes["pgv_default_5"] == ("PGV_default_5", 5)
    assert indexes["pgv_default_5_person"] == ("PGV_default_5_Person", 5)
    # (nothing is pending now)
    assert plan(graph, snapshot(), project_installed).migrations == []


async def test_a_change_of_a_part_s_dimension_drops_the_old_indexes_and_makes_new_ones_by_other_names(
    db_driver, vectors, project_installed
):
    graph, _ = await made_by_migrations(project_installed, declare)
    await build("a", A1)

    vectors.a.size = 4
    planned = plan(graph, snapshot(), project_installed)
    assert [m.app for m in planned.migrations] == [PROJECT]
    changes = vector_changes(planned.migrations[0])
    assert {(type(ch).__name__, ch.index["name"]) for ch in changes} == {
        ("RemoveIndex", "pgv_default_5"),
        ("RemoveIndex", "pgv_default_5_person"),
        ("AddIndex", "pgv_default_6"),
        ("AddIndex", "pgv_default_6_person"),
    }
    await backend.apply(planned.migrations, graph.state())

    indexes = {
        n: v for n, v in vector_indexes(db_driver).items() if n.startswith("pgv_")
    }
    assert indexes == {
        "pgv_default_6": ("PGV_default_6", 6),
        "pgv_default_6_person": ("PGV_default_6_Person", 6),
    }
    # (the vectors of the old dimension are still there, under their own labels, until a rebuild)
    rows = run(db_driver, "MATCH (n:PGV_default_5) RETURN count(n) AS n")
    assert rows[0]["n"] == 3
    await build("a", [row("p1", "Person", 1, 0, 0, 0)])
    vector, labels = await profile_vector("p1")
    assert len(vector) == 6 and labels == ["PGV_default_6", "PGV_default_6_Person"]
