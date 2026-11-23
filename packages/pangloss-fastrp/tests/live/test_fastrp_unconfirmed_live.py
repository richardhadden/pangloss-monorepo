"""A guess no person has confirmed is no evidence, in the graph part (step 10.5c of
implementation_docs/similarity-build-plan.md; the user's answer to row 16), on the backend under test, with
`pangloss_testing.similar_models` declared with `suggested=True` (a participant may be a toolchain's suggestion, and
an `InRole` may hold one).

A factoid of Gus's meeting with Parent is stored; a suggestion naming Ben, Cy and Fay is added to it (as a
participant, or in a role: a `WeightedAlternative` in the suggestion in an `InRole`), every part it had keeping its
id. After one turn of the worker no graph vector stored differs, to 10⁻⁶, from what it was, and each is the oracle's;
once the suggestion is confirmed (an `Identification` of the same id) Ben, Cy and Fay are joined to the factoid. And
what a project sees: built before the hook said anything, `pangloss vectors status` has a rebuild of the graph part
due, by its signature."""

from typing import no_type_check

import numpy as np
import pytest
from pangloss_fastrp import maps
from pangloss_models import hooks
from pangloss_testing.parts import one_turn
from pangloss_testing.parts.writes import (
    confirmed,
    gathering,
    in_role,
    participants_added,
    suggestion,
)
from pangloss_testing.similar_models import declare
from pangloss_vectors.rebuild import rebuild
from pangloss_vectors.status import status

from fastrp_live_support import (
    differences,
    drop_vector_indexes,
    fresh_oracle,
    stored,
    write_shapes,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

NAMED = ("Ben", "Cy", "Fay")


@pytest.fixture
def database(db_driver, clear_database):
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


@no_type_check
async def gathered(m, database) -> dict[str, str]:
    """The shapes, and the factoid of Gus's meeting with Parent (`ids["gathering"]`), written; every part rebuilt and
    the marks worked off"""
    ids = await write_shapes(m, database)
    made = await m.Factoid.Create(label="gathering", statements=[gathering(ids)]).save()
    ids["gathering"] = str(made.id)
    await rebuild()
    await one_turn(database)
    assert differences(await stored(database), await fresh_oracle()) == []
    return ids


def changed(before: dict, after: dict, tolerance: float = 1e-6) -> list[str]:
    """The ids whose vectors differ (or that one of the two has not)"""
    return sorted(
        of
        for of in set(before) | set(after)
        if of not in before
        or of not in after
        or not np.allclose(before[of], after[of], atol=tolerance, rtol=0)
    )


def suggested(ids: dict[str, str], where: str) -> dict:
    """A suggestion of Ben, Cy or Fay, as a participant or in a role"""
    held = suggestion(ids, ("Ben", 50), ("Cy", 30), ("Fay", 20))
    return held if where == "a participant" else in_role("witness", held)


@pytest.mark.parametrize("where", ["a participant", "in a role"])
@no_type_check
async def test_a_suggestion_changes_no_vector_and_once_confirmed_the_people_it_names_are_joined(
    database, where
):
    m = declare(suggested=True)
    ids = await gathered(m, database)
    before = await stored(database)

    await participants_added(m, ids["gathering"], suggested(ids, where))
    assert await one_turn(database) > 0
    after = await stored(database)
    assert changed(before, after) == []
    assert differences(after, await fresh_oracle()) == []

    await confirmed(m, ids["gathering"])
    assert await one_turn(database) > 0
    confirmed_vectors = await stored(database)
    assert differences(confirmed_vectors, await fresh_oracle()) == []
    moved = changed(after, confirmed_vectors)
    for name in NAMED:
        assert ids[name] in moved, name
    assert ids["gathering"] in moved


@no_type_check
async def test_with_the_hook_empty_a_suggestion_would_join_the_people_it_names(
    database, monkeypatch
):
    """(that the test above is not empty: without `hooks.unconfirmed`, as before step 10.5c, the same write moves
    them)"""
    m = declare(suggested=True)
    monkeypatch.setattr(hooks, "unconfirmed", [])
    maps.forget()
    try:
        ids = await gathered(m, database)
        before = await stored(database)
        await participants_added(m, ids["gathering"], suggested(ids, "in a role"))
        assert await one_turn(database) > 0
        moved = changed(before, await stored(database))
        for name in NAMED:
            assert ids[name] in moved, name
    finally:
        maps.forget()


@no_type_check
async def test_built_before_suggestions_ended_the_chains_the_status_has_a_rebuild_of_the_graph_part_due(
    database, monkeypatch
):
    m = declare(suggested=True)
    await write_shapes(m, database)
    with monkeypatch.context() as patched:
        patched.setattr(hooks, "unconfirmed", [])
        maps.forget()
        before = maps.signature()
        await rebuild()
    maps.forget()
    assert maps.signature() != before
    found = await status()
    (graph,) = [p for p in found.parts if p.part == "graph"]
    assert graph.rebuild_due
    assert any(
        reason.startswith("its signature is now ") for reason in graph.reasons
    ), graph.reasons
    assert found.rebuild_due
    await rebuild()
    (graph,) = [p for p in (await status()).parts if p.part == "graph"]
    assert not graph.rebuild_due
