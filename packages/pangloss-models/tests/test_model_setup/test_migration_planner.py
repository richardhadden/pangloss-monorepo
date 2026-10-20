"""Making the migrations to write: what changed since the last, shared among the apps"""

import importlib
import sys
from typing import Annotated, no_type_check

import pytest
from migration_support import snapshot_of
from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations import changes as c
from pangloss_models.migrations import data_view
from pangloss_models.migrations.files import (
    MigrationGraph,
    graph_of,
    migrations_directory,
    write,
)
from pangloss_models.migrations.planner import app_of_module, plan
from pangloss_models.migrations.questions import (
    answers_needed,
    collect_questions,
    parse_value,
    with_answer,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation


@pytest.fixture
def apps(tmp_path, monkeypatch):
    """Two importable app packages, `appone` and `apptwo`"""
    for name in ("appone", "apptwo"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    yield ["appone", "apptwo"]
    for name in [n for n in sys.modules if n.split(".")[0] in ("appone", "apptwo")]:
        del sys.modules[name]


def in_app(snapshot: dict, **modules: str) -> dict:
    """The snapshot with each model said to be in a module (as where its class is)"""
    for model, module in modules.items():
        snapshot["models"][model]["module"] = module
    return snapshot


def write_all(migrations, apps_):
    for migration in migrations:
        write(migration, migrations_directory(migration.app))
    return graph_of(apps_)


def test_apps_are_found_from_modules():
    apps = ["a", "a.sub", "b"]
    assert app_of_module("a.models", apps) == "a"
    assert app_of_module("a.sub.models", apps) == "a.sub"
    assert app_of_module("b", apps) == "b"
    assert app_of_module("ab.models", apps) is None


@no_type_check
def test_the_first_migration_makes_everything(apps):
    def declare():
        class Person(Entity):
            name: str

        class Place(Entity):
            pass

    new = in_app(snapshot_of(declare), Person="appone.models", Place="appone.models")
    result = plan(MigrationGraph(), new, apps)
    assert result.is_final
    (migration,) = result.migrations
    assert (migration.app, migration.name) == ("appone", "0001_initial")
    assert {type(ch) for ch in migration.changes} == {c.CreateModel}
    assert migration.schema_hash

    graph = write_all(result.migrations, apps)
    assert graph.state() == data_view(new)
    # ... and the models are what the migrations come to: nothing to do
    assert plan(graph, new, apps).is_empty


@no_type_check
def test_a_later_change_is_a_later_migration(apps):
    def one():
        class Person(Entity):
            name: str

    def two():
        class Person(Entity):
            name: str
            born: int

    first = in_app(snapshot_of(one), Person="appone.models")
    graph = write_all(plan(MigrationGraph(), first, apps).migrations, apps)

    second = in_app(snapshot_of(two), Person="appone.models")
    result = plan(graph, second, apps)
    (migration,) = result.migrations
    assert migration.name.startswith("0002_addfield_person_born")
    assert [type(ch) for ch in migration.changes] == [c.AddField]

    # the answer a change needs goes in the change, and so in the file
    def answer(changes, old):
        return [with_answer(ch, "default", 1900) for ch in changes]

    answered = plan(graph, second, apps, answer=answer)
    graph = write_all(answered.migrations, apps)
    assert graph.leaf("appone").changes[0].default == 1900
    assert plan(graph, second, apps).is_empty


@no_type_check
def test_a_rename_is_a_question_until_it_is_answered(apps):
    def one():
        class Person(Entity):
            born: int

    def two():
        class Person(Entity):
            birth_year: int

    first = in_app(snapshot_of(one), Person="appone.models")
    graph = write_all(plan(MigrationGraph(), first, apps).migrations, apps)
    second = in_app(snapshot_of(two), Person="appone.models")

    result = plan(graph, second, apps)
    assert not result.is_final
    assert result.migrations == []
    question = result.questions[0]

    done = plan(graph, second, apps, confirmed=[question])
    assert [type(ch) for ch in done.migrations[0].changes] == [c.RenameField]


@no_type_check
def test_changes_are_shared_among_the_apps_and_the_migrations_depend_on_each_other(apps):
    """A statement (in one app) that is a relation to a person made by the other: the second
    app's migration comes after the first's"""

    def declare():
        class Person(Entity):
            pass

        class IdentifiedAs[T](ReifiedRelation[T]):
            certainty: int

        class Statement(Document):
            person: IdentifiedAs[Person]

    new = in_app(
        snapshot_of(declare),
        Person="appone.models",
        IdentifiedAs="appone.models",
        Statement="apptwo.models",
    )
    result = plan(MigrationGraph(), new, apps)
    by_app = {m.app: m for m in result.migrations}
    assert set(by_app) == {"appone", "apptwo"}
    assert ("appone", "0001_initial") in by_app["apptwo"].dependencies
    assert by_app["appone"].dependencies == ()
    # in the order they can be applied
    assert [m.app for m in result.migrations] == ["appone", "apptwo"]

    graph = write_all(result.migrations, apps)
    assert graph.state() == data_view(new)
    assert [str(m) for m in graph.order()] == ["appone.0001_initial", "apptwo.0001_initial"]

    # a later change to the model of the second app goes in the second
    def later():
        class Person(Entity):
            pass

        class IdentifiedAs[T](ReifiedRelation[T]):
            certainty: int

        class Statement(Document):
            person: IdentifiedAs[Person]
            text: str | None

    newer = in_app(
        snapshot_of(later),
        Person="appone.models",
        IdentifiedAs="appone.models",
        Statement="apptwo.models",
    )
    result = plan(graph, newer, apps)
    assert [(m.app, m.name[:4]) for m in result.migrations] == [("apptwo", "0002")]


@no_type_check
def test_models_that_need_each_other_in_two_apps_cannot_be_shared(apps):
    def declare():
        class Place(Entity):
            lived_here: list[Person]

        class Person(Entity):
            home: Place

    new = in_app(snapshot_of(declare), Place="appone.models", Person="apptwo.models")
    with pytest.raises(PanglossMigrationError, match="circle|depend on each other"):
        plan(MigrationGraph(), new, apps)


# ---------------------------------------------------------------------------
# What a person is asked
# ---------------------------------------------------------------------------


@no_type_check
def test_a_new_required_field_asks_for_a_value():
    def one():
        class Person(Entity):
            name: str

    def two():
        class Person(Entity):
            name: str
            born: int
            aliases: list[str]
            nickname: str | None

    old, new = snapshot_of(one), snapshot_of(two)
    from pangloss_models.migrations import diff

    changes = diff(old, new).changes
    # (the required int is asked; a list starts empty, and an optional field needs nothing)
    names = [changes[i].name for i, _ in collect_questions(changes, old)]
    assert names == ["born"]
    (question,) = [q for _, q in collect_questions(changes, old)]
    assert question.field == "default"
    assert question.descriptor == {"type": "int"}
    assert parse_value("1900", question.descriptor, {}) == 1900


@no_type_check
def test_the_fields_of_a_wrapper_are_asked_for():
    def one():
        class Person(Entity):
            pass

        class Statement(Document):
            person: Person

    def two():
        class IdentifiedAs[T](ReifiedRelation[T]):
            certainty: int
            note: str | None

        class Person(Entity):
            pass

        class Statement(Document):
            person: IdentifiedAs[Person]

    from pangloss_models.migrations import diff

    old, new = snapshot_of(one), snapshot_of(two)
    changes = diff(old, new).changes
    asked = collect_questions(changes, old)
    assert [(changes[i].kind, q.field) for i, q in asked] == [("WrapRelation", "defaults.certainty")]

    answered = with_answer(changes[1], "defaults.certainty", 3)
    assert answered.defaults == {"certainty": 3}
    assert collect_questions([changes[0], answered], old) == []


def test_answers_are_parsed_by_type():
    from pangloss_models.exceptions import PanglossMigrationError

    enums = {"Colour": {"members": [{"name": "RED", "value": "red"}]}}
    assert parse_value("3.5", {"type": "float"}, enums) == 3.5
    assert parse_value("yes", {"type": "bool"}, enums) is True
    assert parse_value("2020-01-02", {"type": "date"}, enums) == "2020-01-02"
    assert parse_value("red", {"type": "enum", "enum": "Colour"}, enums) == "RED"
    assert parse_value("a, b", {"type": "list", "item": {"type": "str"}}, enums) == ["a", "b"]
    with pytest.raises(PanglossMigrationError):
        parse_value("x", {"type": "int"}, enums)
    with pytest.raises(PanglossMigrationError):
        parse_value("blue", {"type": "enum", "enum": "Colour"}, enums)


@no_type_check
def test_what_the_new_wrapper_or_the_embedded_object_has_more_is_asked():
    from pangloss_models.migrations import diff
    from pangloss_models.model_bases.embedded import Embedded

    def one():
        class IdentifiedAs[T](ReifiedRelation[T]):
            certainty: int

        class Person(Entity):
            pass

        class Statement(Document):
            person: IdentifiedAs[Person]
            when: str

    def two():
        class ProxyFor[T](ReifiedRelation[T]):
            certainty: int
            reason: str

        class Date(Embedded):
            when: str
            precision: int

        class Person(Entity):
            pass

        class Statement(Document):
            person: ProxyFor[Person]
            date: Date

    old, new = snapshot_of(one), snapshot_of(two)
    changes = diff(old, new, declined=[
        c.PossibleRename(what="model", old="IdentifiedAs", new="ProxyFor"),
    ]).changes
    asked = {(changes[i].kind, q.field) for i, q in collect_questions(changes, old)}
    # the field the old wrapper has not; and what the embedded object has besides the literals
    assert ("ChangeWrapper", "defaults.reason") in asked
    assert ("LiteralsToEmbedded", "defaults.precision") in asked
