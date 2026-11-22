"""What a part keeps with a generation (`Part.kept`, `store.keep`, `store.kept`; implementation_docs/similarity-build-plan.md,
step 8.3), on the backend under test, with a part made up for the tests: a rebuild stores the text before its switch,
and it is the one in use only after it; a second rebuild replaces it; a part with no `kept` keeps nothing; a rebuild
that stops before its switch leaves the text in use as it was, and its own is dropped by the next"""

from typing import no_type_check

import pytest
from pangloss_testing.live import run
from pangloss_vectors import store
from pangloss_vectors.rebuild import rebuild
from vectors_live_support import declare_events
from vectors_support import SizedPart

pytestmark = pytest.mark.asyncio(loop_scope="session")


class KeepingPart(SizedPart):
    """A part that writes no vector and keeps `text` (as a part whose rebuild found nothing to write would)"""

    def __init__(self, name: str, text: str | None):
        super().__init__(name)
        self.text = text

    def kept(self) -> str | None:
        return self.text


def kept_nodes(db_driver) -> list[tuple[str, int, str]]:
    return [
        (r["part"], r["generation"], r["text"])
        for r in run(
            db_driver,
            "MATCH (k:PGVectorKept) RETURN k.part AS part, k.generation AS generation, k.text AS text "
            "ORDER BY part, generation",
        )
    ]


@pytest.fixture
def keeping(db_driver, clear_database, parts_of_the_test):
    declare_events()
    made = KeepingPart("k", '{"names": 1}')
    parts_of_the_test(made)
    return made


@no_type_check
async def test_a_rebuild_keeps_the_text_with_its_generation_and_it_is_in_use_after_the_switch(
    db_driver, keeping, monkeypatch
):
    switch = store.switch
    seen = {}

    async def look_first(built, combined=()):
        # (kept by now, and not in use yet)
        seen["kept"] = kept_nodes(db_driver)
        seen["in use"] = await store.kept("k")
        await switch(built, combined)

    monkeypatch.setattr(store, "switch", look_first)
    done = await rebuild()

    [made] = done.parts
    assert seen["kept"] == [("k", made.generation, '{"names": 1}')]
    assert seen["in use"] is None
    assert await store.kept("k") == '{"names": 1}'
    assert (await store.states()).parts["k"].generation == made.generation


async def test_a_second_rebuild_replaces_the_text_and_the_older_is_gone(
    db_driver, keeping
):
    await rebuild()
    keeping.text = '{"names": 2}'
    done = await rebuild()

    [made] = done.parts
    assert await store.kept("k") == '{"names": 2}'
    assert kept_nodes(db_driver) == [("k", made.generation, '{"names": 2}')]


async def test_a_part_with_no_kept_or_one_that_gives_none_keeps_nothing(
    db_driver, clear_database, parts_of_the_test
):
    declare_events()
    parts_of_the_test(SizedPart("s"))
    parts_of_the_test(KeepingPart("t", None))
    await rebuild()

    assert kept_nodes(db_driver) == []
    assert await store.kept("s") is None
    assert await store.kept("t") is None


async def test_nothing_is_kept_in_use_before_a_part_is_ever_built(keeping):
    assert await store.kept("k") is None


@no_type_check
async def test_a_rebuild_that_stops_before_its_switch_leaves_the_text_in_use_as_it_was(
    db_driver, keeping, monkeypatch
):
    """(and its generation, at which it kept text and wrote no vector, is not given out again: the next rebuild drops
    what it kept)"""
    first = (await rebuild()).parts[0].generation
    keeping.text = '{"names": 2}'

    async def stopped(built, combined=()):
        raise RuntimeError("stopped before the switch")

    switch = store.switch
    monkeypatch.setattr(store, "switch", stopped)
    with pytest.raises(RuntimeError, match="stopped before the switch"):
        await rebuild()

    assert await store.kept("k") == '{"names": 1}'
    assert (await store.states()).parts["k"].generation == first
    [(_, left, _)] = [node for node in kept_nodes(db_driver) if node[1] != first]
    assert left > first
    assert await store.next_generation() > left

    monkeypatch.setattr(store, "switch", switch)
    keeping.text = '{"names": 3}'
    again = (await rebuild()).parts[0].generation
    assert again > left
    assert await store.kept("k") == '{"names": 3}'
    assert kept_nodes(db_driver) == [("k", again, '{"names": 3}')]
