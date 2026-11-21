"""The worker that keeps the vectors current (implementation_docs/similarity-build-plan.md, step 5.2), on the backend
under test, with parts that compute nothing: what each part is told of a batch; a failing part gives the claims back
and the next turn succeeds; two workers do not do a batch twice; a part never built is skipped; what is gone loses its
vectors of every part; nothing is claimed while a rebuild holds its lease, and a rebuild waits for the batch in hand;
stale vectors are counted, and past `VECTORS_REBUILD_AFTER` a rebuild is started. (What marks is in
`test_vectors_marks_live.py`; the vectors kept equal to a rebuild, after every kind of write, in `pangloss-fastrp`'s
`test_fastrp_worker_live.py`)"""

import asyncio
from typing import no_type_check

import pangloss_core.settings as core_settings
import pytest
from pangloss_testing.live import run
from pangloss_vectors import Changed, Refreshed, VectorRow, store
from pangloss_vectors.class_part import PART as CLASS_PART
from pangloss_vectors.rebuild import rebuild
from pangloss_vectors.worker import Settings, Worker, run_pending
from vectors_live_support import build, declare_events, saved_events
from vectors_support import SizedPart

pytestmark = pytest.mark.asyncio(loop_scope="session")


class TellingPart(SizedPart):
    """A part that writes `[1, 0, 0]` for each head written, and keeps what it was told; `fail` times it raises
    first; `stale` it says of each batch; `pause`: it waits for this before it writes"""

    def __init__(self, name: str = "fake"):
        super().__init__(name)
        self.told: list[Changed] = []
        self.fail = 0
        self.stale = 0
        self.pause: asyncio.Event | None = None
        self.working = asyncio.Event()

    async def rebuild(self, write) -> int:
        self.rebuilt = True
        return 0

    async def refresh(self, changed: Changed, write) -> Refreshed:
        self.told.append(changed)
        self.working.set()
        if self.pause is not None:
            await self.pause.wait()
        if self.fail:
            self.fail -= 1
            raise RuntimeError("the part failed")
        rows = [
            VectorRow(item.id, item.type, [1.0, 0.0, 0.0]) for item in changed.written
        ]
        await write(rows)
        return Refreshed(written=len(rows), stale=self.stale)


@pytest.fixture
def telling(db_driver, clear_database, parts_of_the_test):
    """The models of events, and a part that keeps what it is told, alone (the default profile is it)"""
    made = TellingPart()
    parts_of_the_test(made)
    return made


def marks(db_driver) -> list[dict]:
    return run(
        db_driver,
        "MATCH (p:PGPending {kind: 'vectors'}) RETURN p.head_id AS head, p.claim AS claim ORDER BY head",
    )


def vectors_of(db_driver, of: str) -> list[str]:
    """The labels of what is stored for the item: `PGVector part` and `PGProfileVector profile`"""
    rows = run(
        db_driver,
        "MATCH (v {of: $of}) RETURN labels(v) AS labels, v.part AS part, v.profile AS profile",
        of=of,
    )
    return sorted(
        f"{'part ' + r['part'] if r['part'] else 'profile ' + r['profile']}"
        for r in rows
    )


async def built_with_items(part) -> tuple:
    """The events declared and saved, the part built with nothing, and the marks of the saves still there"""
    m = declare_events()
    ids = await saved_events(m, Person=["Anna"], Birth=["birth"])
    await build(part.name, [])
    return m, ids


@no_type_check
async def test_a_batch_tells_each_part_what_was_written_and_what_removed_and_completes_the_marks(
    telling, db_driver
):
    m, ids = await built_with_items(telling)
    await m.Birth.delete(ids["birth"])
    assert await run_pending() == 2
    assert marks(db_driver) == []
    (changed,) = telling.told
    assert [item.id for item in changed.written] == [ids["Anna"]]
    assert changed.removed == (ids["birth"],)
    assert vectors_of(db_driver, ids["Anna"]) == ["part fake", "profile default"]
    # (written again: told again; nothing pending, nothing told)
    assert await run_pending() == 0
    assert len(telling.told) == 1


@no_type_check
async def test_a_failing_part_gives_the_claims_back_and_the_next_turn_succeeds(
    telling, db_driver
):
    m, ids = await built_with_items(telling)
    telling.fail = 1
    with pytest.raises(RuntimeError, match="the part failed"):
        await run_pending()
    left = marks(db_driver)
    assert sorted(r["head"] for r in left) == sorted(ids.values())
    assert all(r["claim"] is None for r in left)
    assert await run_pending() == 2
    assert marks(db_driver) == []
    assert vectors_of(db_driver, ids["Anna"]) == ["part fake", "profile default"]


@no_type_check
async def test_two_workers_do_not_do_a_batch_twice(telling, db_driver):
    m = declare_events()
    await build(telling.name, [])
    ids = await saved_events(m, Person=["A", "B", "C", "D", "E", "F"])
    first, second = Worker(Settings(batch=1)), Worker(Settings(batch=1))
    assert await first.take_lease()
    # (the lease: only one works)
    assert not await second.take_lease()
    await first.give_up_lease()
    # (and the claims: two at once claim none twice)
    done = await asyncio.gather(first.drain(), second.drain())
    told = [item.id for changed in telling.told for item in changed.written]
    assert sorted(told) == sorted(ids.values())
    assert sum(done) == len(ids)


@no_type_check
async def test_a_part_never_built_is_skipped_and_the_marks_completed(
    db_driver, clear_database, parts_of_the_test, monkeypatch
):
    built, never = TellingPart("built"), TellingPart("never")
    parts_of_the_test(built)
    parts_of_the_test(never)
    m = declare_events()
    ids = await saved_events(m, Person=["Anna"])
    # (a profile of the built part alone: one that weighs a part never built is not built either)
    monkeypatch.setattr(
        core_settings.SETTINGS, "VECTORS_PROFILES", {"default": {"built": 1}}
    )
    await build("built", [])
    worker = Worker()
    await worker.drain()
    assert len(built.told) == 1 and never.told == []
    assert worker.stats.skipped == {"never": "it has never been built"}
    assert marks(db_driver) == []
    assert ids


@no_type_check
async def test_what_is_gone_loses_its_vectors_of_every_part(
    db_driver, clear_database, parts_of_the_test
):
    """A deleted head's class vector and the other part's go, and those of the profile"""
    other = TellingPart()
    parts_of_the_test(CLASS_PART)
    parts_of_the_test(other)
    m = declare_events()
    ids = await saved_events(m, Person=["Anna", "Bernard"])
    await rebuild()
    await run_pending()
    assert vectors_of(db_driver, ids["Anna"]) == [
        "part class",
        "part fake",
        "profile default",
    ]
    await m.Person.delete(ids["Anna"])
    await run_pending()
    assert vectors_of(db_driver, ids["Anna"]) == []
    assert vectors_of(db_driver, ids["Bernard"]) == [
        "part class",
        "part fake",
        "profile default",
    ]
    # (and brought back: the parts write it again)
    await m.Person.undelete(ids["Anna"])
    await run_pending()
    assert vectors_of(db_driver, ids["Anna"]) == [
        "part class",
        "part fake",
        "profile default",
    ]


# ---------------------------------------------------------------------------
# The worker and a rebuild
# ---------------------------------------------------------------------------


@no_type_check
async def test_nothing_is_claimed_while_a_rebuild_holds_its_lease_and_the_marks_are_worked_after(
    telling, db_driver
):
    from pangloss_vectors.rebuild import Lease

    m, ids = await built_with_items(telling)
    lease = Lease()
    await lease.take()
    try:
        worker = Worker()
        assert await worker.drain() == 0
        assert worker.stats.paused == 1
        assert len(marks(db_driver)) == 2
        assert telling.told == []
    finally:
        await lease.give_up()
    assert await worker.drain() == 2
    assert marks(db_driver) == []


@no_type_check
async def test_a_rebuild_waits_for_the_batch_the_worker_has_in_hand(telling, db_driver):
    m, ids = await built_with_items(telling)
    telling.pause = asyncio.Event()
    telling.rebuilt = False
    batch = asyncio.create_task(run_pending())
    await asyncio.wait_for(telling.working.wait(), 10)
    rebuilding = asyncio.create_task(rebuild(telling.name))
    await asyncio.sleep(0.5)
    # (it holds the lease, and has not begun)
    assert not rebuilding.done() and not telling.rebuilt
    telling.pause.set()
    assert await batch == 2
    await asyncio.wait_for(rebuilding, 10)
    assert telling.rebuilt


@no_type_check
async def test_a_rebuild_takes_off_the_mark_of_a_batch_that_ran_out(telling, db_driver):
    """(a worker that stopped in the middle of a batch: its mark runs out, and the rebuild goes ahead; the claims run
    out too, and are claimed again)"""
    m, ids = await built_with_items(telling)
    run(
        db_driver,
        "MERGE (w:PGVectorsWorker {kind: 'vectors'}) SET w.batch = 'gone', w.batch_until = 1.0",
    )
    telling.rebuilt = False
    await asyncio.wait_for(rebuild(telling.name), 10)
    assert telling.rebuilt
    assert run(
        db_driver, "MATCH (w:PGVectorsWorker) RETURN w.batch_until AS until"
    ) == [{"until": None}]


# ---------------------------------------------------------------------------
# Stale vectors
# ---------------------------------------------------------------------------


@no_type_check
async def test_what_a_part_says_is_stale_is_counted_and_a_rebuild_sets_it_to_0(
    telling, db_driver
):
    m, ids = await built_with_items(telling)
    telling.stale = 3
    await run_pending()
    assert (await store.states()).parts["fake"].stale == 3
    await saved_events(m, Person=["Bernard"])
    await run_pending()
    assert (await store.states()).parts["fake"].stale == 6
    await rebuild("fake")
    assert (await store.states()).parts["fake"].stale == 0


@no_type_check
async def test_past_vectors_rebuild_after_the_worker_rebuilds_the_part(
    telling, db_driver, monkeypatch
):
    """(with no `pangloss_admin` installed: the rebuild itself, in the worker)"""
    monkeypatch.setattr(core_settings.SETTINGS, "VECTORS_REBUILD_AFTER", 4)
    m, ids = await built_with_items(telling)
    generation = (await store.states()).parts["fake"].generation
    telling.stale = 3
    worker = Worker()
    await worker.drain()
    assert (await store.states()).parts["fake"].stale == 3
    assert worker.stats.rebuilds == 0
    await saved_events(m, Person=["Bernard"])
    await worker.drain()
    state = (await store.states()).parts["fake"]
    assert worker.stats.rebuilds == 1
    assert state.stale == 0 and state.generation > generation


@no_type_check
async def test_past_vectors_rebuild_after_with_pangloss_admin_the_worker_starts_the_job(
    telling, db_driver, monkeypatch, tmp_path
):
    from pangloss_admin import store as job_store

    started = []
    monkeypatch.setattr(job_store, "jobs_directory", lambda settings: tmp_path)
    monkeypatch.setattr(job_store, "launch", lambda jobs, id: started.append(id))
    monkeypatch.setattr(core_settings.SETTINGS, "VECTORS_REBUILD_AFTER", 0)
    monkeypatch.setattr(
        core_settings.SETTINGS, "INSTALLED_APPS", ["pangloss_vectors", "pangloss_admin"]
    )
    m, ids = await built_with_items(telling)
    telling.stale = 1
    await run_pending()
    (job,) = job_store.JobStore(tmp_path).recent()
    assert (job["kind"], job["options"], job["state"]) == (
        "vectors_rebuild",
        {"part": "fake"},
        "queued",
    )
    assert started == [job["id"]]
    # (and while it is queued, no other)
    await saved_events(m, Person=["Bernard"])
    await run_pending()
    assert len(job_store.JobStore(tmp_path).recent()) == 1
