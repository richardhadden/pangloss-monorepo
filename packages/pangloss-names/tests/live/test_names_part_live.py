"""The name part on the backend under test (implementation_docs/similarity-build-plan.md, step 8.3): the suite every
part passes (`pangloss_testing.parts.PartSuite`), whose slow way here reads every name with a query of its own and
weighs them by the table of rarity **kept** with the generation in use, as a refresh does (so the claims after a
write are "exact against the last rebuild's table"); and the part's own claims: a rebuild after writes gives what a
fresh table gives, a person renamed has the new name's vector after one turn, a refresh before any rebuild does
nothing, an overlay of a person gives the vector it has once written."""

from typing import Any, no_type_check

import numpy as np
import pytest
from pangloss_names import maths
from pangloss_names import meta
from pangloss_names.part import NAME, PART, table_of
from pangloss_testing.live import run
from pangloss_testing.parts import PartSuite, differences, one_turn, stored, writes
from pangloss_testing.parts.suite import drop_vector_indexes
from pangloss_vectors import Changed, Item, store

pytestmark = pytest.mark.asyncio(loop_scope="session")

DIMENSION = 256

# (written plainly here, not the part's: every item of a class with names that is not merged into another and whose
# head is there and not deleted)
NAMES_QUERY = """
MATCH (n:PGIndexableNode)
WHERE n.type IN $types AND n.merged_into IS NULL
OPTIONAL MATCH (h:HeadNode {id: n.head_node_id})
WITH n, h WHERE (n.head_node_id IS NULL OR h IS NOT NULL) AND NOT coalesce(coalesce(h, n).deleted, false)
RETURN n.id AS id, n.type AS type, properties(n) AS properties
"""


def names_now(db_driver) -> dict[str, list[str]]:
    """Every item with names, by id: the values of its class's name fields, lists flattened, nulls left out"""
    fields_of = meta.named()
    found: dict[str, list[str]] = {}
    for row in run(db_driver, NAMES_QUERY, types=sorted(fields_of)):
        names: list[str] = []
        for field in fields_of[row["type"]]:
            value = row["properties"].get(field)
            if isinstance(value, list):
                names += [v for v in value if v is not None]
            elif value is not None:
                names.append(value)
        found[row["id"]] = names
    return found


def vectors_by(
    names: dict[str, list[str]], rarity: maths.Rarity
) -> dict[str, np.ndarray]:
    made = {
        of: maths.vector(given, rarity, DIMENSION, {}) for of, given in names.items()
    }
    return {of: vector for of, vector in made.items() if vector is not None}


def fresh_table(names: dict[str, list[str]]) -> maths.Rarity:
    return maths.Rarity.of(maths.words(given, {}) for given in names.values())


async def by_the_kept_table(db_driver) -> dict[str, Any]:
    """The slow way: every name read now, weighed by the table kept with the generation in use"""
    text = await store.kept(NAME)
    if text is None:
        return {}
    return vectors_by(names_now(db_driver), table_of(text))


class TestTheNamePart(PartSuite):
    parts = {"name": by_the_kept_table}


# ---------------------------------------------------------------------------
# The part's own
# ---------------------------------------------------------------------------


@pytest.fixture
def database(db_driver, clear_database):
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


@no_type_check
async def built(database) -> tuple[Any, dict[str, str]]:
    from pangloss_testing.similar_models import declare
    from pangloss_vectors.rebuild import rebuild

    m = declare()
    ids = await writes.write_shapes(m, database)
    await rebuild()
    await one_turn(database)
    return m, ids


@no_type_check
async def test_after_writes_and_a_turn_a_rebuild_gives_the_vectors_of_a_fresh_table(
    database,
):
    from pangloss_vectors.rebuild import rebuild

    m, ids = await built(database)
    await writes.create(m, ids)
    await writes.update_that_renames_a_person(m, ids)
    await m.Person.Create(label="Ada Smith").save()
    await one_turn(database)
    names = names_now(database)
    fresh = vectors_by(names, fresh_table(names))
    # (the writes changed what the table would count: the refreshed vectors are by the old one)
    assert differences(await stored(database, NAME), fresh) != []

    await rebuild()
    assert differences(await stored(database, NAME), fresh) == []
    assert table_of(await store.kept(NAME)) == fresh_table(names)


@no_type_check
async def test_a_person_renamed_has_the_vector_of_the_new_name_after_one_turn(
    database,
):
    m, ids = await built(database)
    rarity = table_of(await store.kept(NAME))
    before = (await stored(database, NAME))[ids["Ada"]]
    await m.Person.Update(id=ids["Ada"], label="Adelaide Bourne").save()
    await one_turn(database)

    after = (await stored(database, NAME))[ids["Ada"]]
    want = maths.vector(["Adelaide Bourne"], rarity, DIMENSION, {})
    assert differences({"Ada": after}, {"Ada": want}) == []
    assert differences({"Ada": before}, {"Ada": want}) != []


@no_type_check
async def test_a_refresh_before_any_rebuild_writes_nothing_and_fails_nothing(database):
    from pangloss_testing.similar_models import declare

    m = declare()
    ada = await m.Person.Create(label="Ada").save()
    written = []

    async def write(rows) -> None:
        written.extend(rows)

    refreshed = await PART.refresh(
        Changed(written=(Item(str(ada.id), "Person"),)), write
    )
    assert (refreshed.written, refreshed.stale, written) == (0, 0, [])
    assert run(database, "MATCH (v:PGVector) RETURN count(v) AS n")[0]["n"] == 0
    # (and the worker's turn, which skips a part never built, neither)
    await one_turn(database)
    assert await stored(database, NAME) == {}


@no_type_check
async def test_an_overlay_of_a_person_gives_the_vector_it_has_once_written(database):
    from pangloss_cypher.write_functions import to_db_model, write_head_node
    from pangloss_cypher.write_plan import plan_create

    m, _ = await built(database)
    instance = to_db_model(m.Person.Create(label="Hal Ford"))
    overlaid = await PART.overlay(plan_create(instance))
    assert list(overlaid) == [str(instance.id)]
    await write_head_node(instance)
    await one_turn(database)

    have = await stored(database, NAME)
    assert differences(overlaid, {str(instance.id): have[str(instance.id)]}) == []


@no_type_check
async def test_a_refresh_counts_as_stale_the_names_that_changed_and_no_others(
    database,
):
    """(the turn after the rebuild in `built` refreshed the heads written before it, which the rebuild had counted:
    their vectors are what was stored, so none of them is stale)"""
    m, ids = await built(database)
    assert (await store.states()).parts[NAME].stale == 0
    await writes.update_that_renames_a_person(m, ids)
    await one_turn(database)
    assert (await store.states()).parts[NAME].stale == 1
    # (saved again with the name it has: the same vector, and nothing more to count)
    label = (await m.Person.get(ids["Ada"])).label
    await m.Person.Update(id=ids["Ada"], label=label).save()
    await one_turn(database)
    assert (await store.states()).parts[NAME].stale == 1
    # (a new person is a name the table did not count)
    await m.Person.Create(label="Balthasar Quittenbaum").save()
    await one_turn(database)
    assert (await store.states()).parts[NAME].stale == 2


@no_type_check
async def test_an_item_whose_names_give_no_vector_loses_its_vector(database):
    m, ids = await built(database)
    assert ids["Ada"] in await stored(database, NAME)
    await m.Person.Update(id=ids["Ada"], label="--").save()
    await one_turn(database)
    assert ids["Ada"] not in await stored(database, NAME)
    assert ids["Ada"] not in await by_the_kept_table(database)


@no_type_check
async def test_documents_with_names_nested_in_a_head_are_refreshed_with_it(
    database, monkeypatch
):
    """(no class of documents of `similar_models` has names: here the statements `Transfer` and `ChildOf` are given
    theirs, their labels, as `NamesMeta(include=True)` would)"""
    plain = meta.named

    def with_statements() -> dict[str, list[str]]:
        return {**plain(), "Transfer": ["label"], "ChildOf": ["label"]}

    monkeypatch.setattr(meta, "named", with_statements)
    m, ids = await built(database)
    before = await stored(database, NAME)
    assert ids["Fay child"] in before and ids["transfer"] in before

    await writes.update_that_replaces_its_statements(m, ids)
    await one_turn(database)
    after = await stored(database, NAME)
    assert ids["Fay child"] not in after
    [new] = [
        row["id"]
        for row in run(
            database,
            "MATCH (n:PGIndexableNode {head_node_id: $head}) WHERE n.type = 'Transfer' RETURN n.id AS id",
            head=ids["Fay's parent"],
        )
    ]
    assert new in after
    assert differences(after, await by_the_kept_table(database)) == []


@no_type_check
async def test_a_head_written_of_a_class_that_no_longer_has_names_loses_its_vector(
    database, monkeypatch
):
    """(as a head whose class was changed in place to a class without names: `similar_models` has no entity without
    names, so here `Person` stops having them after the rebuild)"""
    m, ids = await built(database)
    assert {ids["Ada"], ids["Ben"]} <= set(await stored(database, NAME))
    plain = meta.named()
    monkeypatch.setattr(
        meta, "named", lambda: {k: v for k, v in plain.items() if k != "Person"}
    )
    await m.Person.Update(id=ids["Ada"], label="Ada again").save()
    await one_turn(database)

    after = await stored(database, NAME)
    assert ids["Ada"] not in after
    # (and only the head written: nothing else is looked for)
    assert ids["Ben"] in after


@no_type_check
async def test_built_with_its_table_gone_a_refresh_says_a_rebuild_is_due_and_the_worker_goes_on(
    database,
):
    m, ids = await built(database)
    before = (await stored(database, NAME))[ids["Ada"]]
    run(database, "MATCH (k:PGVectorKept {part: $part}) DETACH DELETE k", part=NAME)
    PART.forget()

    with pytest.raises(store.RebuildDue, match="table of rarity"):
        await PART.refresh(Changed(written=(Item(ids["Ada"], "Person"),)), None)
    await m.Person.Update(id=ids["Ada"], label="Adelaide Bourne").save()
    await one_turn(database)
    # (nothing written by a table that is not there: the vector is as it was, until a rebuild)
    assert (await stored(database, NAME))[ids["Ada"]] == before
