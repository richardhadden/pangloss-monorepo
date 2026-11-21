"""Rebuild and status on the backend under test (implementation_docs/similarity-build-plan.md, step 2.5): a rebuild
writes a new generation of each part and of the profiles that weigh it, switches to them and drops the old ones,
under a lease that refuses a second; status says when a rebuild is due, and why; the states' counts follow the
changes made in place. (The commands are in `test_vectors_commands_live.py`)"""

import asyncio
from typing import no_type_check

import pangloss_core.settings as core_settings
import pytest
from pangloss_admin.kinds import job_kinds
from pangloss_admin.runner import run_job
from pangloss_admin.store import JobStore
from pangloss_testing.backends import under_test
from pangloss_testing.live import run
from pangloss_vectors import VectorRow, VectorsRebuildBusy, nearest, store
from pangloss_vectors.class_part import PART
from pangloss_vectors.rebuild import rebuild
from pangloss_vectors.status import status
from vectors_live_support import (
    EVENTS,
    build,
    declare_events,
    drop_vector_indexes,
    make_vector_indexes,
    saved_events,
)
from vectors_support import SizedPart

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def class_part(db_driver, clear_database, parts_of_the_test):
    """The class part alone (the default profile is it, at its weight)"""
    parts_of_the_test(PART)
    drop_vector_indexes(db_driver)
    yield PART
    drop_vector_indexes(db_driver)


@pytest.fixture
def settings_changed(monkeypatch):
    """Change a setting of the test settings for the test alone"""

    def change(name: str, value) -> None:
        monkeypatch.setattr(core_settings.SETTINGS, name, value)

    return change


class WaitingPart(SizedPart):
    """A part whose rebuild writes the rows it is given, half of them, then waits for `go` (once `waiting` is set)
    before it writes the rest"""

    def __init__(self, name: str, dimension: int = 3):
        super().__init__(name, dimension)
        self.rows: list[VectorRow] = []
        self.waiting = asyncio.Event()
        self.go: asyncio.Event | None = None

    async def rebuild(self, write) -> int:
        half = len(self.rows) // 2
        await write(self.rows[:half])
        if self.go is not None:
            self.waiting.set()
            await self.go.wait()
        await write(self.rows[half:])
        return len(self.rows)


def counted(db_driver, label: str) -> int:
    return run(db_driver, f"MATCH (n:{label}) RETURN count(n) AS n")[0]["n"]


def generations(db_driver, label: str) -> list[int]:
    rows = run(
        db_driver,
        f"MATCH (n:{label}) RETURN DISTINCT n.generation AS g ORDER BY g",
    )
    return [r["g"] for r in rows]


# ---------------------------------------------------------------------------
# A rebuild
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_rebuild_builds_the_class_part_and_its_profile_and_switches_to_them(
    db_driver, class_part
):
    m = declare_events()
    made = await saved_events(m, **EVENTS)

    done = await rebuild()

    [part_done] = done.parts
    [profile_done] = done.profiles
    assert (part_done.part, part_done.count) == ("class", 7)
    assert (profile_done.profile, profile_done.count) == ("default", 7)
    assert profile_done.why == "with the class part"
    assert part_done.seconds >= 0 and done.seconds >= part_done.seconds
    assert done.skipped == {}
    found = await store.states()
    assert found.parts["class"].generation == part_done.generation
    assert found.parts["class"].count == 7
    assert found.parts["class"].signature == PART.signature()
    assert found.parts["class"].graph_sees == "everyone"
    assert found.profiles["default"].generation == profile_done.generation
    assert found.profiles["default"].weights == {"class": 0.1}

    await make_vector_indexes()
    near = await nearest(made["painting 1"], k=3)
    assert near.status == "ok"
    assert {hit.id for hit in near.hits[:2]} == {made["painting 2"], made["painting 3"]}
    assert near.hits[2].id == made["artwork"]


@no_type_check
async def test_after_a_rebuild_the_old_generations_are_gone(db_driver, class_part):
    m = declare_events()
    await saved_events(m, **EVENTS)
    first = await rebuild()
    # (a generation a rebuild that stopped part way left, below the next)
    await store.write_generation(
        "class",
        first.parts[0].generation - 1,
        [VectorRow("stray", "Birth", PART.vector("Birth"))],
    )

    second = await rebuild()

    assert second.parts[0].generation > first.profiles[0].generation
    assert second.parts[0].dropped == 8
    assert second.profiles[0].dropped == 7
    assert generations(db_driver, "PGVector") == [second.parts[0].generation]
    assert generations(db_driver, "PGProfileVector") == [second.profiles[0].generation]
    assert counted(db_driver, "PGVector") == counted(db_driver, "PGProfileVector") == 7


@no_type_check
async def test_a_second_rebuild_at_once_is_refused_and_names_what_holds_it(
    db_driver, clear_database, parts_of_the_test
):
    declare_events()
    waiting = WaitingPart("w")
    parts_of_the_test(waiting)
    waiting.rows = [VectorRow(f"i{n}", "Birth", [1, n, 0]) for n in range(4)]
    waiting.go = asyncio.Event()

    first = asyncio.create_task(rebuild())
    await asyncio.wait_for(waiting.waiting.wait(), 10)
    try:
        with pytest.raises(
            VectorsRebuildBusy,
            match=r"Another rebuild of the vectors is running on this database: process \d+ on .*, since ",
        ):
            await rebuild()
    finally:
        waiting.go.set()
        done = await first
    assert done.parts[0].count == 4
    # (and once it is over, the next may run)
    waiting.go = None
    assert (await rebuild()).parts[0].count == 4


@no_type_check
async def test_a_search_during_a_rebuild_sees_the_old_generation_whole(
    db_driver, clear_database, parts_of_the_test
):
    m = declare_events()
    waiting = WaitingPart("w")
    parts_of_the_test(waiting)
    made = await saved_events(m, Birth=["q", "a", "b", "c"])
    old = {"q": [1, 0, 0], "a": [1, 0.1, 0], "b": [1, 0.5, 0], "c": [0, 1, 0]}
    # (the other way round, in the new one)
    new = {"q": [1, 0, 0], "a": [0, 1, 0], "b": [1, 0.5, 0], "c": [1, 0.1, 0]}
    waiting.rows = [VectorRow(made[k], "Birth", v) for k, v in old.items()]
    drop_vector_indexes(db_driver)
    await rebuild()
    await make_vector_indexes()
    before = await nearest(made["q"], k=3)
    assert [hit.id for hit in before.hits] == [made["a"], made["b"], made["c"]]

    waiting.rows = [VectorRow(made[k], "Birth", v) for k, v in new.items()]
    waiting.go = asyncio.Event()
    task = asyncio.create_task(rebuild())
    try:
        await asyncio.wait_for(waiting.waiting.wait(), 10)
        # (half the new generation is written: the search reads the old one, all of it, as it was)
        during = await nearest(made["q"], k=3)
        assert during == before
    finally:
        waiting.go.set()
        await task
    after = await nearest(made["q"], k=3)
    assert [hit.id for hit in after.hits] == [made["c"], made["b"], made["a"]]
    drop_vector_indexes(db_driver)


@no_type_check
async def test_a_part_the_backend_cannot_build_is_skipped_and_said(
    db_driver, clear_database, parts_of_the_test
):
    declare_events()
    needs = SizedPart("m")
    needs.requires = frozenset({"query_modules"})
    parts_of_the_test(needs)

    done = await rebuild()

    if under_test().name == "memgraph":
        assert [p.part for p in done.parts] == ["m"] and done.skipped == {}
    else:
        assert done.parts == []
        assert done.skipped == {
            "part m": "it needs query_modules, which the backend 'neo4j' does not have"
        }
        [state] = (await status()).parts
        assert state.unavailable is not None and not state.rebuild_due


async def test_a_part_that_is_not_registered_is_refused_by_name(class_part):
    from pangloss_models.exceptions import PanglossInitialisationError

    with pytest.raises(PanglossInitialisationError, match="no part named 'nope'"):
        await rebuild("nope")


# ---------------------------------------------------------------------------
# Status: when a rebuild is due
# ---------------------------------------------------------------------------


@no_type_check
async def test_nothing_built_is_a_rebuild_due_of_everything(class_part):
    declare_events()

    found = await status()

    assert found.rebuild_due
    [part_status] = found.parts
    assert part_status.generation is None
    assert part_status.reasons == ("it has never been built",)
    [profile_status] = found.profiles
    assert profile_status.reasons[0] == "it has never been built"


@no_type_check
async def test_a_changed_class_decay_says_a_rebuild_is_due_and_a_rebuild_clears_it(
    class_part, settings_changed
):
    m = declare_events()
    await saved_events(m, **EVENTS)
    await rebuild()
    assert not (await status()).rebuild_due

    settings_changed("VECTORS_CLASS_DECAY", 0.3)
    found = await status()

    assert found.rebuild_due
    [part_status] = found.parts
    assert len(part_status.reasons) == 1
    assert part_status.reasons[0].startswith(f"its signature is now {PART.signature()}")
    assert "a setting it depends on changed" in part_status.reasons[0]
    [profile_status] = found.profiles
    assert profile_status.reasons == ("the class part it weighs has to be rebuilt",)

    await rebuild()
    assert not (await status()).rebuild_due


@no_type_check
async def test_a_changed_graph_sees_says_a_rebuild_is_due(class_part, settings_changed):
    m = declare_events()
    await saved_events(m, **EVENTS)
    await rebuild()

    settings_changed("VECTORS_GRAPH_SEES", "logged_in")
    [part_status] = (await status()).parts

    assert part_status.reasons == (
        "VECTORS_GRAPH_SEES is now 'logged_in', not the 'everyone' it was built with",
    )


@no_type_check
async def test_a_changed_profile_weight_says_a_rebuild_is_due_and_a_rebuild_of_another_part_recombines_it(
    db_driver, clear_database, parts_of_the_test, settings_changed
):
    m = declare_events()
    await saved_events(m, **EVENTS)
    parts_of_the_test(PART)
    parts_of_the_test(SizedPart("a"))
    settings_changed(
        "VECTORS_PROFILES", {"default": {"class": 0.1, "a": 1}, "classes": {"class": 1}}
    )
    await rebuild()
    assert not (await status()).rebuild_due

    settings_changed(
        "VECTORS_PROFILES", {"default": {"class": 0.1, "a": 1}, "classes": {"class": 2}}
    )
    found = await status()
    assert [p.part for p in found.parts if p.rebuild_due] == []
    assert found.profile("classes").reasons == (
        "its weights are now class 2, not the class 1 it was built with",
    )
    assert not found.profile("default").rebuild_due

    # (a rebuild of the other part: `classes` weighs only the class part, and is combined again alone)
    done = await rebuild("a")

    assert [p.part for p in done.parts] == ["a"]
    assert {p.profile: p.why for p in done.profiles} == {
        "default": "with the a part",
        "classes": "its weights changed",
    }
    assert {p.profile: p.count for p in done.profiles} == {"default": 7, "classes": 7}
    assert not (await status()).rebuild_due


@no_type_check
async def test_a_profile_is_not_recombined_alone_from_a_part_that_is_itself_due(
    class_part, parts_of_the_test, settings_changed
):
    m = declare_events()
    await saved_events(m, **EVENTS)
    parts_of_the_test(SizedPart("a"))
    settings_changed("VECTORS_PROFILES", {"default": {"a": 1}, "classes": {"class": 1}})
    await rebuild()
    settings_changed("VECTORS_PROFILES", {"default": {"a": 1}, "classes": {"class": 2}})
    settings_changed("VECTORS_CLASS_DECAY", 0.3)

    done = await rebuild("a")

    assert [p.profile for p in done.profiles] == ["default"]
    assert done.skipped == {
        "profile classes": "its weights changed, but the class part it weighs has to be rebuilt first "
        "(pangloss vectors rebuild --part class)"
    }


# ---------------------------------------------------------------------------
# The counts
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_count_follows_set_vectors_and_delete_for(
    db_driver, clear_database, parts_of_the_test
):
    declare_events()
    parts_of_the_test(SizedPart("a"))
    await build("a", [VectorRow(f"i{n}", "Birth", [1, n, 0]) for n in range(3)])

    def counts(found):
        return (
            found.parts["a"].count,
            found.profiles["default"].count,
            found.profiles["default"].removed,
        )

    assert counts(await store.states()) == (3, 3, 0)
    # (one new, one already there)
    await store.set_vectors(
        "a", [VectorRow("i9", "Birth", [0, 1, 0]), VectorRow("i0", "Birth", [0, 0, 1])]
    )
    assert counts(await store.states()) == (4, 4, 0)
    await store.delete_for(["i1", "i9", "not there"])
    assert counts(await store.states()) == (2, 2, 2)
    assert counted(db_driver, "PGVector") == 2
    # (a rebuild counts again, and nothing is removed from what it built)
    await build("a", [VectorRow(f"i{n}", "Birth", [1, n, 0]) for n in range(5)])
    assert counts(await store.states()) == (5, 5, 0)


# ---------------------------------------------------------------------------
# The admin job
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_admin_job_rebuilds_and_says_its_counts(
    db_driver, class_part, tmp_path
):
    m = declare_events()
    await saved_events(m, **EVENTS)
    kinds = job_kinds(["pangloss_vectors"])
    assert list(kinds) == ["vectors_rebuild"]
    assert kinds["vectors_rebuild"].checked_options({}) == {"part": "all"}
    with pytest.raises(ValueError, match="part must be one of all, class"):
        kinds["vectors_rebuild"].checked_options({"part": "nope"})

    jobs = JobStore(tmp_path / "jobs")
    job = jobs.create("vectors_rebuild", {"part": "class"}, "me")
    await run_job(jobs, job["id"], kinds)

    done = jobs.read(job["id"])
    assert done is not None
    assert done["state"] == "finished", done["error"]
    assert done["counts"] == {"part class": 7, "profile default": 7}
    assert (await store.states()).parts["class"].count == 7
