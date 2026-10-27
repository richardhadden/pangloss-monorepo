"""From the changes between the models and the migrations to the migrations to write.

`plan(graph, new, apps)` finds what changed since the last migrations, asks (through `ask`)
what only a person can say, and shares the changes among the apps: each model, and each enum, is
the business of the app it is in, and a migration depends on those of the other apps whose models
it mentions.

    result = plan(graph, snapshot, installed_apps, confirmed=..., declined=...)
    result.questions      # renames to be asked: ask, and plan again with the answers
    result.migrations     # the migrations to write, if nothing is left to ask
"""

import dataclasses
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pangloss_models.exceptions import (
    PanglossMigrationError,
    PanglossMigrationNotSupported,
)
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.diff import diff, needs_value
from pangloss_models.migrations.files import (
    Migration,
    MigrationGraph,
    next_name,
    slug_of,
    structure_id,
)
from pangloss_models.migrations.snapshot import data_view, snapshot_hash
from pangloss_models.migrations.state import replay, same_structure


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
            if json.dumps(model.get("fields", [])).count(f'"{name}"') and model.get(
                "module"
            ):
                app = app_of_module(model["module"], apps)
                if app:
                    return app
    if apps:
        return apps[0]
    raise PanglossMigrationError(f"{name} is not in any installed app")


def structure_owner(
    change: c.Change, new: dict[str, Any], owners: dict[str, str], apps: list[str]
) -> str:
    """The app that makes (or drops) an index or constraint: the one the database package says,
    for one that is new; the one that made it, for one that is dropped; otherwise the first"""
    entry = getattr(change, "index", None) or getattr(change, "constraint")  # noqa: B009
    key = "indexes" if hasattr(change, "index") else "constraints"
    for candidate in new.get(key, []):
        if same_structure(candidate, entry) and candidate.get("app") in apps:
            return candidate["app"]
    return owners.get(structure_id(change)) or apps[0]


def app_of_change(
    change: c.Change, new: dict[str, Any], owners: dict[str, str], apps: list[str]
) -> str:
    """The app whose migration a change is written in"""
    if isinstance(
        change, (c.AddIndex, c.RemoveIndex, c.AddConstraint, c.RemoveConstraint)
    ):
        return structure_owner(change, new, owners, apps)
    subject = subject_of(change)
    return owner_of(subject, new, owners, apps) if subject else apps[0]


def with_what_they_need(migrations: Iterable[Migration], app: str) -> list[Migration]:
    """The migrations of one app, and those of other apps in the same lot that they depend on
    (a migration cannot be written without the ones it follows)"""
    by_key = {m.key: m for m in migrations}
    wanted = {key for key, m in by_key.items() if m.app == app}
    pending = list(wanted)
    while pending:
        for dependency in by_key[pending.pop()].dependencies:
            if dependency in by_key and dependency not in wanted:
                wanted.add(dependency)
                pending.append(dependency)
    return [m for m in migrations if m.key in wanted]


def mentioned(change: c.Change, names: Iterable[str]) -> set[str]:
    """Which of the names of models and enums a change mentions"""
    text = json.dumps(change.to_dict(), default=str)
    return {name for name in names if f'"{name}"' in text}


def refuse_kind_changes(changes: list[c.Change]) -> None:
    """A model or a field that is another kind (an Entity that is a Document, a plain field that is a
    relation) is stored differently, and nothing can be made of it: it is not allowed."""
    refused = [
        ch for ch in changes if isinstance(ch, (c.AlterModelKind, c.ChangeFieldKind))
    ]
    if refused:
        raise PanglossMigrationNotSupported(
            "Changing the kind of a model or a field is not supported:\n  "
            + "\n  ".join(ch.describe() for ch in refused)
            + "\nKeep its kind, or make a new model or field and move the data to it."
        )


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

    refuse_kind_changes(result.changes)
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
    names = (
        set(new["models"]) | set(new["enums"]) | set(old["models"]) | set(old["enums"])
    )

    groups: dict[str, list[c.Change]] = {}
    for change in changes:
        groups.setdefault(app_of_change(change, new, owners, apps), []).append(change)

    # what each app makes, so that another's migration can depend on it
    created = created_by(groups)

    existing = list(graph.migrations.values())
    layers = layers_of(groups, created, names)
    migrations: dict[tuple[str, int], Migration] = {}
    names_of: dict[tuple[str, int], str] = {}
    for (app, layer), group in layers.items():
        taken = [m for m in existing if m.app == app] + [
            m for (a, _), m in migrations.items() if a == app
        ]
        # (a name given is the slug: the number goes in front of it, as of any other)
        migration_name = next_name(
            taken,
            name
            if name and len(layers) == 1
            else slug_of(group, initial=graph.leaf(app) is None and layer == 0),
        )
        names_of[(app, layer)] = migration_name
        # (a placeholder, so that the next layer of the app is numbered after it)
        migrations[(app, layer)] = Migration(
            app=app, name=migration_name, changes=tuple(group)
        )

    for (app, layer), group in layers.items():
        dependencies: set[tuple[str, str]] = set()
        for change in group:
            for mention in mentioned(change, names):
                other = created.get(mention) or owners.get(mention)
                if other and other != app:
                    if mention in created and (other, 0) in names_of:
                        dependencies.add(
                            (other, names_of[(other, 0)])
                        )  # (made in the first layer)
                    else:
                        leaf = graph.leaf(other)
                        if leaf:
                            dependencies.add((other, leaf.name))
        migrations[(app, layer)] = Migration(
            app=app,
            name=names_of[(app, layer)],
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


def created_by(groups: dict[str, list[c.Change]]) -> dict[str, str]:
    """The app that makes each model and enum that is new"""
    created: dict[str, str] = {}
    for app, group in groups.items():
        for change in group:
            if isinstance(change, (c.CreateModel, c.CreateEnum)):
                created[
                    change.model if isinstance(change, c.CreateModel) else change.enum
                ] = app
    return created


def needs_other_apps(
    group: list[c.Change], app: str, created: dict[str, str], names: set[str]
) -> set[str]:
    """The other apps whose new models or enums the changes mention"""
    others = {n for n, a in created.items() if a != app}
    found: set[str] = set()
    for change in group:
        found |= {created[n] for n in mentioned(change, others)}
    return found


def cyclic_apps(
    groups: dict[str, list[c.Change]], created: dict[str, str], names: set[str]
) -> set[str]:
    """The apps whose new models need those of an app that needs theirs, however far round"""
    needs = {
        app: needs_other_apps(group, app, created, names)
        for app, group in groups.items()
    }

    def reaches(start: str, goal: str, seen: set[str]) -> bool:
        return any(
            nxt == goal or (nxt not in seen and reaches(nxt, goal, seen | {nxt}))
            for nxt in needs.get(start, ())
        )

    return {app for app in groups if reaches(app, app, {app})}


def layers_of(
    groups: dict[str, list[c.Change]], created: dict[str, str], names: set[str]
) -> dict[tuple[str, int], list[c.Change]]:
    """The changes of each app as one migration (layer 0), except where new models need each other
    round a circle. Then an app is split in two, one at a time until the circle is broken: the first
    makes its models without the fields that refer to another app's new models, the second adds
    those fields, once the others' models are there. (The second follows the first of every app it
    needs, so there is no circle.)"""
    first = dict(groups)
    second: dict[str, list[c.Change]] = {}
    while True:
        cyclic = sorted(cyclic_apps(first, created, names))
        if not cyclic:
            break
        for app in cyclic:
            moved_first, moved_second = split_app(first[app], app, created)
            if moved_second:
                break
        else:
            raise PanglossMigrationError(
                "The new models of these apps need each other, and not by a field or a parent class that "
                f"can be added later: {', '.join(cyclic)}. Put them in one app, or write the migrations by hand"
            )
        first[app] = moved_first
        second[app] = second.get(app, []) + moved_second
    layers: dict[tuple[str, int], list[c.Change]] = {
        (app, 0): group for app, group in first.items()
    }
    layers.update({(app, 1): group for app, group in second.items() if group})
    return layers


def split_app(
    group: list[c.Change], app: str, created: dict[str, str]
) -> tuple[list[c.Change], list[c.Change]]:
    """The changes of an app that do not need the new models of other apps, and those that do (a
    model's fields that refer to them are added after it is made)"""
    others = {n for n, a in created.items() if a != app}
    first: list[c.Change] = []
    second: list[c.Change] = []
    for change in group:
        if isinstance(change, c.CreateModel):
            kept, moved = [], []
            for entry in change.definition.get("fields", []):
                (moved if mentioned_in(entry, others) else kept).append(entry)
            # (a parent class that is another app's new model is a label, and the `parent`: given once
            # it is there)
            own_labels = [
                l for l in change.definition.get("labels", []) if l not in others
            ]
            parent_labels = [
                l for l in change.definition.get("labels", []) if l in others
            ]
            parent = change.definition.get("parent")
            late_parent = parent if parent in others else None
            definition = {**change.definition, "fields": kept, "labels": own_labels}
            if late_parent:
                definition["parent"] = None
            first.append(
                dataclasses.replace(change, definition=definition)
                if moved or parent_labels or late_parent
                else change
            )
            if parent_labels:
                second.append(
                    c.AlterModelLabels(model=change.model, added=parent_labels)
                )
            if late_parent:
                second.append(
                    c.AlterModelOption(
                        model=change.model, option="parent", old=None, new=late_parent
                    )
                )
            second += [
                c.AddField(
                    model=change.model,
                    name=entry["name"],
                    field_kind=entry["kind"],
                    needs_value=needs_value(entry),
                    definition=entry,
                )
                for entry in moved
            ]
        elif not isinstance(change, c.CreateEnum) and mentioned(change, others):
            second.append(change)
        else:
            first.append(change)
    return first, second


def mentioned_in(value: Any, names: Iterable[str]) -> set[str]:
    text = json.dumps(value, default=str)
    return {name for name in names if f'"{name}"' in text}


def order_migrations(migrations: dict[tuple[str, int], Migration]) -> list[Migration]:
    """Each after those of the other apps that it depends on (and an app's layers in order)"""
    remaining = dict(migrations)
    done: list[Migration] = []
    placed: set[str] = set()  # (the names of the migrations, as app.name)
    while remaining:
        ready = [
            key
            for key, m in remaining.items()
            if all(
                f"{dep_app}.{dep_name}" in placed
                or (dep_app, dep_name)
                not in {(a, mm.name) for (a, _), mm in migrations.items()}
                for dep_app, dep_name in m.dependencies
            )
            and not any(a == key[0] and layer < key[1] for (a, layer) in remaining)
        ]
        if not ready:
            raise PanglossMigrationError(
                "The migrations to write depend on each other in a circle: "
                + ", ".join(sorted(f"{a}.{m.name}" for (a, _), m in remaining.items()))
            )
        key = sorted(ready)[0]
        migration = remaining.pop(key)
        placed.add(f"{migration.app}.{migration.name}")
        done.append(migration)
    return done
