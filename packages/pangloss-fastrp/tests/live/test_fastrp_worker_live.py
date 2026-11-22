"""The vectors kept current by the worker (implementation_docs/similarity-build-plan.md, steps 5.2 to 5.4), on the
backend under test, with both parts, on `pangloss_testing.similar_models`.

The suite every part passes (`pangloss_testing.parts.PartSuite`, step 8.4) is called for the graph part, with the
class part checked beside it: after each kind of write, the other workers (criteria, derived) and **one turn of the
vectors' worker**, every graph vector stored is the oracle's (a fresh whole rebuild, to 10⁻⁵), of exactly the stops
the oracle gives one, and the class vectors are those the class part's rebuild would write (nothing left of what is
gone); the same after a delete and its undelete, a merge and its undo, a publish and an unpublish under both values of
`VECTORS_GRAPH_SEES`; an overlay is the payload written; writes made during a rebuild are all reflected after it and
one turn. What is the graph part's alone is here: the criteria worker's new candidate joined; a batch past the cap is
refreshed in groups, exactly; past the cap alone, the vectors written are close to the exact ones and counted stale,
until a rebuild."""

from typing import no_type_check

import numpy as np
import pytest
from pangloss_testing.live import run
from pangloss_testing.parts import PartSuite, one_turn
from pangloss_testing.parts.writes import (
    criteria_change_candidates,
    update_that_drops_a_reference,
)
from pangloss_testing.similar_models import declare
from pangloss_vectors import store
from pangloss_vectors.class_part import PART as CLASS_PART
from pangloss_vectors.rebuild import rebuild
from pangloss_vectors.settings import graph_sees

from fastrp_live_support import (
    differences,
    drop_vector_indexes,
    fresh_oracle,
    stored,
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
# The suite of the parts, for the graph part and the class part beside it
# ---------------------------------------------------------------------------


class TestTheGraphPartAndTheClassPartBesideIt(PartSuite):
    """(the graph part's slow way is the oracle; the class part's, its own rebuild, to `np.allclose`'s tolerance)"""

    parts = {
        "graph": lambda db_driver: fresh_oracle(),
        "class": lambda db_driver: class_rebuild(),
    }
    tolerances = {"class": 1e-8}

    async def also(self, step, m, ids, database) -> None:
        """What the graph part's tests asserted before the suite, which does not hold for every part: the activity has
        a class vector again once undeleted, and Eve a graph vector once the merge is undone; the secret factoid is in
        the graph while it is published, or always if the graph sees what the logged-in see"""
        if step == "undeleted":
            assert ids["activity"] in await class_vectors(database)
        elif step == "unmerged":
            assert ids["Eve"] in await stored(database)
        elif step in ("saved unpublished", "published", "unpublished"):
            seen = step == "published" or graph_sees() == "logged_in"
            assert (ids["secret"] in await stored(database)) is seen


# ---------------------------------------------------------------------------
# The graph part's own
# ---------------------------------------------------------------------------


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


# (the batch of the last test below reaches 35 stops whole, and its groups at most 30 after three halvings: measured
# 2026-11-21 on the shapes of `write_shapes`; the test asserts that the cap still splits it)
CAP_THAT_SPLITS = 30


def gift(by: str, to: str, label: str) -> dict:
    return {
        "type": "Transfer",
        "label": label,
        "given_by": ref(by),
        "given_to": ref(to),
    }


@no_type_check
async def test_a_batch_past_the_cap_is_refreshed_in_groups_and_only_what_is_past_it_alone_is_approximate(
    database, settings, monkeypatch
):
    """A cap of 50 and a hub (a person in sixty transfers, past it alone); one turn after twelve factoids, one with a
    transfer from the hub and eleven each between two people of their own (four stops each, 44 together): the
    eleven's stops and the people they name have the vectors a rebuild gives, the hub's factoid and its statement
    are approximate, and the part's state counts those two stale, not the batch"""
    m = declare()
    hub = await m.Person.Create(label="Hub").save()
    others = [await m.Person.Create(label=f"Other {n}").save() for n in range(20)]
    for n in range(60):
        await m.Factoid.Create(
            label=f"gift {n}",
            statements=[gift(str(hub.id), str(others[n % 20].id), f"Hub gave to {n}")],
        ).save()
    pairs = [
        (
            await m.Person.Create(label=f"Giver {n}").save(),
            await m.Person.Create(label=f"Taker {n}").save(),
        )
        for n in range(11)
    ]
    await rebuild()
    await one_turn(database)
    monkeypatch.setattr(settings, "FASTRP_REFRESH_CAP", 50)
    near = await m.Factoid.Create(
        label="one more gift",
        statements=[gift(str(hub.id), str(others[3].id), "Hub gave to Other 3")],
    ).save()
    far = [
        await m.Factoid.Create(
            label=f"far gift {n}",
            statements=[gift(str(a.id), str(b.id), f"Giver {n} gave to Taker {n}")],
        ).save()
        for n, (a, b) in enumerate(pairs)
    ]
    assert await one_turn(database) == 12
    have, exact = await stored(database), await fresh_oracle()
    eleven = {str(a.id) for a, _ in pairs} | {str(b.id) for _, b in pairs}
    for made in far:
        eleven |= {str(made.id), str((await m.Factoid.get(made.id)).statements[0].id)}
    assert len(eleven) == 44
    assert (
        differences(
            {i: have[i] for i in eleven if i in have}, {i: exact[i] for i in eleven}
        )
        == []
    )
    statement = str((await m.Factoid.get(near.id)).statements[0].id)
    for stop in (str(near.id), statement):
        assert stop in have
        assert cosine(have[stop], exact[stop]) >= 0.9, stop
    assert (await store.states()).parts["graph"].stale == 2


@no_type_check
async def test_a_batch_with_a_head_removed_and_a_reference_dropped_refreshed_in_groups_equals_a_rebuild(
    database, settings, monkeypatch
):
    """A delete and an update that drops a reference in one turn, under a cap that the whole batch passes and no unit
    of it does alone: it is refreshed in groups, and nothing is stale"""
    from pangloss_fastrp import maths

    m = declare()
    ids = await built(m, database)
    monkeypatch.setattr(settings, "FASTRP_REFRESH_CAP", CAP_THAT_SPLITS)
    refresh = maths.refresh
    tried: list[bool] = []

    def counted(*args, **kwargs):
        try:
            made = refresh(*args, **kwargs)
        except maths.TooLarge:
            tried.append(False)
            raise
        tried.append(True)
        return made

    monkeypatch.setattr(maths, "refresh", counted)
    await m.Factoid.delete(ids["no gift"])
    await update_that_drops_a_reference(m, ids)
    assert await one_turn(database) == 2
    # (the whole batch was too large, and every unit of it fitted at last)
    assert tried[0] is False and True in tried, tried
    assert (await store.states()).parts["graph"].stale == 0
    await as_a_rebuild(database)
