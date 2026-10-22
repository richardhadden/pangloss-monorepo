"""Applying a list of changes to a database, in order.

The changes to the data that come one after another are made in one transaction (so that
they happen together or not at all); a change to the database itself (an index or constraint) is made on
its own, between them, as Memgraph requires. The snapshot is followed through, so that
each change is given the state of the models just before it.
"""

import dataclasses
import json
from collections.abc import Awaitable, Callable
from typing import Any

from pangloss_models.migrations import apply_change as apply_to_snapshot
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.reports import ChangeReport

from pangloss_memgraph.databases.memgraph.database import Database, Transaction
from pangloss_memgraph.databases.memgraph.migrations.operations import (
    COUNTERS,
    Window,
    apply_change,
    apply_window,
    apply_edges,
    batch_kind,
    is_ddl,
    run_ddl,
    wrap_reified,
)


async def apply_changes(
    database: Database, state: dict[str, Any], changes: list[c.Change]
) -> dict[str, Any]:
    """Apply the changes to the database. Returns the snapshot after them.

    A change is applied once its predecessors have been: a failure leaves the changes
    before it (in a transaction, or made on their own) done."""
    if not hasattr(database, "driver"):
        await database._initialise_driver()
    database_name = database.settings.DATABASE.DATABASE_NAME

    group: list[tuple[c.Change, dict[str, Any]]] = []

    async def flush() -> None:
        if not group:
            return
        batch = list(group)
        group.clear()

        async def work(tx: Transaction) -> None:
            for change, before in batch:
                await apply_change(tx, change, before)

        async with database.driver.session(database=database_name) as session:
            await session.execute_write(work)

    for change in changes:
        if is_ddl(change):
            await flush()
            await run_ddl(database, change, state)
        else:
            group.append((change, state))
        state = apply_to_snapshot(state, change)
    await flush()
    return state


async def dry_run(
    database: Database, state: dict[str, Any], changes: list[c.Change]
) -> tuple[list[ChangeReport], dict[str, Any]]:
    """Try the changes, in one transaction that is rolled back, and say what each did.

    Nothing is changed. A change to the database itself (an index or constraint) cannot be tried, and
    is not. A change that would fail for real says so: a value that is needed and was not given, data
    that does not convert. After a failure the rest are not tried (the transaction cannot go on).
    Returns the reports, and the snapshot after the changes."""
    if not hasattr(database, "driver"):
        await database._initialise_driver()
    reports: list[ChangeReport] = []
    failed = False
    async with database.driver.session(database=database.settings.DATABASE.DATABASE_NAME) as session:
        tx = await session.begin_transaction()
        try:
            for change in changes:
                before = state
                state = apply_to_snapshot(state, change)
                if is_ddl(change):
                    reports.append(ChangeReport(change, "ddl"))
                elif failed:
                    reports.append(ChangeReport(change, "not tried"))
                else:
                    counters: dict[str, int] = {}
                    token = COUNTERS.set(counters)
                    try:
                        await apply_change(tx, change, before)  # ty: ignore[invalid-argument-type]
                        reports.append(ChangeReport(change, "counted", dict(counters)))
                    except Exception as error:
                        failed = True
                        reports.append(ChangeReport(change, "error", message=str(error).split("\n")[0]))
                    finally:
                        COUNTERS.reset(token)
        finally:
            await tx.rollback()
    return reports, state


@dataclasses.dataclass(frozen=True)
class Progress:
    """How far a migration has got, so that it can go on from there: the changes before `change`
    are done, and `change` is done for the nodes with an id up to `after`."""

    change: int = 0
    after: str = ""

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self))

    @classmethod
    def from_json(cls, text: str | None) -> "Progress":
        return cls(**json.loads(text)) if text else cls()


# Saves the progress, in the transaction of the batch if there is one
SaveProgress = Callable[[Transaction | None, Progress], Awaitable[None]]


async def apply_changes_in_batches(
    database: Database,
    state: dict[str, Any],
    changes: list[c.Change],
    size: int,
    start: Progress | None = None,
    save: SaveProgress | None = None,
) -> dict[str, Any]:
    """Apply the changes a batch at a time, each batch its own transaction, saving how far it has
    got in the same transaction (`save`) so that a run that stops can go on from `start`.

    A change that can be made in batches (`batch_kind`) is made `size` nodes at a time, in the order
    of their ids, or (a wrapped relation) as many relations at a time, which are no longer there to
    be wrapped once they are; the others are made at once, in a transaction of their own. A check
    that must pass before anything is changed (that all values convert) is made once, before the
    first batch. Returns the snapshot after the changes."""
    if not hasattr(database, "driver"):
        await database._initialise_driver()
    database_name = database.settings.DATABASE.DATABASE_NAME
    start = start or Progress()

    async def in_transaction(work: Callable[[Transaction], Awaitable[Any]]) -> Any:
        async with database.driver.session(database=database_name) as session:
            return await session.execute_write(work)

    for index, change in enumerate(changes):
        before = state
        state = apply_to_snapshot(state, change)
        if index < start.change:
            continue

        if is_ddl(change):
            await run_ddl(database, change, before)
            if save:
                await save(None, Progress(index + 1))
            continue

        kind = batch_kind(change, before)
        if kind == "window":
            after = start.after if index == start.change else ""
            while True:

                async def window_work(tx: Transaction, after: str = after) -> list[str]:
                    ids = await apply_window(tx, change, before, Window(after, size))
                    if save:
                        await save(tx, Progress(index, max(ids) if ids else after))  # type: ignore[arg-type]
                    return ids

                ids = await in_transaction(window_work)
                if not ids:
                    break
                after = max(ids)
                if len(ids) < size:
                    break
        elif kind == "wrap":
            while True:

                async def wrap_work(tx: Transaction) -> int:
                    wrapped = await wrap_reified(tx, change, before, limit=size)  # ty: ignore[invalid-argument-type]
                    if save:
                        await save(tx, Progress(index))
                    return wrapped

                if await in_transaction(wrap_work) < size:
                    break
        elif kind == "edges":
            while True:

                async def edges_work(tx: Transaction) -> int:
                    renamed = await apply_edges(tx, change, before, size)  # type: ignore[arg-type]
                    if save:
                        await save(tx, Progress(index))
                    return renamed

                if await in_transaction(edges_work) < size:
                    break
        else:

            async def whole_work(tx: Transaction) -> None:
                await apply_change(tx, change, before)

            await in_transaction(whole_work)

        if save:
            await save(None, Progress(index + 1))
    return state
