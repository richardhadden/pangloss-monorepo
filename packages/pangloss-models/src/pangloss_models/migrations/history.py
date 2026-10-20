"""Which migrations have been applied, and which are to be.

The database keeps a record of each migration it has applied (`applied`: by `(app, name)` the
record's `status` ("applied", "running" or "failed") and `checksum`). These compare it with the
migrations there are."""

from typing import Any

from pangloss_models.migrations.files import Migration, MigrationGraph


def pending(graph: MigrationGraph, applied: dict[tuple[str, str], dict[str, Any]]) -> list[Migration]:
    """The migrations to apply, in the order to apply them: those not applied (or that failed,
    or were left running)"""
    return [
        migration
        for migration in graph.order()
        if applied.get(migration.key, {}).get("status") != "applied"
    ]


def problems(graph: MigrationGraph, applied: dict[tuple[str, str], dict[str, Any]]) -> list[str]:
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
            found.append(f"{name} was applied, and has been changed since (a fix is a new migration)")
    for migration in graph.order():
        if applied.get(migration.key, {}).get("status") != "applied":
            continue
        for parent in graph.parents(migration):
            if applied.get(parent, {}).get("status") != "applied":
                found.append(
                    f"{migration} was applied, but {parent[0]}.{parent[1]}, which it follows, was not"
                )
    return found
