"""The upgrade of a stored version, from migrations made by hand (no database)"""

import pytest
from pangloss_history import draft as draft_module
from pangloss_history import upgrade as module
from pangloss_history.store import HistoryRecord
from pangloss_history.upgrade import (
    CannotFindPosition,
    apply_migrations,
    migrations_after,
    upgrade,
)
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import Migration, MigrationGraph


def literal(name, type="str", nullable=False):
    return {
        "name": name,
        "kind": "literal",
        "type": {"type": type},
        "nullable": nullable,
        "required": True,
    }


def person(*fields):
    return {
        "name": "Person",
        "kind": "Entity",
        "labels": ["Person", "Entity"],
        "fields": list(fields),
    }


def migration(name, *changes, app="letters"):
    return Migration(app=app, name=name, changes=tuple(changes))


FIRST = migration(
    "0001_initial",
    c.CreateModel(
        model="Person", model_kind="Entity", definition=person(literal("name"))
    ),
)
GRAPH = MigrationGraph.of(
    [
        FIRST,
        migration(
            "0002_born",
            c.AddField(
                model="Person",
                name="born",
                field_kind="literal",
                needs_value=True,
                definition=literal("born", "int"),
                default=1900,
            ),
        ),
        migration("0003_by_hand", c.RunCypher(query="MATCH (n) RETURN n")),
    ]
)


@pytest.fixture(autouse=True)
def graph(monkeypatch):
    monkeypatch.setattr(module, "graph_of", lambda apps: GRAPH)


VERSION_ONE = {"type": "Person", "id": "1", "label": "Ann", "name": "Ann"}


def test_only_the_migrations_after_the_position_are_applied():
    pending, state = migrations_after(GRAPH, {"letters": "0001_initial"})
    assert [m.name for m in pending] == ["0002_born", "0003_by_hand"]
    assert [f["name"] for f in state["models"]["Person"]["fields"]] == ["name"]

    pending, state = migrations_after(GRAPH, {"letters": "0003_by_hand"})
    assert pending == [] and len(state["models"]["Person"]["fields"]) == 2


def test_a_version_is_upgraded_and_a_hand_written_migration_is_reported():
    result = upgrade(VERSION_ONE, {"letters": "0001_initial"}, ["letters"])
    assert result.data["born"] == 1900
    assert result.applied == ["letters.0002_born", "letters.0003_by_hand"]
    (problem,) = result.problems
    assert (problem.kind, problem.migration, problem.blocking) == (
        "hand-written-migration",
        "letters.0003_by_hand",
        True,
    )
    assert "born" not in VERSION_ONE  # (the stored version is not changed)


def test_a_version_at_the_latest_position_is_not_changed():
    result = upgrade(VERSION_ONE, {"letters": "0003_by_hand"}, ["letters"])
    assert result.data == VERSION_ONE and result.problems == []


def test_a_position_that_is_not_a_migration_cannot_be_upgraded():
    result = upgrade(VERSION_ONE, {"letters": "0009_gone"}, ["letters"])
    assert [p.kind for p in result.problems] == ["unknown-position"]
    assert result.data == VERSION_ONE
    with pytest.raises(CannotFindPosition):
        migrations_after(GRAPH, {"letters": "0009_gone"})


def test_a_required_field_added_with_no_value_is_a_problem_and_a_nullable_one_is_none():
    state = module.migrations_after(GRAPH, {"letters": "0001_initial"})[1]
    added = migration(
        "0004",
        c.AddField(
            model="Person",
            name="height",
            field_kind="literal",
            needs_value=True,
            definition=literal("height", "int"),
        ),
        c.AddField(
            model="Person",
            name="nickname",
            field_kind="literal",
            needs_value=False,
            definition=literal("nickname", nullable=True),
        ),
        c.AddField(
            model="Person",
            name="tags",
            field_kind="list",
            needs_value=True,
            definition={"name": "tags", "kind": "list", "item": {"type": "str"}},
        ),
    )
    result = apply_migrations(VERSION_ONE, state, [added])
    assert result.data["nickname"] is None and result.data["tags"] == []
    assert "height" not in result.data
    (problem,) = result.problems
    assert (problem.kind, problem.path) == ("missing-required", "height")


def test_a_deleted_model_and_a_change_that_cannot_be_applied_are_problems():
    state = module.migrations_after(GRAPH, {"letters": "0001_initial"})[1]
    result = apply_migrations(
        VERSION_ONE,
        state,
        [
            migration(
                "0004",
                c.WrapRelation(
                    model="Person",
                    name="name",
                    wrapper="W",
                    wrapper_kind="ReifiedRelation",
                ),
                c.DeleteModel(model="Person", model_kind="Entity"),
            )
        ],
    )
    assert [p.kind for p in result.problems] == ["unsupported-change", "model-removed"]


def test_nested_nodes_and_models_that_inherit_the_field_are_upgraded_too():
    parent = person(literal("name"))
    child = {
        "name": "Author",
        "kind": "Entity",
        "labels": ["Author", "Person", "Entity"],
        "fields": [literal("name")],
    }
    state = {"version": 1, "models": {"Person": parent, "Author": child}, "enums": {}}
    data = {
        "type": "Author",
        "id": "1",
        "name": "A",
        "friend": {"type": "Person", "id": "2", "label": "reference"},
    }
    result = apply_migrations(
        data,
        state,
        [migration("0002", c.RenameField(model="Person", old="name", new="full_name"))],
    )
    # (the author has the field of its parent; a reference to an entity is not part of the document)
    assert result.data["full_name"] == "A" and "name" not in result.data
    assert result.data["friend"] == {"type": "Person", "id": "2", "label": "reference"}


def test_the_draft_says_what_is_wrong_with_the_content(monkeypatch):
    class Model:
        __name__ = "Person"

        class Update:
            @staticmethod
            def model_validate(data):
                from pydantic import BaseModel

                class Strict(BaseModel):
                    born: int

                return Strict.model_validate(data)

    record = HistoryRecord(
        head_id=__import__("uuid").uuid7(),
        version=1,
        op="create",
        model="Person",
        at=__import__("datetime").datetime.now(),
        who="j",
        schema_position={"letters": "0001_initial"},
        content='{"type": "Person", "id": "1", "name": "Ann"}',
    )
    monkeypatch.setattr(draft_module, "installed_apps", lambda: ["letters"])
    monkeypatch.setattr(
        draft_module, "schema_position", lambda apps: {"letters": "0003_by_hand"}
    )

    draft = draft_module.make_draft(record, Model)
    assert draft.upgraded and draft.data["born"] == 1900
    assert [p.kind for p in draft.problems] == ["hand-written-migration"]
    assert len(draft.blocking) == 1

    # a missing value is a validation problem
    monkeypatch.setattr(module, "graph_of", lambda apps: MigrationGraph.of([FIRST]))
    monkeypatch.setattr(
        draft_module, "schema_position", lambda apps: {"letters": "0001_initial"}
    )
    plain = draft_module.make_draft(record, Model)
    assert not plain.upgraded
    assert [(p.kind, p.path) for p in plain.problems] == [("validation", "born")]
