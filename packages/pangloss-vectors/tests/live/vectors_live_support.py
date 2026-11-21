"""What the live tests of the class part and of search share: the vector indexes of today's profiles made (as the
project's migrations would make them) and dropped, and a rebuild of a part as step 2.5 will do it"""

import importlib
from types import SimpleNamespace
from typing import no_type_check

from pangloss_cypher.migrations import apply_changes
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT
from pangloss_testing.backends import under_test
from pangloss_testing.under_test.database import current
from pangloss_vectors import VectorRow, meta, store, structure
from pangloss_vectors.parts import part, profiles
from pangloss_vectors.store import Built


def vector_index_names(db_driver) -> list[str]:
    # (not in a transaction: Memgraph refuses its list in one)
    with db_driver.session(database=under_test().database) as session:
        if under_test().name == "neo4j":
            rows = session.run(
                "SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name"
            ).data()
            return [r["name"] for r in rows]
        return [r["index_name"] for r in session.run("SHOW VECTOR INDEX INFO").data()]


def drop_vector_indexes(db_driver, collect: bool = True) -> None:
    """The tests' own vector indexes dropped, by their names (the database is emptied between tests, its indexes are
    not); on Memgraph, with `collect`, the nodes deleted collected too (it keeps them in a vector index, and refuses an
    index of a label where one of them has the property at another length, until it collects them)"""
    with db_driver.session(database=under_test().database) as session:
        for name in vector_index_names(db_driver):
            if name.startswith("pgv_"):
                drop = (
                    f"DROP INDEX {name} IF EXISTS"
                    if under_test().name == "neo4j"
                    else f"DROP VECTOR INDEX {name}"
                )
                session.run(drop).consume()
        if collect and under_test().name == "memgraph":
            session.run("FREE MEMORY").consume()


async def make_vector_indexes() -> list[str]:
    """The vector index of each profile of today's settings and parts, and of each profile and group, as
    `structure.indexes()` would have the project's migrations make them. Gives their names"""
    entries = []
    for name, weights in profiles().items():
        if not weights:
            continue
        lay = store.layout(name, weights)
        entries.append(
            structure.vector_entry(lay.index_name, lay.label, lay.dimension, "test")
        )
        for group in meta.groups():
            entries.append(
                structure.vector_entry(
                    lay.group_index_name(group),
                    lay.group_label(group),
                    lay.dimension,
                    "test",
                )
            )
    changes = [
        c.AddIndex(index={k: v for k, v in entry.items() if k != "app"})
        for entry in entries
    ]
    await apply_changes(current(), EMPTY_SNAPSHOT, changes)
    return [entry["name"] for entry in entries]


async def write_and_combine(
    part_name: str, rows: list[VectorRow] | None = None
) -> tuple[Built, list[store.Combined]]:
    """A new generation of the part (its own `rebuild`, if no rows are given), and of each profile that weighs it,
    written and not switched to"""
    generation = await store.next_generation()
    if rows is None:
        written = 0

        async def write(page) -> None:
            nonlocal written
            written += await store.write_generation(part_name, generation, page)

        await part(part_name).rebuild(write)
        count = written
    else:
        count = await store.write_generation(part_name, generation, rows)
    combined = [
        await store.combine(
            name, await store.next_generation(), using={part_name: generation}
        )
        for name in store.profiles_weighing(part_name)
    ]
    built = Built(
        part_name,
        generation,
        count,
        signature=part(part_name).signature(),
        graph_sees="everyone",
    )
    return built, combined


async def build(part_name: str, rows: list[VectorRow] | None = None) -> int:
    """A rebuild of a part: a new generation and its profiles, the switch, the old generations dropped. Gives the
    new generation"""
    before = await store.states()
    built, combined = await write_and_combine(part_name, rows)
    await store.switch(built, combined)
    if part_name in before.parts:
        await store.drop_generation(part_name, before.parts[part_name].generation)
    for made in combined:
        if made.profile in before.profiles:
            await store.drop_profile_generation(
                made.profile, before.profiles[made.profile].generation
            )
    return built.generation


@no_type_check
def declare_events(reviewed: bool = False) -> SimpleNamespace:
    """A hierarchy of events and people (step 2.5, and phase 2's "documents of a like class"): `Event` above `Birth`
    and `Creation`, `Creation` above `CreationOfArtwork`, which is above `CreationOfPainting` and
    `CreationOfSculpture`; `Person` (a group) above `Saint`. With `reviewed`, a painting is reviewed (and saved
    unpublished)"""
    import pytest
    from pangloss_models import Document, Entity, ModelRegistry, initialise
    from pangloss_vectors import VectorsMeta

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

    class Event(Document):
        pass

    class Birth(Event):
        pass

    class Creation(Event):
        pass

    class CreationOfArtwork(Creation):
        pass

    CreationOfPainting = type(
        "CreationOfPainting",
        (CreationOfArtwork,),
        {"__module__": __name__, **review_meta},
    )

    class CreationOfSculpture(CreationOfArtwork):
        pass

    initialise()
    return SimpleNamespace(
        Person=Person,
        Saint=Saint,
        Event=Event,
        Birth=Birth,
        Creation=Creation,
        CreationOfArtwork=CreationOfArtwork,
        CreationOfPainting=CreationOfPainting,
        CreationOfSculpture=CreationOfSculpture,
    )


async def saved_events(m, **labels: list[str]) -> dict[str, str]:
    """Items saved, by class name and labels (`Birth=["b1"]`): their ids by label"""
    made = {}
    for class_name, names in labels.items():
        for label in names:
            made[label] = str(
                (await getattr(m, class_name).Create(label=label).save()).id
            )
    return made


# (seven items: two people, a birth, three paintings and an artwork)
EVENTS = {
    "Person": ["Anna", "Bernard"],
    "Birth": ["birth"],
    "CreationOfPainting": ["painting 1", "painting 2", "painting 3"],
    "CreationOfArtwork": ["artwork"],
}
