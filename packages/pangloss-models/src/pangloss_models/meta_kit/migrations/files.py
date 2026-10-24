"""Migrations as files: what `makemigrations` writes and `migrate` reads.

A migration is a module in the `migrations` package of an app (`demo_app/migrations/0002_x.py`)
with these names:

    dependencies = [("demo_app", "0001_initial")]   # migrations that come first, of any app
    schema_hash = "..."                              # the snapshot of the models after it
    atomic = True                                    # (optional)
    batch_size = 1000                                # (optional: in batches of this many nodes)
    replaces = [("app", "0001_initial"), ...]        # (optional: a squashed migration)
    changes = changes_from_data([{...}, ...])        # what it does, in order

It is Python, to read and to edit: the answers a change needs (a default, what to do with what
does not convert) are filled in by editing it, and a change that cannot be generated is added by
hand. `checksum` is of the changes as written, so that editing one that was applied is noticed.
"""

import copy
import dataclasses
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
from pangloss_models.meta_kit.migrations import changes as c
from pangloss_models.meta_kit.migrations.snapshot import data_view
from pangloss_models.meta_kit.migrations.state import apply_change

MIGRATION_NAME = re.compile(r"^(\d{4})_\w+$")
SQUASHED_NAME = re.compile(r"^(\d{4})_squashed_(\d{4})_\w+$")
EMPTY_SNAPSHOT: dict[str, Any] = {
    "version": 1,
    "models": {},
    "enums": {},
    "indexes": [],
    "constraints": [],
}


def changes_from_data(data: Iterable[dict[str, Any] | c.Change]) -> list[c.Change]:
    """The changes of a migration file, from the data they are written as (or changes, for one
    written by hand: `RunCypher(...)`)"""
    return [
        entry if isinstance(entry, c.Change) else c.change_from_dict(entry)
        for entry in data
    ]


def structure_id(change: c.Change) -> str:
    """What an index or constraint is known by, among the owners of migrations"""
    entry = getattr(change, "index", None) or change.constraint
    return f"{entry.get('kind')}:{entry['label']}({','.join(entry['properties'])}){entry.get('name', '')}"


def checksum_of(changes: Iterable[c.Change]) -> str:
    canonical = json.dumps(
        [change.to_dict() for change in changes], sort_keys=True, default=str
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class Migration:
    app: str
    name: str
    changes: tuple[c.Change, ...]
    dependencies: tuple[tuple[str, str], ...] = ()
    schema_hash: str = ""
    atomic: bool = True
    # In batches of this many nodes (None: `atomic` says whether in batches at all, and how big)
    batch_size: int | None = None
    # The migrations it stands in for, if it is a squashed one (see `squash`)
    replaces: tuple[tuple[str, str], ...] = ()

    @property
    def key(self) -> tuple[str, str]:
        return (self.app, self.name)

    @property
    def number(self) -> int:
        """Where it comes in its app: for a squashed migration, that of the last it replaces"""
        squashed = SQUASHED_NAME.match(self.name)
        if squashed:
            return int(squashed.group(2))
        match = MIGRATION_NAME.match(self.name)
        return int(match.group(1)) if match else 0

    @property
    def first_number(self) -> int:
        """Where it begins in its app: for a squashed migration, that of the first it replaces"""
        squashed = SQUASHED_NAME.match(self.name)
        return int(squashed.group(1)) if squashed else self.number

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
    lines = [
        f'"""{summary or migration.name}',
        "",
        "Made by `pangloss makemigrations`; the answers a change needs may be filled in here.",
        '"""',
        "",
    ]
    lines.append(
        "from pangloss_models.meta_kit.migrations.files import changes_from_data"
    )
    lines.append("")
    lines.append(
        f"dependencies = {_pformat([list(d) for d in migration.dependencies])}"
    )
    lines.append(f"schema_hash = {migration.schema_hash!r}")
    if not migration.atomic:
        lines.append("atomic = False")
    if migration.batch_size:
        lines.append(f"batch_size = {migration.batch_size}")
    if migration.replaces:
        lines.append(f"replaces = {_pformat([list(r) for r in migration.replaces])}")
    lines.append("")
    data = [change.to_dict() for change in migration.changes]
    if not data:
        lines += EMPTY_HINT
    lines.append(f"changes = changes_from_data({_pformat(data)})")
    lines.append("")
    return "\n".join(lines)


EMPTY_HINT = [
    "# Changes written by hand go here (import them from pangloss_models.meta_kit.migrations.changes):",
    "# queries, or functions of this app, and, when a change of",
    "# the models was refused (`[NEEDS CODE]`), its data moved first and the models after it:",
    "#",
    "#     RunCypher(query='MATCH (n:Person) SET n.born = $year', parameters={'year': 1900}),",
    "#     RunPython(function='myapp.migrations.helpers:move_names'),   # def f(tx, state)",
    "#     StateOnly(changes=(AlterLiteralType(model='Event', name='when', old={'type': 'datetime'}, new={'type': 'str'}),)),",
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
    importlib.reload(
        module
    )  # (it may have been edited, or written, since it was imported)
    try:
        changes = tuple(module.changes)
    except AttributeError:
        raise PanglossMigrationError(
            f"{app}.migrations.{name} has no `changes`"
        ) from None
    return Migration(
        app=app,
        name=name,
        changes=changes,
        dependencies=tuple(tuple(d) for d in getattr(module, "dependencies", [])),  # type: ignore[misc]
        schema_hash=getattr(module, "schema_hash", ""),
        atomic=getattr(module, "atomic", True),
        batch_size=getattr(module, "batch_size", None),
        replaces=tuple(tuple(r) for r in getattr(module, "replaces", [])),  # type: ignore[misc]
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
    # The squashed migrations that are used, and the originals they stand in for
    stands_for: dict[tuple[str, str], tuple[tuple[str, str], ...]] = field(
        default_factory=dict
    )
    # Every squashed migration there is, used or not, and what each replaces
    squashed: dict[tuple[str, str], tuple[tuple[str, str], ...]] = field(
        default_factory=dict
    )

    @classmethod
    def of(
        cls,
        migrations: Iterable[Migration],
        applied: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> MigrationGraph:
        """The graph of the migrations. Where a squashed migration and the migrations it replaces
        are both there, one set is used: the squashed migration, unless the database (`applied`)
        has begun on the originals and not finished them"""
        migrations = list(migrations)
        chosen, stands_for = choose(migrations, applied)
        graph = cls(
            {m.key: m for m in chosen},
            stands_for,
            {m.key: m.replaces for m in migrations if m.replaces},
        )
        graph.check()
        return graph

    def reconcile(
        self, applied: dict[tuple[str, str], dict[str, Any]]
    ) -> dict[tuple[str, str], dict[str, Any]]:
        """The record of the database as the graph reads it: a squashed migration whose originals
        were all applied (or that was itself applied) is applied, and the originals are not there to
        be compared"""
        full = expanded(applied, self.squashed)
        view = dict(applied)
        for key, originals in self.stands_for.items():
            if originals and all(
                full.get(o, {}).get("status") == "applied" for o in originals
            ):
                for original in originals:
                    view.pop(original, None)
                # (keep its own record, if it has one)
                view.setdefault(
                    key,
                    {
                        "status": "applied",
                        "checksum": None,
                        "replaces_applied": list(originals),
                    },
                )
        return view

    def parents(self, migration: Migration) -> list[tuple[str, str]]:
        """What comes before it: its dependencies, and the migration before it in its app"""
        earlier = [
            m.key
            for m in self.migrations.values()
            if m.app == migration.app and m.number < migration.number
        ]
        previous = (
            [max(earlier, key=lambda key: self.migrations[key].number)]
            if earlier
            else []
        )
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
                key
                for key, m in remaining.items()
                if all(p in placed for p in self.parents(m))
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
        wanted = None if upto is None else self.closure(upto)
        snapshot = copy.deepcopy(EMPTY_SNAPSHOT)
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
                    owners[
                        change.model
                        if isinstance(change, c.CreateModel)
                        else change.enum
                    ] = migration.app
                elif isinstance(change, (c.RenameModel, c.RenameEnum)):
                    owners[change.new] = owners.pop(change.old, migration.app)
                elif isinstance(change, (c.AddIndex, c.AddConstraint)):
                    owners[structure_id(change)] = migration.app
                elif isinstance(change, (c.RemoveIndex, c.RemoveConstraint)):
                    owners.pop(structure_id(change), None)
                elif isinstance(change, (c.DeleteModel, c.RemoveEnum)):
                    owners.pop(
                        change.model
                        if isinstance(change, c.DeleteModel)
                        else change.enum,
                        None,
                    )
        return owners

    def closure(self, keys: Iterable[tuple[str, str]]) -> set[tuple[str, str]]:
        wanted: set[tuple[str, str]] = set()
        pending = list(keys)
        while pending:
            key = pending.pop()
            if key in wanted:
                continue
            wanted.add(key)
            pending.extend(self.parents(self.migrations[key]))
        return wanted


def expanded(
    applied: dict[tuple[str, str], dict[str, Any]],
    squashed: dict[tuple[str, str], tuple[tuple[str, str], ...]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """The record of a database with what a squashed migration means filled in: if it was applied,
    so were the migrations it replaces; and if they all were, so was it. (A database that applied a
    squashed migration, or the migrations that were squashed into it, has the same.)"""
    view = dict(applied)
    changed = True
    while changed:
        changed = False
        for key, originals in squashed.items():
            if view.get(key, {}).get("status") == "applied":
                for original in originals:
                    if original not in view:
                        view[original] = {
                            "status": "applied",
                            "checksum": None,
                            "implied": True,
                        }
                        changed = True
            elif key not in view and all(
                view.get(o, {}).get("status") == "applied" for o in originals
            ):
                view[key] = {"status": "applied", "checksum": None, "implied": True}
                changed = True
    return view


def choose(
    migrations: list[Migration], applied: dict[tuple[str, str], dict[str, Any]] | None
) -> tuple[list[Migration], dict[tuple[str, str], tuple[tuple[str, str], ...]]]:
    """Of each squashed migration and the migrations it replaces, those to use; and what the
    migrations that were left out are replaced by, for the dependencies on them. A squashed
    migration can be among those another replaces (it was squashed again): the outer one is used
    or not as the inner one was, and replaces everything."""
    by_key = {m.key: m for m in migrations}
    squashed_index = {m.key: m.replaces for m in migrations if m.replaces}
    if applied is not None:
        applied = expanded(applied, squashed_index)
    dropped: set[tuple[str, str]] = set()
    redirect: dict[tuple[str, str], tuple[str, str]] = {}
    stands_for: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}
    # (the ones that replace least first: what a squashed migration replaces is decided before it)
    for squashed in sorted(
        (m for m in migrations if m.replaces), key=lambda m: (len(m.replaces), m.key)
    ):
        originals = squashed.replaces
        records = [applied.get(o) for o in originals] if applied is not None else []
        began = any(record is not None for record in records)
        finished = all(
            record is not None and record.get("status") == "applied"
            for record in records
        )
        if began and not finished:
            # (the database is part way through them: they are used, as they are on disk)
            missing = [o for o in originals if o not in by_key]
            if missing:
                names = ", ".join(".".join(o) for o in missing)
                raise PanglossMigrationError(
                    f"{squashed} replaces migrations that the database has only begun, and their "
                    f"{'file is' if len(missing) == 1 else 'files are'} missing ({names}): "
                    "restore the files and finish them, then the squashed one can be used"
                )
            dropped.add(squashed.key)
            last = max((by_key[o] for o in originals), key=lambda m: m.number)
            redirect[squashed.key] = last.key
        else:
            dropped |= {o for o in originals if o in by_key}
            redirect.update({o: squashed.key for o in originals})
            stands_for[squashed.key] = originals
    stands_for = {
        key: originals for key, originals in stands_for.items() if key not in dropped
    }
    kept = []
    for migration in migrations:
        if migration.key in dropped:
            continue
        dependencies = tuple(
            dict.fromkeys(redirect.get(d, d) for d in migration.dependencies)
        )
        kept.append(
            migration
            if dependencies == migration.dependencies
            else dataclasses.replace(migration, dependencies=dependencies)
        )
    return kept, stands_for


def graph_of(
    apps: Iterable[str], applied: dict[tuple[str, str], dict[str, Any]] | None = None
) -> MigrationGraph:
    """The migrations of the apps (`applied` is the record of a database, which says which of a
    squashed migration and its originals are used)"""
    return MigrationGraph.of((m for app in apps for m in discover(app)), applied)


# --- squashing -------------------------------------------------------------------------------------


def squash(
    graph: MigrationGraph,
    app: str,
    first: str,
    last: str,
    name: str | None = None,
    optimize: bool = True,
) -> Migration:
    """One migration to stand in for those of `app` from `first` to `last` (their names, or
    numbers): it does what they do, and replaces them. A database that has had them all, or none of
    them, uses it; one part way through them goes on with them.

    Its changes are theirs in order, unless the run begins the app (so there is no data of its
    own in the way) and none of it is by hand: then they are the changes from the models before to
    those after, which is usually far fewer (a model created and then given fields is created with
    them)."""
    from pangloss_models.meta_kit.migrations.diff import diff
    from pangloss_models.meta_kit.migrations.history import resolve_target

    start, end = resolve_target(graph, app, first), resolve_target(graph, app, last)
    if start is None or end is None or start.number > end.number:
        raise PanglossMigrationError(
            f"{first} to {last} is not a run of migrations of {app}"
        )
    run = [
        m
        for m in graph.order()
        if m.app == app and start.number <= m.number <= end.number
    ]
    if len(run) < 2:
        raise PanglossMigrationError("There is nothing to squash in one migration")
    inside = {m.key for m in run}
    outside = [p for m in run for p in graph.parents(m) if p not in inside]
    # (the models as they are when the run begins, with everything it depends on)
    before = graph.state(outside) if outside else data_view(EMPTY_SNAPSHOT)
    changes: list[c.Change] = [change for m in run for change in m.changes]
    after = before
    for change in changes:
        after = apply_change(after, change)

    by_hand = any(
        isinstance(ch, (c.RunCypher, c.RunPython, c.StateOnly)) for ch in changes
    )
    first_of_app = not any(
        m.app == app and m.number < start.first_number
        for m in graph.migrations.values()
    )
    if optimize and first_of_app and not by_hand:
        found = diff(before, after)
        found = diff(
            before, after, declined=found.questions
        )  # (a rename is a removal and an addition)
        state = before
        for change in found.changes:
            state = apply_change(state, change)
        if state == data_view(after) and not any(
            isinstance(ch, (c.AlterModelKind, c.ChangeFieldKind))
            for ch in found.changes
        ):
            changes = found.changes
    squashed_end = SQUASHED_NAME.match(end.name)
    rest = end.name.split("_", 3)[3] if squashed_end else end.name.split("_", 1)[1]
    # (what it replaces: a squashed migration in the run, and the migrations that went into that)
    replaces = tuple(dict.fromkeys(key for m in run for key in (*m.replaces, m.key)))
    return Migration(
        app=app,
        name=name or f"{start.first_number:04d}_squashed_{end.number:04d}_{rest}",
        changes=tuple(changes),
        dependencies=tuple(dict.fromkeys(p for p in outside if p[0] != app)),
        schema_hash=end.schema_hash,
        atomic=all(m.atomic for m in run),
        batch_size=min((m.batch_size for m in run if m.batch_size), default=None),
        replaces=replaces,
    )
