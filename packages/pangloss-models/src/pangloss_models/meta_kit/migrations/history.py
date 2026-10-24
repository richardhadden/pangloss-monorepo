"""Which migrations have been applied, and which are to be.

The database keeps a record of each migration it has applied (`applied`: by `(app, name)` the
record's `status` ("applied", "running" or "failed") and `checksum`). These compare it with the
migrations there are."""

import copy
from typing import Any

from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.meta_kit.migrations.files import (
    EMPTY_SNAPSHOT,
    Migration,
    MigrationGraph,
)
from pangloss_models.meta_kit.migrations.state import apply_change


def pending(
    graph: MigrationGraph, applied: dict[tuple[str, str], dict[str, Any]]
) -> list[Migration]:
    """The migrations to apply, in the order to apply them: those not applied (or that failed,
    or were left running)"""
    return [
        migration
        for migration in graph.order()
        if applied.get(migration.key, {}).get("status") != "applied"
    ]


def problems(
    graph: MigrationGraph, applied: dict[tuple[str, str], dict[str, Any]]
) -> list[str]:
    """What is wrong between the migrations and the record of them: an applied migration that was
    edited since, one that is not there, one applied after one that depends on it is not"""
    found: list[str] = []
    for key, record in sorted(applied.items()):
        name = f"{key[0]}.{key[1]}"
        if key not in graph.migrations:
            found.append(f"{name} was applied, but there is no such migration")
            continue
        if record.get("status") == "applied" and record.get("checksum") not in (
            None,
            graph.migrations[key].checksum,
        ):
            found.append(
                f"{name} was applied, and has been changed since (a fix is a new migration)"
            )
    for migration in graph.order():
        if applied.get(migration.key, {}).get("status") != "applied":
            continue
        for parent in graph.parents(migration):
            if applied.get(parent, {}).get("status") != "applied":
                found.append(
                    f"{migration} was applied, but {parent[0]}.{parent[1]}, which it follows, was not"
                )
    return found


def resolve_target(graph: MigrationGraph, app: str, text: str) -> Migration | None:
    """The migration of the app that `text` names: its name, its number (`0002`) or the start of
    its name. `zero` is none of them (None): the app as it was before its first migration."""
    if text == "zero":
        return None
    own = [m for m in graph.migrations.values() if m.app == app]
    if not own:
        raise PanglossMigrationError(f"{app} has no migrations")
    matches = [m for m in own if m.name == text] or [
        m for m in own if m.name.startswith(text)
    ]
    if len(matches) != 1:
        names = ", ".join(sorted(m.name for m in own))
        raise PanglossMigrationError(
            f"'{text}' is not one migration of {app}"
            + (f" ({names})" if not matches else "")
        )
    return matches[0]


def begun(applied: dict[tuple[str, str], dict[str, Any]], key: tuple[str, str]) -> bool:
    """Whether a migration has been applied, or begun and not finished (failed, or running)"""
    return applied.get(key, {}).get("status") in ("applied", "failed", "running")


def to_unapply(
    graph: MigrationGraph,
    applied: dict[tuple[str, str], dict[str, Any]],
    app: str,
    target: Migration | None,
) -> list[Migration]:
    """The migrations to undo to leave `app` at `target` (None: before its first), last first: those
    of the app after it, and whatever applied migrations follow those (of any app). One that failed
    or was left running is undone too: it was begun, and what it did is undone (every change can be
    made over what is already done)."""
    number = target.number if target else 0
    chosen = {
        m.key
        for m in graph.migrations.values()
        if m.app == app and m.number > number and begun(applied, m.key)
    }
    grew = True
    while grew:
        grew = False
        for m in graph.migrations.values():
            if (
                m.key not in chosen
                and begun(applied, m.key)
                and any(parent in chosen for parent in graph.parents(m))
            ):
                chosen.add(m.key)
                grew = True
    return [m for m in reversed(graph.order()) if m.key in chosen]


def states_around(
    graph: MigrationGraph, applied_keys: set[tuple[str, str]]
) -> tuple[
    dict[tuple[str, str], dict[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
    dict[str, Any],
]:
    """The snapshot before and after each applied migration (as the files say, without the classes
    of the models), and the snapshot after all of them"""
    before: dict[tuple[str, str], dict[str, Any]] = {}
    after: dict[tuple[str, str], dict[str, Any]] = {}
    state = copy.deepcopy(EMPTY_SNAPSHOT)
    for migration in graph.order():
        if migration.key not in applied_keys:
            continue
        before[migration.key] = state
        for change in migration.changes:
            state = apply_change(state, change)
        after[migration.key] = state
    return before, after, state
