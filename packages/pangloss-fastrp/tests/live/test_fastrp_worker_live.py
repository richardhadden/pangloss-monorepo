"""The vectors kept current by the worker (implementation_docs/similarity-build-plan.md, steps 5.2 to 5.4), on the
backend under test, with both parts, on `pangloss_testing.similar_models`: after each kind of write, the other workers
(criteria, derived) and **one turn of the vectors' worker**, every graph vector stored is the oracle's (a fresh whole
rebuild, to 10⁻⁵), of exactly the stops the oracle gives one, and the class vectors are exactly those the class part's
rebuild would write (nothing left of what is gone). Past the cap, the vectors written are close to the exact ones and
counted stale, until a rebuild; writes made during a rebuild are all reflected after it and one turn."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, no_type_check

import numpy as np
import pytest
from pangloss_testing.live import run
from pangloss_testing.similar_models import declare
from pangloss_users import current_request_username
from pangloss_vectors import store
from pangloss_vectors.class_part import PART as CLASS_PART
from pangloss_vectors.rebuild import rebuild
from pangloss_vectors.worker import run_pending

from fastrp_live_support import (
    differences,
    drop_vector_indexes,
    fresh_oracle,
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


def ref(id: str, kind: str = "Person") -> dict:
    return {"type": kind, "id": id}


def people(ids: dict[str, str], *names: str) -> dict:
    from types import SimpleNamespace

    return {name: SimpleNamespace(id=ids[name]) for name in names}


OTHER_KINDS = ("criteria", "derive")


def others_pending(db_driver) -> int:
    return run(
        db_driver,
        "MATCH (p:PGPending) WHERE p.kind IN $kinds RETURN count(p) AS n",
        kinds=list(OTHER_KINDS),
    )[0]["n"]


async def the_others_done(db_driver) -> None:
    """The criteria and derived workers run until neither has work (each may leave work for the other)"""
    from pangloss_criteria import run_pending as criteria_pending
    from pangloss_derived.worker import run_pending_derivations

    for _ in range(6):
        await criteria_pending()
        await run_pending_derivations()
        if not others_pending(db_driver):
            return
    raise AssertionError("the criteria and derived workers did not settle")


async def one_turn(db_driver) -> int:
    """The other workers, then one turn of the vectors' worker; nothing of the kind left"""
    await the_others_done(db_driver)
    done = await run_pending()
    assert (
        run(db_driver, "MATCH (p:PGPending {kind: 'vectors'}) RETURN count(p) AS n")[0][
            "n"
        ]
        == 0
    )
    return done


async def class_vectors(db_driver) -> dict[str, list[float]]:
    state = (await store.states()).parts["class"]
    return {
        row["of"]: row["vector"]
        for row in run(
            db_driver,
            "MATCH (v:PGVector {part: 'class', generation: $generation}) RETURN v.of AS of, v.vector AS vector",
            generation=state.generation,
        )
    }


async def class_rebuild() -> dict[str, list[float]]:
    """What the class part's rebuild would write now"""
    rows: dict[str, list[float]] = {}

    async def keep(page) -> None:
        rows.update({row.of: list(row.vector) for row in page})

    await CLASS_PART.rebuild(keep)
    return rows


async def as_a_rebuild(db_driver) -> None:
    """Every graph vector is the oracle's, of the oracle's stops; every class vector is the class part's"""
    assert differences(await stored(db_driver), await fresh_oracle()) == []
    have, want = await class_vectors(db_driver), await class_rebuild()
    assert sorted(set(have) - set(want)) == [], "class vectors of what has none"
    assert sorted(set(want) - set(have)) == [], "class vectors missing"
    assert all(np.allclose(have[of], want[of]) for of in want)


async def built(m, db_driver, **saved) -> dict[str, str]:
    """The shapes written, both parts rebuilt, and the marks of the writes worked off (so the test starts equal)"""
    ids = await write_shapes(m, db_driver, **saved)
    await rebuild()
    await one_turn(db_driver)
    await as_a_rebuild(db_driver)
    return ids


# ---------------------------------------------------------------------------
# After each kind of write
# ---------------------------------------------------------------------------


@no_type_check
async def create(m, ids) -> None:
    await m.Factoid.Create(
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


@no_type_check
async def update_that_adds_a_reference(m, ids) -> None:
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


@no_type_check
async def update_that_drops_a_reference(m, ids) -> None:
    """The meeting without Eve (and so without the `Sworn` that held her), nor the place"""
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
async def update_that_replaces_its_statements(m, ids) -> None:
    """Fay's parent written again as a transfer: its old statement gone (and the siblings derived from it), a new
    one"""
    await m.Factoid.Update(
        id=ids["Fay's parent"],
        label="Fay's parent",
        statements=[
            {
                "type": "Transfer",
                "label": "Fay gave to Gus",
                "given_by": ref(ids["Fay"]),
                "given_to": ref(ids["Gus"]),
            }
        ],
    ).save()


@no_type_check
async def delete(m, ids) -> None:
    await m.Factoid.delete(ids["meeting"])


@no_type_check
async def new_citation(m, ids) -> None:
    await m.Factoid.Create(
        label="another inference",
        statements=[
            {
                "type": "Inference",
                "label": "So Ada knew Dee",
                "evidence": [{"type": "Activity", "id": ids["activity"]}],
            }
        ],
    ).save()


@no_type_check
async def criteria_change_candidates(m, ids) -> None:
    """Ben joins the guild: the description of a member in "member gift" has him as a candidate more (the criteria
    worker writes it, `set_computed`)"""
    await m.Factoid.Create(
        label="Ben joins",
        statements=[
            {
                "type": "MemberOf",
                "label": "Ben of the guild",
                "member": ref(ids["Ben"]),
                "group": ref(ids["group"], "Group"),
            }
        ],
    ).save()


WRITES: dict[str, Callable[[Any, dict[str, str]], Awaitable[None]]] = {
    "a create": create,
    "an update that adds a reference": update_that_adds_a_reference,
    "an update that drops a reference": update_that_drops_a_reference,
    "an update that replaces its statements": update_that_replaces_its_statements,
    "a delete": delete,
    "a new citation": new_citation,
    "a criteria evaluation that changes candidates": criteria_change_candidates,
}


@pytest.mark.parametrize("write", list(WRITES))
@no_type_check
async def test_after_a_write_and_one_turn_the_vectors_are_those_of_a_rebuild(
    database, write
):
    m = declare()
    ids = await built(m, database)
    await WRITES[write](m, ids)
    assert await one_turn(database) > 0
    await as_a_rebuild(database)


@no_type_check
async def test_after_an_update_that_replaces_its_statements_the_old_ones_have_no_vector_left(
    database,
):
    m = declare()
    ids = await built(m, database)
    await update_that_replaces_its_statements(m, ids)
    await one_turn(database)
    left = run(
        database,
        "MATCH (v) WHERE (v:PGVector OR v:PGProfileVector) AND v.of = $of RETURN count(v) AS n",
        of=ids["Fay child"],
    )
    assert left == [{"n": 0}]


@no_type_check
async def test_the_criteria_worker_s_new_candidate_is_joined_after_one_turn(database):
    """(the case above, looked at: Ben is a candidate now, and the member transfer is joined to him)"""
    from pangloss_fastrp import maps, maths
    from pangloss_fastrp.cypher_reader import reading

    m = declare()
    ids = await built(m, database)
    graph = maps.graph_maps()

    async def joined() -> set[str]:
        found = await reading(
            graph, lambda reader: maths.joins(reader, graph, [ids["member transfer"]])
        )
        return {i for key in found for i in key}

    assert ids["Ben"] not in await joined()
    await criteria_change_candidates(m, ids)
    await one_turn(database)
    assert ids["Ben"] in await joined()
    await as_a_rebuild(database)


@no_type_check
async def test_after_a_delete_and_its_undelete(database):
    m = declare()
    ids = await built(m, database)
    await m.Factoid.delete(ids["meeting"])
    await one_turn(database)
    await as_a_rebuild(database)
    assert ids["activity"] not in await class_vectors(database)
    await m.Factoid.undelete(ids["meeting"])
    await one_turn(database)
    await as_a_rebuild(database)
    assert ids["activity"] in await class_vectors(database)


@no_type_check
async def test_after_a_merge_and_its_undo(database):
    m = declare()
    ids = await built(m, database)
    merged = await m.Person.merge(absorb=ids["Eve"], into=ids["Dee"])
    await one_turn(database)
    await as_a_rebuild(database)
    assert ids["Eve"] not in await stored(database)
    assert ids["Eve"] not in await class_vectors(database)
    await m.Person.unmerge(merged.merge.id)
    await one_turn(database)
    await as_a_rebuild(database)
    assert ids["Eve"] in await stored(database)


@no_type_check
async def test_after_a_publish_and_an_unpublish(database, graph_sees):
    """Under `VECTORS_GRAPH_SEES = "everyone"`, a document is in the graph while it is published"""
    pytest.importorskip("pangloss_review")
    from pangloss_review.service import set_status
    from pangloss_review.status import ReviewStatus

    graph_sees("everyone")
    m = declare(reviewed=True)
    ids = await built(m, database, published=True)
    secret = await m.Factoid.Create(
        label="secret", statements=[transfer(people(ids, "Ada", "Ben", "Cy"))]
    ).save()
    await one_turn(database)
    await as_a_rebuild(database)
    assert str(secret.id) not in await stored(database)
    user = current_request_username.get()
    await set_status(secret.id, ReviewStatus.PUBLISHED, user)
    await one_turn(database)
    await as_a_rebuild(database)
    assert str(secret.id) in await stored(database)
    await set_status(secret.id, ReviewStatus.UNCHECKED, user)
    await one_turn(database)
    await as_a_rebuild(database)
    assert str(secret.id) not in await stored(database)


# ---------------------------------------------------------------------------
# Past the cap (5.3)
# ---------------------------------------------------------------------------


def cosine(a, b) -> float:
    a, b = np.asarray(a), np.asarray(b)
    return float(a @ b / np.linalg.norm(a) / np.linalg.norm(b))


@no_type_check
async def test_past_the_cap_a_hub_s_new_document_has_a_close_vector_counted_stale_until_a_rebuild(
    database, settings, monkeypatch
):
    """A person in sixty transfers (a hub), and a cap of 50: the factoid saved with a transfer from the hub has a
    graph vector of cosine 0.9 or more with the exact one, and so has its statement; `stale` counts them; a rebuild
    brings equality, and 0"""
    m = declare()
    hub = await m.Person.Create(label="Hub").save()
    others = [await m.Person.Create(label=f"Other {n}").save() for n in range(20)]
    for n in range(60):
        await m.Factoid.Create(
            label=f"gift {n}",
            statements=[
                {
                    "type": "Transfer",
                    "label": f"Hub gave to {n % 20}",
                    "given_by": ref(str(hub.id)),
                    "given_to": ref(str(others[n % 20].id)),
                }
            ],
        ).save()
    await rebuild()
    await one_turn(database)
    monkeypatch.setattr(settings, "FASTRP_REFRESH_CAP", 50)
    new = await m.Factoid.Create(
        label="one more gift",
        statements=[
            {
                "type": "Transfer",
                "label": "Hub gave to Other 3",
                "given_by": ref(str(hub.id)),
                "given_to": ref(str(others[3].id)),
            }
        ],
    ).save()
    statement = str((await m.Factoid.get(new.id)).statements[0].id)
    await one_turn(database)
    have, exact = await stored(database), await fresh_oracle()
    for stop in (str(new.id), statement):
        assert stop in have
        assert cosine(have[stop], exact[stop]) >= 0.9, stop
    assert (await store.states()).parts["graph"].stale == 2
    # (the class part is exact whatever the cap)
    assert set(await class_vectors(database)) == set(await class_rebuild())
    await rebuild()
    assert (await store.states()).parts["graph"].stale == 0
    await as_a_rebuild(database)


# ---------------------------------------------------------------------------
# Writes during a rebuild (5.4)
# ---------------------------------------------------------------------------


@no_type_check
async def test_writes_made_during_a_slowed_rebuild_are_all_reflected_after_it_and_one_turn(
    database, monkeypatch
):
    from pangloss_fastrp.part import PART as GRAPH_PART

    m = declare()
    ids = await built(m, database)
    reading_done, go = asyncio.Event(), asyncio.Event()
    rebuild_graph = type(GRAPH_PART).rebuild

    async def slowed(self, write) -> int:
        # (the graph read whole, then held: everything written meanwhile is after what it read)
        from pangloss_fastrp import maps, maths
        from pangloss_fastrp.cypher_reader import load_all
        from pangloss_fastrp.part import _write
        from pangloss_vectors import VectorRow

        graph = maps.graph_maps()
        reader = await load_all(graph)
        reading_done.set()
        await go.wait()
        vectors = maths.rebuild(reader, graph)
        rows = [
            VectorRow(of=i, type=reader.node[i].type, vector=[float(x) for x in v])
            for i, v in sorted(vectors.items())
        ]
        await _write(write, rows)
        return len(rows)

    monkeypatch.setattr(type(GRAPH_PART), "rebuild", slowed)
    rebuilding = asyncio.create_task(rebuild())
    await asyncio.wait_for(reading_done.wait(), 30)
    for write in (create, new_citation, update_that_replaces_its_statements):
        await write(m, ids)
    await m.Person.merge(absorb=ids["Eve"], into=ids["Dee"])
    await m.Factoid.delete(ids["no gift"])
    # (the worker does nothing while the rebuild runs)
    await the_others_done(database)
    assert await run_pending() == 0
    go.set()
    await asyncio.wait_for(rebuilding, 60)
    monkeypatch.setattr(type(GRAPH_PART), "rebuild", rebuild_graph)
    assert await one_turn(database) > 0
    await as_a_rebuild(database)
