"""From the changes between the models and the migrations to the migrations to write.

`plan(graph, new, apps)` finds what changed since the last migrations, asks (through `ask`)
what only a person can say, and shares the changes among the apps: each model, and each enum, is
the business of the app it is in, and a migration depends on those of the other apps whose models
it mentions.

    result = plan(graph, snapshot, installed_apps, confirmed=..., declined=...)
    result.questions      # renames to be asked: ask, and plan again with the answers
    result.migrations     # the migrations to write, if nothing is left to ask
"""

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.diff import diff
from pangloss_models.migrations.files import (
    Migration,
    MigrationGraph,
    next_name,
    slug_of,
)
from pangloss_models.migrations.snapshot import data_view, snapshot_hash
from pangloss_models.migrations.state import replay


@dataclass
class Plan:
    changes: list[c.Change] = field(default_factory=list)
    questions: list[c.PossibleRename] = field(default_factory=list)
    migrations: list[Migration] = field(default_factory=list)
    # The snapshot after the migrations that there are (what the changes are from)
    old: dict[str, Any] = field(default_factory=dict)

    @property
    def is_final(self) -> bool:
        return not self.questions

    @property
    def is_empty(self) -> bool:
        return not self.changes


def app_of_module(module: str, apps: Iterable[str]) -> str | None:
    """The installed app a module is in: the longest name that it is, or is in"""
    matches = [app for app in apps if module == app or module.startswith(app + ".")]
    return max(matches, key=len) if matches else None


def subject_of(change: c.Change) -> str | None:
    """The model or enum a change is about (by the name it has after the change)"""
    if isinstance(change, (c.RenameModel, c.RenameEnum)):
        return change.new
    return getattr(change, "model", None) or getattr(change, "enum", None)


def owner_of(
    name: str,
    new: dict[str, Any],
    owners: dict[str, str],
    apps: list[str],
) -> str:
    """The app that a model or enum belongs to: where the class is now, or where the
    migrations made it, or (for an enum new to them) the app of a model that uses it"""
    model = new["models"].get(name)
    if model is not None and model.get("module"):
        app = app_of_module(model["module"], apps)
        if app:
            return app
    if name in owners:
        return owners[name]
    if name in new["enums"]:
        for model in new["models"].values():
            if json.dumps(model.get("fields", [])).count(f'"{name}"') and model.get("module"):
                app = app_of_module(model["module"], apps)
                if app:
                    return app
    if apps:
        return apps[0]
    raise PanglossMigrationError(f"{name} is not in any installed app")


def mentioned(change: c.Change, names: Iterable[str]) -> set[str]:
    """Which of the names of models and enums a change mentions"""
    text = json.dumps(change.to_dict(), default=str)
    return {name for name in names if f'"{name}"' in text}


def plan(
    graph: MigrationGraph,
    new: dict[str, Any],
    apps: list[str],
    confirmed: Iterable[c.PossibleRename] = (),
    declined: Iterable[c.PossibleRename] = (),
    answer: Any = None,
    name: str | None = None,
) -> Plan:
    """What to write so that the migrations give the snapshot `new`.

    `answer(changes, old)` may return the changes with the answers they need filled in."""
    old = graph.state()
    result = diff(old, new, confirmed=confirmed, declined=declined)
    plan_ = Plan(changes=result.changes, questions=result.questions, old=old)
    if not result.changes or not result.is_final:
        return plan_

    changes = answer(result.changes, old) if answer else result.changes
    plan_.changes = changes
    plan_.migrations = split(graph, old, new, changes, apps, name)
    return plan_


def split(
    graph: MigrationGraph,
    old: dict[str, Any],
    new: dict[str, Any],
    changes: list[c.Change],
    apps: list[str],
    name: str | None = None,
) -> list[Migration]:
    owners = graph.owners()
    names = set(new["models"]) | set(new["enums"]) | set(old["models"]) | set(old["enums"])

    groups: dict[str, list[c.Change]] = {}
    for change in changes:
        subject = subject_of(change)
        app = owner_of(subject, new, owners, apps) if subject else apps[0]
        groups.setdefault(app, []).append(change)

    # what each app makes, so that another's migration can depend on it
    created: dict[str, str] = {}
    for app, group in groups.items():
        for change in group:
            if isinstance(change, (c.CreateModel, c.CreateEnum)):
                created[getattr(change, "model", None) or change.enum] = app  # type: ignore[attr-defined]

    existing = list(graph.migrations.values())
    migrations: dict[str, Migration] = {}
    names_of: dict[str, str] = {}
    for app, group in groups.items():
        initial = graph.leaf(app) is None
        migration_name = name if name and len(groups) == 1 else next_name(
            [m for m in existing if m.app == app], slug_of(group, initial=initial)
        )
        names_of[app] = migration_name

    for app, group in groups.items():
        dependencies: set[tuple[str, str]] = set()
        for change in group:
            for mention in mentioned(change, names):
                other = created.get(mention) or owners.get(mention)
                if other and other != app:
                    if other in names_of and mention in created:
                        dependencies.add((other, names_of[other]))
                    else:
                        leaf = graph.leaf(other)
                        if leaf:
                            dependencies.add((other, leaf.name))
        migrations[app] = Migration(
            app=app,
            name=names_of[app],
            changes=tuple(group),
            dependencies=tuple(sorted(dependencies)),
        )

    ordered = order_migrations(migrations)
    # check that they do what was found, applied in the order they will be
    state = old
    for migration in ordered:
        state = replay(state, migration.changes)
    if state != data_view(new):
        raise PanglossMigrationError(
            "The changes cannot be shared among the apps so that they come to the models: "
            "models of different apps depend on each other. Put them in one app, or write the "
            "migrations by hand"
        )
    final = snapshot_hash(new)
    return [
        Migration(
            app=m.app,
            name=m.name,
            changes=m.changes,
            dependencies=m.dependencies,
            schema_hash=final,
        )
        for m in ordered
    ]


def order_migrations(migrations: dict[str, Migration]) -> list[Migration]:
    """Each after those of the other apps that it depends on"""
    remaining = dict(migrations)
    done: list[Migration] = []
    placed: set[str] = set()
    while remaining:
        ready = [
            app
            for app, m in remaining.items()
            if all(dep_app in placed or dep_app not in migrations for dep_app, _ in m.dependencies)
        ]
        if not ready:
            raise PanglossMigrationError(
                "The migrations to write depend on each other in a circle: "
                + ", ".join(sorted(remaining))
            )
        app = sorted(ready)[0]
        done.append(remaining.pop(app))
        placed.add(app)
    return done
