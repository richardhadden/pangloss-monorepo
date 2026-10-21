"""Migrations as files: what `makemigrations` writes and `migrate` reads.

A migration is a module in the `migrations` package of an app (`demo_app/migrations/0002_x.py`)
with these names:

    dependencies = [("demo_app", "0001_initial")]   # migrations that come first, of any app
    schema_hash = "..."                              # the snapshot of the models after it
    atomic = True                                    # (optional)
    changes = changes_from_data([{...}, ...])        # what it does, in order

It is Python, to read and to edit: the answers a change needs (a default, what to do with what
does not convert) are filled in by editing it, and a change that cannot be generated is added by
hand. `checksum` is of the changes as written, so that editing one that was applied is noticed.
"""

import hashlib
import importlib
import json
import pkgutil
import pprint
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.snapshot import data_view
from pangloss_models.migrations.state import apply_change

MIGRATION_NAME = re.compile(r"^(\d{4})_\w+$")
EMPTY_SNAPSHOT: dict[str, Any] = {"version": 1, "models": {}, "enums": {}}


def changes_from_data(data: Iterable[dict[str, Any] | c.Change]) -> list[c.Change]:
    """The changes of a migration file, from the data they are written as (or changes, for one
    written by hand: `RunCypher(...)`)"""
    return [entry if isinstance(entry, c.Change) else c.change_from_dict(entry) for entry in data]


def checksum_of(changes: Iterable[c.Change]) -> str:
    canonical = json.dumps([change.to_dict() for change in changes], sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class Migration:
    app: str
    name: str
    changes: tuple[c.Change, ...]
    dependencies: tuple[tuple[str, str], ...] = ()
    schema_hash: str = ""
    atomic: bool = True

    @property
    def key(self) -> tuple[str, str]:
        return (self.app, self.name)

    @property
    def number(self) -> int:
        match = MIGRATION_NAME.match(self.name)
        return int(match.group(1)) if match else 0

    @property
    def checksum(self) -> str:
        return checksum_of(self.changes)

    def __str__(self) -> str:
        return f"{self.app}.{self.name}"


# --- writing -------------------------------------------------------------------------------------


def slug_of(changes: Sequence[c.Change], initial: bool = False) -> str:
    """A name for a migration from what it does"""
    if initial:
        return "initial"
    if not changes:
        return "empty"
    parts: list[str] = []
    for change in changes[:3]:
        words = [change.kind]
        for attribute in ("model", "enum", "name", "old", "new"):
            value = getattr(change, attribute, None)
            if isinstance(value, str):
                words.append(value)
        parts.append("_".join(words))
    slug = re.sub(r"[^a-z0-9_]+", "_", "_".join(parts).lower()).strip("_")
    slug = re.sub(r"(?<=_)([a-z])", lambda m: m.group(1), slug)
    return slug[:60].rstrip("_") or "auto"


def next_name(existing: Iterable[Migration], slug: str) -> str:
    number = max((m.number for m in existing), default=0) + 1
    return f"{number:04d}_{slug}"


def render(migration: Migration, summary: str | None = None) -> str:
    """The source of a migration file"""
    lines = [f'"""{summary or migration.name}', "", "Made by `pangloss makemigrations`; the answers a change needs may be filled in here.", '"""', ""]
    lines.append("from pangloss_models.migrations.files import changes_from_data")
    lines.append("")
    lines.append(f"dependencies = {_pformat([list(d) for d in migration.dependencies])}")
    lines.append(f"schema_hash = {migration.schema_hash!r}")
    if not migration.atomic:
        lines.append("atomic = False")
    lines.append("")
    data = [change.to_dict() for change in migration.changes]
    if not data:
        lines += EMPTY_HINT
    lines.append(f"changes = changes_from_data({_pformat(data)})")
    lines.append("")
    return "\n".join(lines)


EMPTY_HINT = [
    "# Changes written by hand go here (import them from pangloss_models.migrations.changes):",
    "# queries, or functions of this app, and, when a change of",
    "# the models was refused (`[NEEDS CODE]`), its data moved first and the models after it:",
    "#",
    "#     RunCypher(query='MATCH (n:Person) SET n.born = $year', parameters={'year': 1900}),",
    "#     RunPython(function='myapp.migrations.helpers:move_names'),   # def f(tx, state)",
    "#     StateOnly(changes=(AlterModelKind(model='Person', old='entity', new='document'),)),",
    "",
]


def _pformat(value: Any) -> str:
    return pprint.pformat(value, width=100, sort_dicts=False)


def write(migration: Migration, directory: Path, summary: str | None = None) -> Path:
    """Write a migration to the `migrations` directory of its app (made if it is not there)"""
    directory.mkdir(parents=True, exist_ok=True)
    init = directory / "__init__.py"
    if not init.exists():
        init.write_text("")
    path = directory / f"{migration.name}.py"
    if path.exists():
        raise PanglossMigrationError(f"{path} exists already")
    path.write_text(render(migration, summary))
    importlib.invalidate_caches()
    return path


# --- reading -------------------------------------------------------------------------------------


def load(app: str, name: str) -> Migration:
    module = importlib.import_module(f"{app}.migrations.{name}")
    importlib.reload(module)  # (it may have been edited, or written, since it was imported)
    try:
        changes = tuple(module.changes)
    except AttributeError:
        raise PanglossMigrationError(f"{app}.migrations.{name} has no `changes`") from None
    return Migration(
        app=app,
        name=name,
        changes=changes,
        dependencies=tuple(tuple(d) for d in getattr(module, "dependencies", [])),  # type: ignore[misc]
        schema_hash=getattr(module, "schema_hash", ""),
        atomic=getattr(module, "atomic", True),
    )


def migrations_directory(app: str) -> Path:
    """Where the migrations of an app are (or would be): beside its models"""
    package = importlib.import_module(app)
    paths = list(getattr(package, "__path__", []))
    if not paths:
        raise PanglossMigrationError(f"{app} is not a package")
    return Path(paths[0]) / "migrations"


def discover(app: str) -> list[Migration]:
    """The migrations of an app, in order (none if it has no `migrations` package)"""
    try:
        package = importlib.import_module(f"{app}.migrations")
    except ModuleNotFoundError as error:
        if error.name and f"{app}.migrations".startswith(error.name):
            return []
        raise
    names = sorted(
        info.name
        for info in pkgutil.iter_modules(package.__path__)
        if MIGRATION_NAME.match(info.name)
    )
    return [load(app, name) for name in names]


# --- the migrations together ------------------------------------------------------------------------


@dataclass
class MigrationGraph:
    migrations: dict[tuple[str, str], Migration] = field(default_factory=dict)

    @classmethod
    def of(cls, migrations: Iterable[Migration]) -> "MigrationGraph":
        graph = cls({m.key: m for m in migrations})
        graph.check()
        return graph

    def parents(self, migration: Migration) -> list[tuple[str, str]]:
        """What comes before it: its dependencies, and the migration before it in its app"""
        earlier = [
            m.key for m in self.migrations.values() if m.app == migration.app and m.number < migration.number
        ]
        previous = [max(earlier, key=lambda key: self.migrations[key].number)] if earlier else []
        return [*previous, *migration.dependencies]

    def check(self) -> None:
        for migration in self.migrations.values():
            for dependency in migration.dependencies:
                if dependency not in self.migrations:
                    raise PanglossMigrationError(
                        f"{migration} depends on {dependency[0]}.{dependency[1]}, which there is not"
                    )
        self.order()

    def order(self) -> list[Migration]:
        """All of them, each after what it depends on (in a steady order otherwise)"""
        remaining = dict(sorted(self.migrations.items()))
        done: list[Migration] = []
        placed: set[tuple[str, str]] = set()
        while remaining:
            ready = [
                key for key, m in remaining.items() if all(p in placed for p in self.parents(m))
            ]
            if not ready:
                raise PanglossMigrationError(
                    "The migrations depend on each other in a circle: "
                    + ", ".join(f"{app}.{name}" for app, name in remaining)
                )
            key = ready[0]
            done.append(remaining.pop(key))
            placed.add(key)
        return done

    def leaf(self, app: str) -> Migration | None:
        own = [m for m in self.migrations.values() if m.app == app]
        return max(own, key=lambda m: m.number) if own else None

    def state(self, upto: Iterable[tuple[str, str]] | None = None) -> dict[str, Any]:
        """The snapshot of the models after the migrations (all, or those given and what they
        need), made without the classes of the models"""
        wanted = None if upto is None else self._closure(upto)
        snapshot = {"version": 1, "models": {}, "enums": {}}
        for migration in self.order():
            if wanted is not None and migration.key not in wanted:
                continue
            for change in migration.changes:
                snapshot = apply_change(snapshot, change)
        return data_view(snapshot)

    def owners(self) -> dict[str, str]:
        """The app of each model and enum, as the migrations that made them say"""
        owners: dict[str, str] = {}
        for migration in self.order():
            for change in migration.changes:
                if isinstance(change, (c.CreateModel, c.CreateEnum)):
                    owners[getattr(change, "model", None) or change.enum] = migration.app  # type: ignore[attr-defined]
                elif isinstance(change, (c.RenameModel, c.RenameEnum)):
                    owners[change.new] = owners.pop(change.old, migration.app)
                elif isinstance(change, (c.DeleteModel, c.RemoveEnum)):
                    owners.pop(getattr(change, "model", None) or change.enum, None)  # type: ignore[attr-defined]
        return owners

    def _closure(self, keys: Iterable[tuple[str, str]]) -> set[tuple[str, str]]:
        wanted: set[tuple[str, str]] = set()
        pending = list(keys)
        while pending:
            key = pending.pop()
            if key in wanted:
                continue
            wanted.add(key)
            pending.extend(self.parents(self.migrations[key]))
        return wanted


def graph_of(apps: Iterable[str]) -> MigrationGraph:
    """The migrations of the apps"""
    return MigrationGraph.of(m for app in apps for m in discover(app))
