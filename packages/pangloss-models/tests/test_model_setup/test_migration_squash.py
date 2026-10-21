"""Squashing: one migration for a run of them"""

import importlib
import sys
from typing import no_type_check

import pytest
from migration_support import snapshot_of
from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations import changes as c
from pangloss_models.migrations import data_view, diff
from pangloss_models.migrations.files import (
    EMPTY_SNAPSHOT,
    Migration,
    MigrationGraph,
    discover,
    migrations_directory,
    squash,
    write,
)
from pangloss_models.migrations.history import pending, problems
from pangloss_models.model_bases.entity import Entity


@no_type_check
def versions():
    def v1():
        class Person(Entity):
            name: str

    def v2():
        class Person(Entity):
            name: str

        class Place(Entity):
            name: str

    def v3():
        class Person(Entity):
            name: str
            nickname: str | None

        class Place(Entity):
            name: str

    def v4():
        class Person(Entity):
            name: str
            nickname: str | None

        class Place(Entity):
            name: str
            country: str | None

    return [snapshot_of(v) for v in (v1, v2, v3, v4)]


def run_of_migrations(app="sq", dependencies=None) -> list[Migration]:
    snapshots = [EMPTY_SNAPSHOT, *versions()]
    migrations = []
    for number, (old, new) in enumerate(zip(snapshots, snapshots[1:]), start=1):
        migrations.append(
            Migration(
                app=app,
                name=f"{number:04d}_{'initial' if number == 1 else 'step'}",
                changes=tuple(diff(old, new).changes),
                dependencies=tuple((dependencies or {}).get(number, ())),
                schema_hash=f"hash{number}",
            )
        )
    return migrations


def key(app, n):
    return (app, run_of_migrations(app)[n - 1].name)


def test_a_run_from_the_start_is_squashed_to_the_changes_between_the_models():
    migrations = run_of_migrations()
    graph = MigrationGraph.of(migrations)
    squashed = squash(graph, "sq", "0001", "0004")

    assert squashed.name == "0001_squashed_0004_step"
    assert squashed.replaces == tuple(m.key for m in migrations)
    assert squashed.schema_hash == "hash4"
    # (models made with all their fields, not made and then changed)
    assert [type(ch) for ch in squashed.changes] == [c.CreateModel, c.CreateModel]
    assert len(squashed.changes) < sum(len(m.changes) for m in migrations)
    assert MigrationGraph.of([squashed]).state() == graph.state()


def test_a_run_in_the_middle_keeps_its_changes_as_they_were():
    migrations = run_of_migrations()
    graph = MigrationGraph.of(migrations)
    squashed = squash(graph, "sq", "0002", "0004")
    # (there is data of the models from before: what was done to it is kept)
    assert list(squashed.changes) == [ch for m in migrations[1:] for ch in m.changes]
    assert squashed.replaces == tuple(m.key for m in migrations[1:])
    assert MigrationGraph.of([migrations[0], squashed]).state() == graph.state()


def test_changes_by_hand_are_kept_even_from_the_start():
    migrations = run_of_migrations()
    migrations[2] = Migration(
        app="sq",
        name=migrations[2].name,
        changes=(*migrations[2].changes, c.RunCypher(query="MATCH (n) SET n.x = 1")),
        schema_hash="hash3",
    )
    squashed = squash(MigrationGraph.of(migrations), "sq", "0001", "0004", optimize=True)
    assert list(squashed.changes) == [ch for m in migrations for ch in m.changes]


def test_the_options_can_keep_every_change():
    migrations = run_of_migrations()
    squashed = squash(MigrationGraph.of(migrations), "sq", "0001", "0004", optimize=False)
    assert list(squashed.changes) == [ch for m in migrations for ch in m.changes]


def test_what_cannot_be_squashed_is_said():
    graph = MigrationGraph.of(run_of_migrations())
    with pytest.raises(PanglossMigrationError, match="nothing to squash"):
        squash(graph, "sq", "0002", "0002")
    with pytest.raises(PanglossMigrationError, match="not a run"):
        squash(graph, "sq", "0003", "0001")
    with pytest.raises(PanglossMigrationError, match="not one migration"):
        squash(graph, "sq", "0001", "0009")

    squashed = squash(graph, "sq", "0001", "0003")
    again = MigrationGraph.of([*run_of_migrations(), squashed])
    with pytest.raises(PanglossMigrationError, match="squashed"):
        squash(again, "sq", "0001_squashed_0003_step", "0004")


def test_the_squashed_migration_stands_in_for_the_originals_with_no_record():
    migrations = run_of_migrations()
    squashed = squash(MigrationGraph.of(migrations), "sq", "0001", "0003")
    graph = MigrationGraph.of([*migrations, squashed])

    # (the later migration follows it, and the originals are not there to be run)
    assert [m.name for m in graph.order()] == ["0001_squashed_0003_step", "0004_step"]
    assert [m.name for m in pending(graph, {})] == ["0001_squashed_0003_step", "0004_step"]
    assert graph.state() == MigrationGraph.of(migrations).state()


def applied_record(*names, status="applied"):
    return {("sq", name): {"status": status, "checksum": "x"} for name in names}


def test_a_database_that_had_all_the_originals_has_the_squashed_one():
    migrations = run_of_migrations()
    squashed = squash(MigrationGraph.of(migrations), "sq", "0001", "0003")
    record = applied_record("0001_initial", "0002_step", "0003_step")

    graph = MigrationGraph.of([*migrations, squashed], record)
    view = graph.reconcile(record)
    assert set(view) == {("sq", squashed.name)}
    assert problems(graph, view) == []
    assert [m.name for m in pending(graph, view)] == ["0004_step"]


def test_a_database_that_had_the_originals_before_they_were_deleted():
    migrations = run_of_migrations()
    squashed = squash(MigrationGraph.of(migrations), "sq", "0001", "0003")
    record = applied_record("0001_initial", "0002_step", "0003_step")

    graph = MigrationGraph.of([squashed, migrations[3]], record)
    view = graph.reconcile(record)
    assert problems(graph, view) == []
    assert [m.name for m in pending(graph, view)] == ["0004_step"]


def test_a_database_part_way_through_the_originals_goes_on_with_them():
    migrations = run_of_migrations()
    squashed = squash(MigrationGraph.of(migrations), "sq", "0001", "0003")
    record = applied_record("0001_initial")

    graph = MigrationGraph.of([*migrations, squashed], record)
    assert [m.name for m in graph.order()] == ["0001_initial", "0002_step", "0003_step", "0004_step"]
    assert graph.reconcile(record) == record
    assert [m.name for m in pending(graph, record)] == ["0002_step", "0003_step", "0004_step"]

    # (the originals are needed: they cannot have been deleted)
    with pytest.raises(PanglossMigrationError, match="only begun"):
        MigrationGraph.of([squashed, migrations[3]], record)

    # a failed one is a beginning too
    graph = MigrationGraph.of(
        [*migrations, squashed], applied_record("0001_initial", status="failed")
    )
    assert "0001_initial" in [m.name for m in graph.order()]


def test_a_dependency_on_an_original_is_on_the_squashed_one():
    other = Migration(
        app="other", name="0001_initial", changes=(), dependencies=(("sq", "0002_step"),)
    )
    migrations = run_of_migrations()
    squashed = squash(MigrationGraph.of(migrations), "sq", "0001", "0003")

    graph = MigrationGraph.of([*migrations, squashed, other])
    assert graph.migrations[("other", "0001_initial")].dependencies == (("sq", squashed.name),)
    # (and on the last of the originals, where they are the ones used)
    part = applied_record("0001_initial")
    graph = MigrationGraph.of([*migrations, squashed, other], part)
    assert graph.migrations[("other", "0001_initial")].dependencies == (("sq", "0002_step"),)

    # the squashed migration depends on what the run did, outside the app
    with_dependency = run_of_migrations(dependencies={2: [("other", "0001_initial")]})
    free = Migration(app="other", name="0001_initial", changes=())
    squashed = squash(MigrationGraph.of([free, *with_dependency]), "sq", "0001", "0003")
    assert squashed.dependencies == (("other", "0001_initial"),)


@pytest.fixture
def app(tmp_path, monkeypatch):
    package = tmp_path / "squashapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    yield "squashapp"
    for name in [n for n in sys.modules if n.split(".")[0] == "squashapp"]:
        del sys.modules[name]


def test_a_squashed_migration_is_written_and_read_back(app):
    migrations = run_of_migrations(app=app)
    for migration in migrations:
        write(migration, migrations_directory(app))
    squashed = squash(MigrationGraph.of(migrations), app, "0001", "0003")
    path = write(squashed, migrations_directory(app))
    assert path.name == "0001_squashed_0003_step.py"
    assert "replaces" in path.read_text()

    found = discover(app)
    assert [m.name for m in found] == [
        "0001_initial",
        "0001_squashed_0003_step",
        "0002_step",
        "0003_step",
        "0004_step",
    ]
    loaded = next(m for m in found if m.replaces)
    assert loaded.replaces == squashed.replaces and loaded.number == 3
    assert loaded.changes == squashed.changes

    graph = MigrationGraph.of(found)
    assert [m.name for m in graph.order()] == ["0001_squashed_0003_step", "0004_step"]
    assert graph.state() == data_view(versions()[3])
