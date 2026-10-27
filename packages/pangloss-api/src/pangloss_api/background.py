"""Background tasks: things an installed app keeps running for as long as the server does.

An app's `api.py` adds one in `configure_app`:

    async def watch(settings): ...             # loops until it is cancelled

    def configure_app(app, settings):
        app.state.background_tasks.append(BackgroundTask("zotero", watch))

The server starts them (as `asyncio` tasks on its own event loop, after the migration check and the startup
hooks) and stops them, before the database disconnects. A task that raises is logged and started again after a
delay that doubles up to a limit, and goes back to the start after a run that lasted; one that returns, or is
cancelled, is not started again. A task is not told about migrations: a write refused during one is an error
like any other, and it is tried again after the delay.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("pangloss.api.background")

STOP_TIMEOUT = 5.0


@dataclass
class BackgroundTask:
    name: str
    run: Callable[[Any], Awaitable[None]]
    """`async def run(settings)`: runs until cancelled (or returns, when there is nothing more to do)"""
    first_delay: float = 1.0
    max_delay: float = 60.0
    reset_after: float = 60.0
    """A run that lasts this long (seconds) is healthy: the delay after its failure starts again"""


@dataclass
class TaskStatus:
    state: str = "waiting"  # starting, running, waiting (to restart), finished, stopped
    started: float | None = None
    restarts: int = 0
    last_error: str | None = None
    last_error_when: float | None = None


@dataclass
class Supervisor:
    settings: Any
    tasks: list[BackgroundTask] = field(default_factory=list)
    statuses: dict[str, TaskStatus] = field(default_factory=dict)
    _running: dict[str, asyncio.Task] = field(default_factory=dict)

    def start(self) -> None:
        for task in self.tasks:
            if task.name in self._running:
                raise ValueError(f"There are two background tasks called {task.name!r}")
            self.statuses[task.name] = TaskStatus()
            self._running[task.name] = asyncio.create_task(
                self._supervise(task), name=f"pangloss-background-{task.name}"
            )
            logger.info("Background task %s started", task.name)

    async def _supervise(self, task: BackgroundTask) -> None:
        status = self.statuses[task.name]
        delay = task.first_delay
        while True:
            began = time.monotonic()
            status.state, status.started = "running", time.time()
            try:
                await task.run(self.settings)
            except asyncio.CancelledError:
                status.state = "stopped"
                raise
            except Exception as error:
                status.last_error = f"{type(error).__name__}: {error}"
                status.last_error_when = time.time()
                if time.monotonic() - began >= task.reset_after:
                    delay = task.first_delay
                logger.exception(
                    "Background task %s failed; trying again in %.0f s",
                    task.name,
                    delay,
                )
                status.state = "waiting"
                await asyncio.sleep(delay)
                delay = min(delay * 2, task.max_delay)
                status.restarts += 1
            else:
                status.state = "finished"
                logger.info("Background task %s finished", task.name)
                return

    async def stop(self, timeout: float = STOP_TIMEOUT) -> None:
        running = list(self._running.values())
        for task in running:
            task.cancel()
        if running:
            _, pending = await asyncio.wait(running, timeout=timeout)
            for task in pending:
                logger.warning(
                    "Background task %s did not stop within %.0f s",
                    task.get_name(),
                    timeout,
                )
        self._running.clear()

    def status(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "state": status.state,
                "started": status.started,
                "restarts": status.restarts,
                "last_error": status.last_error,
                "last_error_when": status.last_error_when,
            }
            for name, status in self.statuses.items()
        }
