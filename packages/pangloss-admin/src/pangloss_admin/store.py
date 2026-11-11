"""The jobs, as files: `<directory>/<id>/job.json` and what the job made in `files/`.

Files, rather than nodes in the graph, because what a job makes is a file on this machine anyway, a job's progress is
then no load on the database, and every server worker sees the same jobs. `job.json` has one writer at a time: the
server while a job is queued, the job's own process while it runs, and the server again if that process dies. It is
replaced whole, so a reader never sees half of it.
"""

import contextlib
import datetime
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

ACTIVE = {"queued", "running"}
HEARTBEAT_EVERY = 5.0
STALE_AFTER = 30.0
"""Seconds with no heartbeat after which a job's process is taken to be gone (the machine or server went down)"""
DEFAULT_DIRECTORY = ".pangloss/admin-jobs"
LOG_TAIL = 2000


class JobConflict(Exception):
    """What was asked cannot be done to the job as it is now"""


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def jobs_directory(settings: Any) -> Path:
    """`ADMIN_JOBS_DIRECTORY` in the settings, or `.pangloss/admin-jobs` of where the server was started"""
    value = getattr(settings, "ADMIN_JOBS_DIRECTORY", None) or DEFAULT_DIRECTORY
    return Path(value).expanduser().resolve()


class JobStore:
    def __init__(self, root: Path):
        self.root = root

    def directory(self, job_id: str) -> Path:
        return self.root / job_id

    def files(self, job_id: str) -> Path:
        return self.directory(job_id) / "files"

    def _ids(self) -> list[str]:
        # (the ids are UUID7s: by name is by age)
        if not self.root.is_dir():
            return []
        return sorted(
            (entry.name for entry in self.root.iterdir() if entry.is_dir()),
            reverse=True,
        )

    def read_raw(self, job_id: str) -> dict[str, Any] | None:
        """The job as it was written"""
        try:
            return json.loads((self.directory(job_id) / "job.json").read_text())
        except FileNotFoundError, NotADirectoryError:
            return None

    def write(self, job: dict[str, Any]) -> None:
        path = self.directory(job["id"]) / "job.json"
        temporary = path.with_name(f"job.{os.getpid()}.{threading.get_ident()}.tmp")
        temporary.write_text(json.dumps(job))
        os.replace(temporary, path)

    def beat(self, job_id: str) -> None:
        (self.directory(job_id) / "heartbeat").touch()

    def cancel_requested(self, job_id: str) -> bool:
        return (self.directory(job_id) / "cancelling").exists()

    def interrupted(self, job_id: str) -> bool:
        """The job was taken to be gone (see `read`), or has been deleted since: its process is to stop, and nothing
        it does after is kept"""
        directory = self.directory(job_id)
        return not directory.is_dir() or (directory / "interrupted").exists()

    def read(self, job_id: str) -> dict[str, Any] | None:
        """The job as an admin is to see it. One whose process has stopped beating is `interrupted`, and stays so: the
        first read to see it marks it, so that a process that comes back (the machine was asleep) does not take it up
        again, but sees the mark and stops (`runner.start_heartbeat`). Another job of the kind may have started"""
        job = self.read_raw(job_id)
        if job is None:
            return None
        job["cancelling"] = False
        if job["state"] in ACTIVE:
            job["cancelling"] = self.cancel_requested(job_id)
            mark = self.directory(job_id) / "interrupted"
            if not mark.exists():
                try:
                    beat = (self.directory(job_id) / "heartbeat").stat().st_mtime
                except FileNotFoundError:
                    beat = 0.0
                if time.time() - beat > STALE_AFTER:
                    # (deleted meanwhile: nothing to mark)
                    with contextlib.suppress(FileNotFoundError):
                        mark.touch()
            if mark.exists():
                job.update(state="interrupted", pid=None, cancelling=False)
        return job

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        found = (self.read(job_id) for job_id in self._ids()[:limit])
        return [job for job in found if job is not None]

    @contextlib.contextmanager
    def _locked(self) -> Generator[None]:
        # (the server may be several processes: only one at a time decides that no job of the kind is running)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(self.root / ".lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def create(
        self, kind: str, options: dict[str, Any], username: str
    ) -> dict[str, Any]:
        """A new queued job; a `JobConflict` if one of the kind has not finished"""
        with self._locked():
            for other in self.recent(limit=len(self._ids())):
                if other["kind"] == kind and other["state"] in ACTIVE:
                    raise JobConflict(f"A {kind} job is already running")
            job_id = str(uuid.uuid7())
            self.directory(job_id).mkdir(mode=0o700)
            self.beat(job_id)
            job: dict[str, Any] = {
                "id": job_id,
                "kind": kind,
                "options": options,
                "state": "queued",
                "created_by": username,
                "created_when": now(),
                "started_when": None,
                "finished_when": None,
                "pid": None,
                "step": None,
                "steps": None,
                "current": None,
                "counts": {},
                "error": None,
                "files": [],
            }
            self.write(job)
            return job

    def cancel(self, job_id: str) -> dict[str, Any]:
        # (the mark first: a job that starts now either finds it, or is seen below as running and is sent the signal)
        (self.directory(job_id) / "cancelling").touch()
        job = self.read(job_id)
        if job is None or job["state"] not in ACTIVE:
            (self.directory(job_id) / "cancelling").unlink(missing_ok=True)
            raise JobConflict("The job is not running")
        if job["pid"] is not None:
            with contextlib.suppress(ProcessLookupError):
                os.kill(job["pid"], signal.SIGTERM)
        return job

    def delete(self, job_id: str) -> None:
        job = self.read(job_id)
        if job is not None and job["state"] in ACTIVE:
            raise JobConflict("The job is running: cancel it first")
        shutil.rmtree(self.directory(job_id), ignore_errors=True)

    def file_path(self, job_id: str, name: str) -> Path | None:
        """A file the job finished making. (Only a name the job lists: nothing else in the directory can be asked for)"""
        job = self.read(job_id)
        if job is None or name not in [file["name"] for file in job["files"]]:
            return None
        return self.files(job_id) / name

    def reap(self, job_id: str, returncode: int) -> None:
        """The process has ended: if it could not say how, say it here"""
        job = self.read_raw(job_id)
        if job is None or job["state"] not in ACTIVE:
            return
        shutil.rmtree(self.files(job_id), ignore_errors=True)
        if self.interrupted(job_id):
            job.update(state="interrupted", finished_when=now(), pid=None)
        elif returncode == -signal.SIGTERM or self.cancel_requested(job_id):
            job.update(state="cancelled", finished_when=now(), pid=None)
        else:
            job.update(
                state="failed",
                finished_when=now(),
                pid=None,
                error=f"The process ended with {returncode}. {self._log_tail(job_id)}".strip(),
            )
        self.write(job)

    def _log_tail(self, job_id: str) -> str:
        try:
            return (self.directory(job_id) / "log.txt").read_text(errors="replace")[
                -LOG_TAIL:
            ]
        except FileNotFoundError:
            return ""


def command(job_id: str) -> list[str]:
    return [
        sys.executable,
        "-c",
        "from pangloss_cli.main import main; main()",
        "admin",
        "run-job",
        job_id,
    ]


def launch(store: JobStore, job_id: str, argv: list[str] | None = None) -> None:
    """Start the job's process. It is in a session of its own, so a restart of the server (`pangloss dev` reloading)
    does not stop it. A thread waits for it, so that it leaves no zombie and an early death is noticed"""
    try:
        with open(store.directory(job_id) / "log.txt", "ab") as log:
            process = subprocess.Popen(
                argv or command(job_id),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except OSError as error:
        job = store.read_raw(job_id)
        assert job is not None
        job.update(state="failed", finished_when=now(), error=str(error))
        store.write(job)
        return

    def wait() -> None:
        store.reap(job_id, process.wait())

    threading.Thread(target=wait, daemon=True, name=f"admin-job-{job_id}").start()
