"""A server that is still running when its database is migrated.

A server's models are those of its code when it started. `pangloss migrate`, run beside it from newer code, changes
the data under it: the server then read what its models no longer fit and answered 500 until someone thought to
restart it, and could write in the old shape. So the server remembers which migrations were applied when it started
and looks again every `MIGRATION_WATCH_SECONDS` (and before a write, and when a request fails, if it has not looked
for a second). Once a migration is applied that its code did not have, or one it started with is no longer applied,
every request for `/api` is a 503 that says to restart the server.

While a migration runs nothing is refused here: writes are refused by the database's lock
(`PanglossReadOnlyError`), and reading goes on, as `implementation_docs/migrations.md` says.
"""

import asyncio
import logging
import time
from types import ModuleType
from typing import Any

from fastapi.responses import JSONResponse
from pangloss_models.migrations.files import discover
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("pangloss.api.migrations")

# (a write, or a request that failed, looks again if the last look is older than this: seconds)
FRESH = 1.0
READS = ("GET", "HEAD", "OPTIONS")

type Key = tuple[str, str]


def applied_of(records: dict[Key, dict[str, Any]]) -> frozenset[Key]:
    return frozenset(
        key for key, record in records.items() if record.get("status") == "applied"
    )


def names(keys: set[Key] | frozenset[Key]) -> str:
    listed = sorted(f"{app}.{name}" for app, name in keys)
    return ", ".join(listed[:5]) + (", ..." if len(listed) > 5 else "")


class MigrationWatch:
    def __init__(self, backend: ModuleType, apps: list[str], interval: float) -> None:
        self.backend = backend
        self.interval = interval
        # (what the code had when the server started: a migration among these that is applied later, as when the
        # server was started with some pending, is one its models already are)
        self.known: frozenset[Key] = frozenset(
            migration.key for app in apps for migration in discover(app)
        )
        self.at_start: frozenset[Key] = frozenset()
        self.moved: str | None = None
        self.looked = 0.0
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self.at_start = applied_of(await self.backend.applied())
        self.looked = time.monotonic()
        if self.interval > 0:
            self._task = asyncio.create_task(
                self._run(), name="pangloss-migration-watch"
            )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while self.moved is None:
            await asyncio.sleep(self.interval)
            await self.look()

    async def look(self) -> str | None:
        """Read which migrations are applied now: what is wrong, if the database is no longer the one the server
        started with (and it stays wrong: only a restart loads the models again)"""
        if self.moved is not None:
            return self.moved
        self.looked = time.monotonic()
        try:
            now = applied_of(await self.backend.applied())
        except Exception as error:  # noqa: BLE001 (a database that is away is not what this looks for)
            logger.warning("Could not read which migrations are applied: %s", error)
            return None
        new = now - self.at_start - self.known
        gone = self.at_start - now
        if new or gone:
            what = " and ".join(
                part
                for part in (
                    f"{names(new)} applied" if new else "",
                    f"{names(gone)} taken back" if gone else "",
                )
                if part
            )
            self.moved = (
                f"The database has been migrated since this server started ({what}): the server's models are not "
                "the database's any more. Restart the server"
            )
            logger.error(
                "%s. Every request for /api is refused (503) until then", self.moved
            )
        return self.moved

    async def look_if_stale(self) -> str | None:
        if self.moved is None and time.monotonic() - self.looked > FRESH:
            return await self.look()
        return self.moved


def watch_of(scope: Scope) -> MigrationWatch | None:
    app = scope.get("app")
    return getattr(getattr(app, "state", None), "migration_watch", None)


def refusal(message: str) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": message})


async def moved_after_failure(scope: Scope) -> str | None:
    """For a request that failed (a bug, or data the models do not fit): whether the database has been migrated,
    looking now"""
    watch = watch_of(scope)
    return await watch.look_if_stale() if watch is not None else None


class MigrationGate:
    """Refuse every request for `/api` once the database is not the one the server started with"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        watch = watch_of(scope) if scope["type"] == "http" else None
        if watch is None or not scope["path"].startswith("/api"):
            return await self.app(scope, receive, send)
        moved = watch.moved
        if moved is None and scope["method"] not in READS:
            # (a write in the old shape is worse than a read that fails: look before it, not up to ten seconds after)
            moved = await watch.look_if_stale()
        if moved is not None:
            return await refusal(moved)(scope, receive, send)
        await self.app(scope, receive, send)
