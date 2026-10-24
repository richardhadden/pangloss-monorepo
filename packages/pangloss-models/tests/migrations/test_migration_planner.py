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
def test_changes_are_shared_among_the_apps_and_the_migrations_depend_on_each_other(
    apps,
):
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
    assert [str(m) for m in graph.order()] == [
        "appone.0001_initial",
        "apptwo.0001_initial",
    ]

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


def names_of(result):
    return [(m.app, m.name[:4], sorted(m.dependencies)) for m in result.migrations]


@no_type_check
def test_models_that_need_each_other_in_two_apps_are_made_in_two_steps(apps):
    def declare():
        class Place(Entity):
            lived_here: list[Person]

        class Person(Entity):
            home: Place

    new = in_app(snapshot_of(declare), Place="appone.models", Person="apptwo.models")
    result = plan(MigrationGraph(), new, apps)
    # one app makes its models and the other's follow (they need the first); then the first adds
    # the fields that refer to the second's, which exist by then
    assert len(result.migrations) == 3
    steps = [
        (m.app, m.name[:4], [ch.kind for ch in m.changes]) for m in result.migrations
    ]
    assert sorted(a for a, _, _ in steps) == ["appone", "appone", "apptwo"]
    late = [m for m in result.migrations if m.name.startswith("0002")][0]
    assert all(ch.kind == "AddField" for ch in late.changes)
    assert late.dependencies  # (on the other's first)

    # the models come out as declared, written and read back, and nothing is left to make
    graph = write_all(result.migrations, apps)
    assert graph.state() == data_view(new)
    assert plan(graph, new, apps).is_empty


@no_type_check
def test_three_apps_that_need_each_other_round_a_circle(apps, tmp_path, monkeypatch):
    (tmp_path / "appthree").mkdir()
    (tmp_path / "appthree" / "__init__.py").write_text("")
    importlib.invalidate_caches()
    three = [*apps, "appthree"]

    def declare():
        class A(Entity):
            b: B

        class B(Entity):
            c: C

        class C(Entity):
            a: A

    new = in_app(
        snapshot_of(declare), A="appone.models", B="apptwo.models", C="appthree.models"
    )
    result = plan(MigrationGraph(), new, three)
    graph = write_all(result.migrations, three)
    assert graph.state() == data_view(new)
    assert plan(graph, new, three).is_empty
    for name in [n for n in sys.modules if n.startswith("appthree")]:
        del sys.modules[name]


@no_type_check
def test_models_that_only_one_needs_are_made_in_one_step_each(apps):
    def declare():
        class Place(Entity):
            pass

        class Person(Entity):
            home: Place

    new = in_app(snapshot_of(declare), Place="appone.models", Person="apptwo.models")
    result = plan(MigrationGraph(), new, apps)
    assert names_of(result) == [
        ("appone", "0001", []),
        ("apptwo", "0001", [("appone", result.migrations[0].name)]),
    ]


@no_type_check
def test_a_field_added_between_models_that_exist_depends_on_the_other_app(apps):
    def before():
        class Place(Entity):
            pass

        class Person(Entity):
            name: str

    def after():
        class Place(Entity):
            visitors: list[Person]

        class Person(Entity):
            name: str
            home: Place

    modules = dict(Place="appone.models", Person="apptwo.models")
    graph = write_all(
        plan(MigrationGraph(), in_app(snapshot_of(before), **modules), apps).migrations,
        apps,
    )
    new = in_app(snapshot_of(after), **modules)
    result = plan(graph, new, apps)
    graph = write_all(result.migrations, apps)
    assert graph.state() == data_view(new)
    assert plan(graph, new, apps).is_empty


@no_type_check
def test_a_model_moved_to_another_app_needs_no_migration_and_its_later_changes_follow_it(
    apps,
):
    def v1():
        class Person(Entity):
            name: str

    def v2():
        class Person(Entity):
            name: str
            born: int | None

    graph = write_all(
        plan(
            MigrationGraph(), in_app(snapshot_of(v1), Person="appone.models"), apps
        ).migrations,
        apps,
    )
    # the class is in another app now: that is not stored, so nothing has changed
    moved = in_app(snapshot_of(v1), Person="apptwo.models")
    assert plan(graph, moved, apps).is_empty

    # ... and a change to it afterwards is the new app's, which follows the first
    result = plan(graph, in_app(snapshot_of(v2), Person="apptwo.models"), apps)
    assert [(m.app, m.dependencies) for m in result.migrations] == [
        ("apptwo", (("appone", graph.leaf("appone").name),))
    ]
    graph = write_all(result.migrations, apps)
    assert graph.state() == data_view(snapshot_of(v2))


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
    assert [(changes[i].kind, q.field) for i, q in asked] == [
        ("WrapRelation", "defaults.certainty")
    ]

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
    assert parse_value("a, b", {"type": "list", "item": {"type": "str"}}, enums) == [
        "a",
        "b",
    ]
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
    changes = diff(
        old,
        new,
        declined=[
            c.PossibleRename(what="model", old="IdentifiedAs", new="ProxyFor"),
        ],
    ).changes
    asked = {(changes[i].kind, q.field) for i, q in collect_questions(changes, old)}
    # the field the old wrapper has not; and what the embedded object has besides the literals
    assert ("ChangeWrapper", "defaults.reason") in asked
    assert ("LiteralsToEmbedded", "defaults.precision") in asked


@no_type_check
def test_the_migrations_of_one_app_come_with_those_of_others_that_they_need(apps):
    from pangloss_models.migrations.planner import app_of_change, with_what_they_need

    def declare():
        class Place(Entity):
            pass

        class Person(Entity):
            home: Place

        class Thing(Entity):
            pass

    new = in_app(
        snapshot_of(declare),
        Place="appone.models",
        Person="apptwo.models",
        Thing="appone.models",
    )
    result = plan(MigrationGraph(), new, apps)
    # (apptwo's migration needs appone's, so it cannot be written without it)
    assert [m.app for m in with_what_they_need(result.migrations, "apptwo")] == [
        "appone",
        "apptwo",
    ]
    # (and appone's needs nothing)
    assert [m.app for m in with_what_they_need(result.migrations, "appone")] == [
        "appone"
    ]

    owners = MigrationGraph().owners()
    where = {
        ch.model: app_of_change(ch, new, owners, apps)
        for ch in result.changes
        if isinstance(ch, c.CreateModel)
    }
    assert where == {"Place": "appone", "Thing": "appone", "Person": "apptwo"}


@no_type_check
def test_changing_the_kind_of_a_model_or_a_field_is_refused(apps):
    from pangloss_models.exceptions import PanglossMigrationNotSupported

    def entity():
        class Thing(Entity):
            name: str

    def document():
        class Thing(Document):
            name: str

    first = in_app(snapshot_of(entity), Thing="appone.models")
    graph = write_all(plan(MigrationGraph(), first, apps).migrations, apps)

    with pytest.raises(
        PanglossMigrationNotSupported, match="kind of a model cannot be changed"
    ):
        plan(graph, in_app(snapshot_of(document), Thing="appone.models"), apps)


def test_changing_the_kind_of_a_field_is_refused_too():
    from pangloss_models.exceptions import PanglossMigrationNotSupported
    from pangloss_models.migrations.planner import refuse_kind_changes

    with pytest.raises(
        PanglossMigrationNotSupported, match="kind of a field cannot be changed"
    ):
        refuse_kind_changes(
            [
                c.ChangeFieldKind(
                    model="Thing", name="home", old="literal", new="relation"
                )
            ]
        )
    refuse_kind_changes(
        [c.AddField(model="Thing", name="x", field_kind="literal", needs_value=False)]
    )


@no_type_check
def test_a_new_embedded_object_asks_for_the_values_it_requires():
    from pangloss_models.migrations import diff
    from pangloss_models.model_bases.embedded import Embedded

    def before():
        class Statement(Document):
            text: str

    def after():
        class Date(Embedded):
            when: str
            precision: int | None

        class Statement(Document):
            text: str
            date: Date

    old, new = snapshot_of(before), snapshot_of(after)
    found = diff(old, new).changes
    added = next(ch for ch in found if isinstance(ch, c.AddField) and ch.name == "date")
    asked = [
        q
        for _, q in collect_questions(found, data_view(old))
        if q.field.startswith("default")
    ]
    assert [q.field for q in asked] == ["default.when"]  # (`precision` may be left out)

    answered = with_answer(added, "default.when", "unknown")
    assert answered.default == {"when": "unknown"}


@no_type_check
def test_a_model_that_fulfils_a_class_of_another_app_depends_on_that_app(apps):
    from pangloss_models.field_definitions import FieldSubclassing
    from pangloss_models.model_bases.configs import RelationConfig
    from pangloss_models.model_bases.helpers import Fulfils

    def plain():
        class Person(Entity):
            pass

        class Place(Entity):
            pass

        class Dated(Document):
            who: Person
            place: Place

        class Meeting(Document):
            attendee: Person
            place: Place

    def fulfilling():
        class Person(Entity):
            pass

        class Place(Entity):
            pass

        class Dated(Document):
            who: Person
            place: Place

        class Meeting(Document, Fulfils[Dated]):
            attendee: Annotated[
                Person,
                RelationConfig(
                    subclasses_parent_fields=[
                        FieldSubclassing("who", field_on_model=Dated)
                    ]
                ),
            ]

    modules = dict(
        Person="appone.models",
        Place="appone.models",
        Dated="appone.models",
        Meeting="apptwo.models",
    )
    graph = write_all(
        plan(MigrationGraph(), in_app(snapshot_of(plain), **modules), apps).migrations,
        apps,
    )

    new = in_app(snapshot_of(fulfilling), **modules)
    result = plan(graph, new, apps)
    recompute = [
        (m.app, m.dependencies)
        for m in result.migrations
        if any(isinstance(ch, c.RecomputeFulfils) for ch in m.changes)
    ]
    # (it is Meeting's, so apptwo's; and it needs what Dated is, which is appone's)
    assert [app for app, _ in recompute] == ["apptwo"]
    assert ("appone", graph.leaf("appone").name) in recompute[0][1]

    graph = write_all(result.migrations, apps)
    assert graph.state() == data_view(new)
    assert plan(graph, new, apps).is_empty


@no_type_check
def test_apps_whose_models_inherit_from_each_other_round_a_circle_are_made_in_two_steps(
    apps,
):
    def declare():
        class Base(Document):
            pass

        class Child2(Document):
            pass

        class Child(Base):
            pass

        class Holder(Child2):
            pass

    new = in_app(
        snapshot_of(declare),
        Base="apptwo.models",
        Holder="apptwo.models",
        Child="appone.models",
        Child2="appone.models",
    )
    result = plan(MigrationGraph(), new, apps)
    # appone's Child needs apptwo's Base (to inherit from) and apptwo's Holder needs appone's Child2
    kinds = {
        (m.app, m.name[:4]): [type(ch).__name__ for ch in m.changes]
        for m in result.migrations
    }
    assert any("AlterModelLabels" in changes for changes in kinds.values())

    graph = write_all(result.migrations, apps)
    assert graph.state() == data_view(new)
    assert plan(graph, new, apps).is_empty
    labels = graph.state()["models"]["Child"]["labels"]
    assert "Base" in labels and "Child" in labels


def test_a_circle_that_cannot_be_split_is_an_error_and_not_an_endless_loop(monkeypatch):
    from pangloss_models.migrations import planner

    def create(name):
        return c.CreateModel(
            model=name,
            model_kind="Document",
            definition={"fields": [], "labels": [name]},
        )

    groups = {"one": [create("A")], "two": [create("B")]}
    created = {"A": "one", "B": "two"}
    # (each is said to need the other's, and nothing can be moved)
    monkeypatch.setattr(planner, "cyclic_apps", lambda *args: {"one", "two"})
    monkeypatch.setattr(planner, "split_app", lambda group, app, created: (group, []))
    with pytest.raises(PanglossMigrationError, match="need each other"):
        planner.layers_of(groups, created, set())
