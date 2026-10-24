"""Migrations as files: written, read, ordered, and the state they come to"""

import importlib
import sys
from typing import no_type_check

import pytest
from migration_support import snapshot_of
from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.meta_kit.migrations import changes as c
from pangloss_models.meta_kit.migrations import data_view, diff, replay
from pangloss_models.meta_kit.migrations.files import (
    EMPTY_SNAPSHOT,
    Migration,
    MigrationGraph,
    discover,
    load,
    migrations_directory,
    next_name,
    slug_of,
    write,
)
from pangloss_models.model_bases.entity import Entity


@pytest.fixture
def app(tmp_path, monkeypatch):
    """An importable app package, `fileapp`, with no migrations"""
    package = tmp_path / "fileapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    yield "fileapp"
    for name in [n for n in sys.modules if n.split(".")[0] in ("fileapp", "otherapp")]:
        del sys.modules[name]


def migration_for(old, new, app="fileapp", name="0001_initial", dependencies=()):
    result = diff(old, new)
    return Migration(
        app=app,
        name=name,
        changes=tuple(result.changes),
        dependencies=tuple(dependencies),
    )


@no_type_check
def test_a_migration_is_written_and_read_back(app):
    def declare():
        class Person(Entity):
            name: str

    new = snapshot_of(declare)
    migration = migration_for(EMPTY_SNAPSHOT, new)
    path = write(migration, migrations_directory(app))
    assert path.name == "0001_initial.py"
    assert (path.parent / "__init__.py").exists()

    # it is Python that can be read, with the changes as data
    text = path.read_text()
    assert "changes = changes_from_data(" in text
    assert "'change': 'CreateModel'" in text

    loaded = load(app, "0001_initial")
    assert loaded.changes == migration.changes
    assert loaded.checksum == migration.checksum
    assert replay(EMPTY_SNAPSHOT, loaded.changes) == data_view(new)
    assert [m.name for m in discover(app)] == ["0001_initial"]


@no_type_check
def test_a_migration_is_not_written_over(app):
    migration = Migration(app=app, name="0001_initial", changes=())
    write(migration, migrations_directory(app))
    with pytest.raises(PanglossMigrationError, match="exists already"):
        write(migration, migrations_directory(app))


@no_type_check
def test_an_edited_migration_has_another_checksum(app):
    def declare():
        class Person(Entity):
            name: str

    migration = migration_for(EMPTY_SNAPSHOT, snapshot_of(declare))
    path = write(migration, migrations_directory(app))
    path.write_text(
        path.read_text().replace("'name': 'Person'", "'name': 'Persona'", 1)
    )
    assert load(app, "0001_initial").checksum != migration.checksum


def test_an_app_without_migrations_has_none(app):
    assert discover(app) == []
    assert discover("fileapp") == []


def test_names():
    assert next_name([], "initial") == "0001_initial"
    existing = [
        Migration(app="a", name="0001_initial", changes=()),
        Migration(app="a", name="0002_x", changes=()),
    ]
    assert next_name(existing, "more") == "0003_more"
    assert slug_of([], initial=True) == "initial"
    add = c.AddField(
        model="Person", name="born", field_kind="literal", needs_value=False
    )
    slug = slug_of([add])
    assert slug.startswith("addfield_person_born")
    assert " " not in slug and len(slug) <= 60


@no_type_check
def test_migrations_are_ordered_by_what_they_depend_on():
    a1 = Migration(app="a", name="0001_initial", changes=())
    a2 = Migration(
        app="a", name="0002_x", changes=(), dependencies=(("b", "0001_initial"),)
    )
    b1 = Migration(app="b", name="0001_initial", changes=())
    graph = MigrationGraph.of([a2, a1, b1])
    order = [str(m) for m in graph.order()]
    assert order.index("b.0001_initial") < order.index("a.0002_x")
    assert order.index("a.0001_initial") < order.index("a.0002_x")
    assert graph.leaf("a") is a2
    assert graph.leaf("nothing") is None


def test_a_dependency_that_there_is_not_is_an_error():
    lost = Migration(
        app="a", name="0001_initial", changes=(), dependencies=(("b", "0001_initial"),)
    )
    with pytest.raises(PanglossMigrationError, match="which there is not"):
        MigrationGraph.of([lost])


def test_migrations_that_depend_on_each_other_in_a_circle_are_an_error():
    a = Migration(
        app="a", name="0001_initial", changes=(), dependencies=(("b", "0001_initial"),)
    )
    b = Migration(
        app="b", name="0001_initial", changes=(), dependencies=(("a", "0001_initial"),)
    )
    with pytest.raises(PanglossMigrationError, match="circle"):
        MigrationGraph.of([a, b])


@no_type_check
def test_the_state_is_what_the_migrations_come_to_and_who_made_what():
    def one():
        class Person(Entity):
            name: str

    def two():
        class Person(Entity):
            name: str
            born: int | None

        class Place(Entity):
            pass

    s1, s2 = snapshot_of(one), snapshot_of(two)
    first = migration_for(EMPTY_SNAPSHOT, s1, app="a", name="0001_initial")
    second = migration_for(
        s1, s2, app="b", name="0001_initial", dependencies=(("a", "0001_initial"),)
    )
    graph = MigrationGraph.of([first, second])
    assert graph.state() == data_view(s2)
    assert graph.state([("a", "0001_initial")]) == data_view(s1)
    assert graph.owners() == {"Person": "a", "Place": "b"}


def test_a_migration_may_say_its_batch_size(app):
    migration = Migration(
        app="fileapp", name="0001_initial", changes=(), batch_size=250
    )
    path = write(migration, migrations_directory(app))
    assert "batch_size = 250" in path.read_text()
    assert load(app, "0001_initial").batch_size == 250
    assert Migration(app="a", name="0001_x", changes=()).batch_size is None
