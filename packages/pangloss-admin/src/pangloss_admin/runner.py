"""What runs in a job's own process"""

import asyncio
import shutil
import signal
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from pangloss_admin.kinds import JobKind
from pangloss_admin.store import HEARTBEAT_EVERY, JobStore, now

PROGRESS_EVERY = 0.5


class JobContext:
    """What a job's `run` is given: its `options`, the `directory` to write what it makes (which is kept only if it
    succeeds), and `progress` to say how far it is"""

    def __init__(self, store: JobStore, job: dict[str, Any], directory: Path):
        self._store = store
        self._job = job
        self._written = 0.0
        self.id: str = job["id"]
        self.options: dict[str, Any] = job["options"]
        self.directory = directory

    def progress(
        self,
        step: int | None = None,
        steps: int | None = None,
        current: str | None = None,
        counts: dict[str, int] | None = None,
    ) -> None:
        """Say how far it is (`step` of `steps`, working on `current`, and any `counts`). Cheap to call often"""
        self._job.update(step=step, steps=steps, current=current)
        if counts is not None:
            self._job["counts"] = counts
        moment = time.monotonic()
        if moment - self._written >= PROGRESS_EVERY:
            self._written = moment
            self._store.write(self._job)


def start_heartbeat(store: JobStore, job_id: str) -> None:
    """A thread, so that a job busy on the event loop for a while is not taken to be dead"""

    def beat() -> None:
        while True:
            store.beat(job_id)
            time.sleep(HEARTBEAT_EVERY)

    threading.Thread(target=beat, daemon=True, name="admin-job-heartbeat").start()


async def run_job(store: JobStore, job_id: str, kinds: dict[str, JobKind]) -> bool:
    """Run the job to its end and record how it went. Gives whether it succeeded"""
    job = store.read_raw(job_id)
    if job is None:
        raise ValueError(f"There is no job {job_id}")
    import os

    job.update(state="running", started_when=now(), pid=os.getpid())
    store.write(job)
    files = store.files(job_id)
    files.mkdir(exist_ok=True)

    def ended(state: str, error: str | None = None) -> bool:
        if state != "finished":
            shutil.rmtree(files, ignore_errors=True)
        job.update(state=state, finished_when=now(), pid=None, error=error)
        job["files"] = (
            [
                {"name": path.name, "size": path.stat().st_size}
                for path in sorted(files.iterdir())
            ]
            if state == "finished"
            else []
        )
        store.write(job)
        return state == "finished"

    # (after `running` is written: see `JobStore.cancel`)
    if store.cancel_requested(job_id):
        return ended("cancelled")
    task = asyncio.current_task()
    assert task is not None
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        await kinds[job["kind"]].run(JobContext(store, job, files))
    except asyncio.CancelledError:
        return ended("cancelled")
    except Exception as error:
        traceback.print_exc()
        return ended("failed", f"{type(error).__name__}: {error}")
    return ended("finished")
