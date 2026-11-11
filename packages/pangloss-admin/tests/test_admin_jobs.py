"""The job kinds, the files that hold the jobs, and a job's process"""

import asyncio
import os
import sys
import textwrap
import time
import types

import pytest
from pangloss_admin import Choice, Flag, JobKind
from pangloss_admin.kinds import job_kinds
from pangloss_admin.runner import JobContext, run_job
from pangloss_admin.store import JobConflict, JobStore, launch


async def nothing(context):
    pass


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "jobs")


def until(condition, timeout=20.0):
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, "it did not happen"
        time.sleep(0.02)


# -- kinds --

KIND = JobKind(
    "a_job", nothing, options=(Choice("format", ("x", "y"), "x"), Flag("deep"))
)


def test_options_get_their_defaults_and_are_checked():
    assert KIND.checked_options({}) == {"format": "x", "deep": False}
    assert KIND.checked_options({"format": "y", "deep": True}) == {
        "format": "y",
        "deep": True,
    }
    for wrong in ({"format": "z"}, {"deep": "yes"}, {"other": 1}):
        with pytest.raises(ValueError):
            KIND.checked_options(wrong)


def test_a_bad_declaration_is_refused():
    with pytest.raises(ValueError):
        JobKind("Not A Name", nothing)
    with pytest.raises(ValueError):
        Choice("c", ("a",), "b")


def test_apps_declare_jobs_in_their_admin_module(monkeypatch):
    module = types.ModuleType("some_app.admin")
    module.jobs = [KIND]
    monkeypatch.setitem(sys.modules, "some_app", types.ModuleType("some_app"))
    monkeypatch.setitem(sys.modules, "some_app.admin", module)
    # (an app with no admin module has no jobs)
    assert job_kinds(["some_app", "json"]) == {"a_job": KIND}
    twin = types.ModuleType("other_app.admin")
    twin.jobs = [KIND]
    monkeypatch.setitem(sys.modules, "other_app", types.ModuleType("other_app"))
    monkeypatch.setitem(sys.modules, "other_app.admin", twin)
    with pytest.raises(ValueError, match="two"):
        job_kinds(["some_app", "other_app"])


def test_an_error_inside_an_admin_module_is_not_hidden(monkeypatch, tmp_path):
    (tmp_path / "broken_app").mkdir()
    (tmp_path / "broken_app" / "__init__.py").write_text("")
    (tmp_path / "broken_app" / "admin.py").write_text("import no_such_module_at_all\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ModuleNotFoundError):
        job_kinds(["broken_app"])


# -- the store --


def test_one_job_of_a_kind_at_a_time(store):
    job = store.create("a", {}, "me")
    with pytest.raises(JobConflict):
        store.create("a", {}, "me")
    store.create("b", {}, "me")  # (another kind may)
    store.write({**store.read_raw(job["id"]), "state": "finished"})
    store.create("a", {}, "me")


def test_newest_first(store):
    ids = [store.create(f"k{n}", {}, "me")["id"] for n in range(3)]
    assert [job["id"] for job in store.recent()] == ids[::-1]
    assert len(store.recent(limit=2)) == 2


def test_a_job_with_no_heartbeat_is_interrupted_and_lets_another_start(store):
    job = store.create("a", {}, "me")
    long_ago = time.time() - 3600
    os.utime(store.directory(job["id"]) / "heartbeat", (long_ago, long_ago))
    assert store.read(job["id"])["state"] == "interrupted"
    store.create("a", {}, "me")


def test_a_running_job_cannot_be_deleted_and_a_finished_one_cannot_be_cancelled(store):
    job = store.create("a", {}, "me")
    with pytest.raises(JobConflict):
        store.delete(job["id"])
    store.write({**store.read_raw(job["id"]), "state": "finished"})
    with pytest.raises(JobConflict):
        store.cancel(job["id"])
    store.delete(job["id"])
    assert store.read(job["id"]) is None


def test_only_a_file_the_job_lists_can_be_asked_for(store):
    job = store.create("a", {}, "me")
    store.files(job["id"]).mkdir()
    (store.files(job["id"]) / "out.nq").write_text("x")
    store.write({**job, "state": "finished", "files": [{"name": "out.nq", "size": 1}]})
    assert store.file_path(job["id"], "out.nq") == store.files(job["id"]) / "out.nq"
    assert store.file_path(job["id"], "../job.json") is None
    assert store.file_path(job["id"], "log.txt") is None


# -- running --


def test_a_job_that_succeeds_keeps_its_files(store):
    async def run(context: JobContext):
        (context.directory / "out.txt").write_text("hello")
        context.progress(1, 2, "Person", {"items": 5})

    job = store.create("a", {"o": 1}, "me")
    assert asyncio.run(run_job(store, job["id"], {"a": JobKind("a", run)}))
    done = store.read(job["id"])
    assert done["state"] == "finished"
    assert done["files"] == [{"name": "out.txt", "size": 5}]
    assert done["counts"] == {"items": 5}
    assert done["pid"] is None


def test_a_job_that_fails_says_why_and_keeps_nothing(store):
    async def run(context):
        (context.directory / "half.txt").write_text("half")
        raise RuntimeError("no disk")

    job = store.create("a", {}, "me")
    assert not asyncio.run(run_job(store, job["id"], {"a": JobKind("a", run)}))
    done = store.read(job["id"])
    assert done["state"] == "failed"
    assert done["error"] == "RuntimeError: no disk"
    assert done["files"] == []
    assert not store.files(job["id"]).exists()


def test_a_job_cancelled_before_it_starts_does_not_run(store):
    ran = []

    async def run(context):
        ran.append(True)

    job = store.create("a", {}, "me")
    store.cancel(job["id"])
    asyncio.run(run_job(store, job["id"], {"a": JobKind("a", run)}))
    assert ran == []
    assert store.read(job["id"])["state"] == "cancelled"


def test_a_process_that_dies_is_recorded_with_the_end_of_its_log(store):
    job = store.create("a", {}, "me")
    launch(
        store,
        job["id"],
        [sys.executable, "-c", "import sys; print('boom', flush=True); sys.exit(3)"],
    )
    until(lambda: store.read(job["id"])["state"] != "queued")
    done = store.read(job["id"])
    assert done["state"] == "failed"
    assert "3" in done["error"] and "boom" in done["error"]


SLEEPER = textwrap.dedent(
    """
    import asyncio, sys
    from pathlib import Path
    from pangloss_admin import JobKind
    from pangloss_admin.runner import run_job, start_heartbeat
    from pangloss_admin.store import JobStore

    async def run(context):
        (context.directory / "half.txt").write_text("half")
        await asyncio.sleep(600)

    store = JobStore(Path(sys.argv[1]))
    start_heartbeat(store, sys.argv[2])
    asyncio.run(run_job(store, sys.argv[2], {"a": JobKind("a", run)}))
    """
)


def test_cancelling_a_real_process_stops_it_and_keeps_nothing(store):
    job = store.create("a", {}, "me")
    launch(
        store, job["id"], [sys.executable, "-c", SLEEPER, str(store.root), job["id"]]
    )
    until(lambda: (store.files(job["id"]) / "half.txt").exists())
    pid = store.read(job["id"])["pid"]
    store.cancel(job["id"])
    assert store.read(job["id"])["cancelling"] or store.read(job["id"])["state"] == (
        "cancelled"
    )
    until(lambda: store.read(job["id"])["state"] == "cancelled")
    assert not store.files(job["id"]).exists()

    def gone():
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        return False

    until(gone)


def test_an_interrupted_job_stays_interrupted_when_its_heartbeat_comes_back(store):
    """The machine slept: the job is shown as interrupted, and another may have started. It does not come back"""
    job = store.create("a", {}, "me")
    long_ago = time.time() - 3600
    os.utime(store.directory(job["id"]) / "heartbeat", (long_ago, long_ago))
    assert store.read(job["id"])["state"] == "interrupted"
    store.beat(job["id"])
    assert store.read(job["id"])["state"] == "interrupted"
    assert store.interrupted(job["id"])


def mark_interrupted(store, job_id):
    long_ago = time.time() - 3600
    os.utime(store.directory(job_id) / "heartbeat", (long_ago, long_ago))
    assert store.read(job_id)["state"] == "interrupted"


def test_a_job_that_ends_after_it_was_interrupted_is_recorded_so_and_keeps_nothing(
    store,
):
    async def run(context):
        (context.directory / "out.txt").write_text("late")
        mark_interrupted(store, context.id)

    job = store.create("a", {}, "me")
    assert not asyncio.run(run_job(store, job["id"], {"a": JobKind("a", run)}))
    done = store.read_raw(job["id"])
    assert done["state"] == "interrupted"
    assert done["files"] == []
    assert not store.files(job["id"]).exists()


def test_a_job_deleted_while_its_process_runs_on_is_not_written_again(store):
    async def run(context):
        mark_interrupted(store, context.id)
        store.delete(context.id)
        context.progress(1, 2)

    job = store.create("a", {}, "me")
    assert not asyncio.run(run_job(store, job["id"], {"a": JobKind("a", run)}))
    assert not store.directory(job["id"]).exists()


def test_a_real_process_that_was_taken_to_be_gone_stops_itself(store):
    job = store.create("a", {}, "me")
    launch(
        store, job["id"], [sys.executable, "-c", SLEEPER, str(store.root), job["id"]]
    )
    until(lambda: (store.files(job["id"]) / "half.txt").exists())
    pid = store.read(job["id"])["pid"]
    mark_interrupted(store, job["id"])
    # (the heartbeat thread sees the mark at its next beat)
    until(lambda: store.read_raw(job["id"])["state"] == "interrupted")
    assert not store.files(job["id"]).exists()

    def gone():
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        return False

    until(gone)
