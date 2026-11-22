"""The graph part on the backend under test (implementation_docs/similarity-build-plan.md, step 3.3): a rebuild stores
the oracle's vector of every stop; after each kind of write a refresh of the heads written leaves the stored vectors
equal to a fresh oracle's; an overlay of a write plan gives the vectors the same plan gives once written; past the cap a
refresh writes approximate vectors of the heads written alone, and says they are stale."""

from typing import no_type_check

import pytest
from pangloss_cypher.write_functions import (
    replace_head_node,
    to_db_model,
    write_head_node,
)
from pangloss_cypher.write_plan import plan_create, plan_update
from pangloss_fastrp import maps, maths
from pangloss_fastrp.cypher_reader import reading
from pangloss_fastrp.maths import pair
from pangloss_fastrp.part import PART, refresh_ids
from pangloss_testing.live import run
from pangloss_testing.similar_models import declare
from pangloss_users import current_request_username
from pangloss_vectors import Changed, Item
from pangloss_vectors.parts import parts, profiles
from pangloss_vectors.rebuild import rebuild

from fastrp_live_support import (
    differences,
    drop_vector_indexes,
    fresh_oracle,
    set_in_use,
    stored,
    transfer,
    write_shapes,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def database(db_driver, clear_database):
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


async def built(m, db_driver, **saved) -> dict[str, str]:
    """The shapes written and the graph part rebuilt"""
    ids = await write_shapes(m, db_driver, **saved)
    await rebuild("graph")
    return ids


async def equal_to_a_rebuild(db_driver) -> None:
    assert differences(await stored(db_driver), await fresh_oracle()) == []


def node_count(db_driver) -> int:
    return run(db_driver, "MATCH (n) RETURN count(n) AS n")[0]["n"]


async def test_the_default_profile_is_the_graph_at_1_and_the_class_at_0_1():
    """(with no `VECTORS_PROFILES`: the parts' own weights)"""
    # (a part of weight 0, as the name part's when another package's tests have imported it in this process, is
    # registered and in no default profile)
    assert set(parts()) >= {"class", "graph"}
    assert profiles()["default"] == {"class": 0.1, "graph": 1.0}


@no_type_check
async def test_a_rebuild_stores_the_oracle_s_vector_of_every_stop_as_a_list_of_floats(
    database,
):
    m = declare()
    ids = await built(m, database)
    have = await stored(database)
    assert differences(have, await fresh_oracle()) == []
    # (nested documents have vectors; what is out has none)
    assert {ids["transfer"], ids["activity"], ids["Ada"]} <= set(have)
    assert ids["siblings"] not in have and ids["sibling"] not in have
    assert all(isinstance(x, float) for x in have[ids["Ada"]])
    assert len(have[ids["Ada"]]) == PART.dimension() == 128


# ---------------------------------------------------------------------------
# A refresh after each kind of write
# ---------------------------------------------------------------------------


def ref(id: str, kind: str = "Person") -> dict:
    return {"type": kind, "id": id}


@no_type_check
async def test_a_refresh_after_a_new_document_is_saved(database):
    m = declare()
    ids = await built(m, database)
    new = await m.Factoid.Create(
        label="another gift",
        statements=[
            {
                "type": "Transfer",
                "label": "Gus gave to Parent",
                "given_by": ref(ids["Gus"]),
                "given_to": ref(ids["Parent"]),
            }
        ],
    ).save()
    refreshed = await refresh_ids([new.id], set_in_use)
    assert refreshed.written > 0 and refreshed.stale == 0
    await equal_to_a_rebuild(database)


@no_type_check
async def test_a_refresh_after_an_update_that_adds_a_reference(database):
    m = declare()
    ids = await built(m, database)
    await m.Factoid.Update(
        id=ids["two names"],
        label="two names",
        statements=[
            {
                "type": "SameEntity",
                "label": "Dee is Eve",
                "target": [ref(ids["Dee"]), ref(ids["Eve"])],
            },
            {
                "type": "Transfer",
                "label": "Gus gave to Parent",
                "given_by": ref(ids["Gus"]),
                "given_to": ref(ids["Parent"]),
            },
        ],
    ).save()
    await refresh_ids([ids["two names"]], set_in_use)
    await equal_to_a_rebuild(database)


async def drop_a_reference(m, ids) -> None:
    """The meeting written again without Eve (and so without the `Sworn` that held her)"""
    await m.Factoid.Update(
        id=ids["meeting"],
        label="meeting",
        statements=[
            {
                "type": "Activity",
                "label": "Ada met Dee",
                "carried_out_by": ref(ids["Ada"]),
                "participants": [
                    {"type": "InRole", "role": "guest", "target": [ref(ids["Dee"])]}
                ],
            }
        ],
    ).save()


@no_type_check
async def test_a_refresh_after_an_update_that_drops_a_reference_given_what_was_named_before(
    database,
):
    m = declare()
    ids = await built(m, database)
    await drop_a_reference(m, ids)
    # (what the meeting's tree was joined to before, and the activity it held: the update wrote a new one, and the
    # old one is gone from the graph, its vector with nothing to say it should go)
    await refresh_ids(
        [ids["meeting"]], set_in_use, before=[ids["activity"], ids["Eve"], ids["place"]]
    )
    await equal_to_a_rebuild(database)


@no_type_check
async def test_the_part_s_refresh_after_an_update_that_drops_a_reference_given_what_was_named_before(
    database,
):
    """(`Changed.before`, as the worker gives it from the update's mark: the old tree's references and nested
    documents. Without it the dropped reference cannot be found: `test_fastrp_worker_live.py` has the worker)"""
    m = declare()
    ids = await built(m, database)
    await drop_a_reference(m, ids)
    await PART.refresh(
        Changed(
            written=(Item(ids["meeting"], "Factoid"),),
            before=(ids["activity"], ids["Eve"], ids["place"]),
        ),
        set_in_use,
    )
    await equal_to_a_rebuild(database)


@no_type_check
async def test_a_refresh_after_a_delete(database):
    m = declare()
    ids = await built(m, database)
    await m.Factoid.delete(ids["meeting"])
    await PART.refresh(Changed(removed=(ids["meeting"],)), set_in_use)
    await equal_to_a_rebuild(database)
    have = await stored(database)
    assert ids["meeting"] not in have and ids["activity"] not in have


@no_type_check
async def test_a_refresh_after_a_merge_and_after_its_undo(database):
    m = declare()
    ids = await built(m, database)
    merged = await m.Person.merge(absorb=ids["Eve"], into=ids["Dee"])
    await PART.refresh(
        Changed(
            written=(Item(ids["meeting"], "Factoid"), Item(ids["Dee"], "Person")),
            removed=(ids["Eve"],),
        ),
        set_in_use,
    )
    await equal_to_a_rebuild(database)
    assert ids["Eve"] not in await stored(database)

    await m.Person.unmerge(merged.merge.id)
    await PART.refresh(
        Changed(
            written=(
                Item(ids["meeting"], "Factoid"),
                Item(ids["Dee"], "Person"),
                Item(ids["Eve"], "Person"),
            )
        ),
        set_in_use,
    )
    await equal_to_a_rebuild(database)
    assert ids["Eve"] in await stored(database)


@no_type_check
async def test_a_refresh_after_a_new_citation(database):
    m = declare()
    ids = await built(m, database)
    new = await m.Factoid.Create(
        label="another inference",
        statements=[
            {
                "type": "Inference",
                "label": "So Ada knew Dee",
                "evidence": [{"type": "Activity", "id": ids["activity"]}],
            }
        ],
    ).save()
    await PART.refresh(Changed(written=(Item(str(new.id), "Factoid"),)), set_in_use)
    await equal_to_a_rebuild(database)


@no_type_check
async def test_a_refresh_after_a_publish(database):
    """Under `VECTORS_GRAPH_SEES = "everyone"`, a document is in the graph once it is published"""
    pytest.importorskip("pangloss_review")
    from pangloss_review.service import set_status
    from pangloss_review.status import ReviewStatus

    m = declare(reviewed=True)
    ids = await built(m, database, published=True)
    secret = await m.Factoid.Create(
        label="secret", statements=[transfer(_people(ids))]
    ).save()
    await PART.refresh(Changed(written=(Item(str(secret.id), "Factoid"),)), set_in_use)
    await equal_to_a_rebuild(database)
    assert str(secret.id) not in await stored(database)

    await set_status(secret.id, ReviewStatus.PUBLISHED, current_request_username.get())
    await PART.refresh(Changed(written=(Item(str(secret.id), "Factoid"),)), set_in_use)
    await equal_to_a_rebuild(database)
    assert str(secret.id) in await stored(database)


def _people(ids: dict[str, str]) -> dict:
    """The people of `ids` as `transfer` takes them (anything with an `id`)"""
    from types import SimpleNamespace

    return {name: SimpleNamespace(id=ids[name]) for name in ("Ada", "Ben", "Cy")}


@no_type_check
async def test_past_the_cap_a_refresh_writes_approximate_vectors_of_the_heads_written_alone_and_says_they_are_stale(
    database, settings, monkeypatch
):
    m = declare()
    ids = await built(m, database)
    before = await stored(database)
    new = await m.Factoid.Create(
        label="another gift", statements=[transfer(_people(ids))]
    ).save()
    statement = str((await m.Factoid.get(new.id)).statements[0].id)
    monkeypatch.setattr(settings, "FASTRP_REFRESH_CAP", 5)
    refreshed = await PART.refresh(
        Changed(written=(Item(str(new.id), "Factoid"),)), set_in_use
    )
    # (the factoid and its transfer, both approximate: none written exactly, two stale; nothing else is touched)
    assert (refreshed.written, refreshed.stale) == (0, 2)
    after = await stored(database)
    assert set(after) == set(before) | {str(new.id), statement}
    assert all(after[of] == vector for of, vector in before.items())
    # (and a head removed past the cap: its neighbours are left as they were, and stale)
    await m.Factoid.delete(new.id)
    refreshed = await PART.refresh(Changed(removed=(str(new.id),)), set_in_use)
    assert (refreshed.written, refreshed.stale) == (0, 1)


# ---------------------------------------------------------------------------
# An overlay
# ---------------------------------------------------------------------------


@no_type_check
async def test_an_overlay_of_a_new_document_gives_the_vectors_it_has_once_written(
    database,
):
    """The plan of a factoid's `CreateDB`, overlaid, then that same instance written (so its nested ids are the
    plan's): for every stop of the plan, the vector a rebuild then gives"""
    m = declare()
    ids = await built(m, database)
    instance = to_db_model(
        m.Factoid.Create(
            label="a meeting overlaid",
            statements=[
                {
                    "type": "Activity",
                    "label": "Gus met Ada and Fay",
                    "carried_out_by": ref(ids["Gus"]),
                    "participants": [
                        {
                            "type": "InRole",
                            "role": "guest",
                            "at": ref(ids["place"], "Place"),
                            "target": [ref(ids["Ada"])],
                        },
                        {
                            "type": "Sworn",
                            "role": "witness",
                            "target": [ref(ids["Fay"])],
                        },
                    ],
                },
                {
                    "type": "Inference",
                    "label": "So Gus knew Ben",
                    "evidence": [{"type": "Transfer", "id": ids["transfer"]}],
                },
            ],
        )
    )
    plan = plan_create(instance)
    nodes = node_count(database)
    overlaid = await PART.overlay(plan)
    assert node_count(database) == nodes
    stops = {
        str(instance.id),
        str(instance.statements[0].id),
        str(instance.statements[1].id),
    }
    assert stops <= set(overlaid)
    # (the people it names have vectors that the write changes: the overlay gives those of the plan's own stops)
    assert set(overlaid) == stops

    await write_head_node(instance)
    assert (
        differences(
            overlaid, {k: v for k, v in (await fresh_oracle()).items() if k in overlaid}
        )
        == []
    )


@no_type_check
async def test_an_overlay_of_an_update_takes_away_what_was_below_the_head(database):
    m = declare()
    ids = await built(m, database)
    instance = to_db_model(
        m.Factoid.Update(
            id=ids["meeting"],
            label="meeting",
            statements=[
                {
                    "type": "Activity",
                    "label": "Ada met Gus",
                    "carried_out_by": ref(ids["Ada"]),
                    "participants": [
                        {"type": "InRole", "role": "guest", "target": [ref(ids["Gus"])]}
                    ],
                }
            ],
        )
    )
    overlaid = await PART.overlay(plan_update(instance))
    assert ids["activity"] not in overlaid
    await replace_head_node(instance)
    want = await fresh_oracle()
    assert set(overlaid) == {ids["meeting"], str(instance.statements[0].id)}
    assert differences(overlaid, {k: want[k] for k in overlaid}) == []


@no_type_check
async def test_an_overlay_of_a_description_has_no_candidates_yet(database):
    """A `MatchesCriteria` in a plan has none: its worker finds them after the write"""
    from fastrp_live_support import described

    m = declare()
    ids = await built(m, database)
    group = _named(ids, "group")
    instance = to_db_model(
        m.Factoid.Create(
            label="another gift from a member",
            statements=[described({"Ada": _named(ids, "Ada")}, group)],
        )
    )
    overlaid = await PART.overlay(plan_create(instance))
    await write_head_node(instance)
    want = await fresh_oracle()
    assert set(overlaid) == {str(instance.id), str(instance.statements[0].id)}
    assert differences(overlaid, {k: want[k] for k in overlaid}) == []
    # (the transfer is joined to the factoid and to Ada alone)
    graph = maps.graph_maps()
    statement = str(instance.statements[0].id)
    assert await reading(
        graph, lambda reader: maths.joins(reader, graph, [statement])
    ) == {
        pair(str(instance.id), statement): 1.0,
        pair(statement, ids["Ada"]): 1.0,
    }


def _named(ids: dict[str, str], name: str):
    from types import SimpleNamespace

    return SimpleNamespace(id=ids[name])


@no_type_check
async def test_an_overlay_of_a_reference_to_a_merged_entity_joins_its_survivor(
    database,
):
    m = declare()
    ids = await built(m, database)
    await m.Person.merge(absorb=ids["Eve"], into=ids["Dee"])
    await rebuild("graph")
    instance = to_db_model(
        m.Factoid.Create(
            label="a gift to Eve",
            statements=[
                {
                    "type": "Transfer",
                    "label": "Ada gave to Eve",
                    "given_by": ref(ids["Ada"]),
                    "given_to": ref(ids["Eve"]),
                }
            ],
        )
    )
    overlaid = await PART.overlay(plan_create(instance))
    await write_head_node(instance)
    want = await fresh_oracle()
    assert differences(overlaid, {k: want[k] for k in overlaid}) == []
    graph = maps.graph_maps()
    statement = str(instance.statements[0].id)
    assert await reading(
        graph, lambda reader: maths.joins(reader, graph, [statement])
    ) == {
        pair(str(instance.id), statement): 1.0,
        pair(statement, ids["Ada"]): 1.0,
        pair(statement, ids["Dee"]): 1.0,
    }
