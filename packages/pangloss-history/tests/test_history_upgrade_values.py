"""A stored version whose literal values name parts of the models (a search pattern, of a type whose codec says how a
change alters it: `LiteralCodec.migrate`) is upgraded with them (no database). History knows nothing of the type:
the snapshot names its format, and the codec of that format does the work"""

import json

import pytest
from pangloss_history.upgrade import apply_migrations
from pangloss_models import LiteralCodec, ValueNotMigrated, literals
from pangloss_models.migrations import Migration
from pangloss_models.migrations import changes as c
from pangloss_models.migrations import patterns

FORMAT = "test-stored-search"


class StoredSearch(str):
    """(a type of the test's own, stored as text)"""


def migrate(value, change, before):
    """As a package's codec does it: the pattern brought through the change, in the form it was given"""
    result = patterns.upgrade(json.loads(value), change, before)
    made = json.dumps(result.pattern) if result.changed else value
    if result.broken is not None:
        raise ValueNotMigrated(
            result.broken.reason, made, result.broken.path, "pattern"
        )
    return made


@pytest.fixture(autouse=True)
def codec():
    made = LiteralCodec(
        (StoredSearch,), "str", FORMAT, search_kind=None, migrate=migrate
    )
    literals.register_codec(made)
    yield made
    literals._registered.remove(made)


def state() -> dict:
    return {
        "version": 1,
        "models": {
            "Note": {
                "name": "Note",
                "kind": "Document",
                "labels": ["Note", "Document"],
                "fields": [
                    {
                        "name": "query",
                        "kind": "literal",
                        "type": {"type": "str", "format": FORMAT},
                        "nullable": True,
                    },
                    {
                        "name": "queries",
                        "kind": "list",
                        "item": {"type": "str", "format": FORMAT},
                        "nullable": False,
                    },
                ],
            },
            "Person": {
                "name": "Person",
                "kind": "Entity",
                "labels": ["Person", "Entity"],
                "fields": [
                    {
                        "name": "age",
                        "kind": "literal",
                        "type": {"type": "int"},
                        "nullable": True,
                    }
                ],
            },
        },
        "enums": {},
    }


OLDER = json.dumps({"type": "Person", "where": {"age": {"gt": 30}}})


def upgrade(*changes):
    note = {
        "type": "Note",
        "id": "1",
        "label": "n",
        "query": OLDER,
        "queries": [OLDER, json.dumps({"type": "Person", "where": {}})],
    }
    migration = Migration(app="letters", name="0002", changes=tuple(changes))
    return apply_migrations(note, state(), [migration])


def test_a_field_renamed_is_renamed_in_a_pattern_of_an_old_version():
    result = upgrade(c.RenameField(model="Person", old="age", new="years"))
    assert result.problems == []
    assert json.loads(result.data["query"]) == {
        "type": "Person",
        "where": {"years": {"gt": 30}},
    }
    assert json.loads(result.data["queries"][0]) == json.loads(result.data["query"])
    # (one the change does not alter is as it was)
    assert result.data["queries"][1] == json.dumps({"type": "Person", "where": {}})


def test_a_field_removed_that_a_pattern_names_is_a_problem_that_blocks():
    result = upgrade(c.RemoveField(model="Person", name="age", field_kind="literal"))
    problems = [(p.kind, p.path, p.blocking) for p in result.problems]
    assert problems == [
        ("pattern", "query", True),
        ("pattern", "queries[0]", True),
    ]
    assert "age: the field 'age' of Person was removed" in result.problems[0].message
    assert result.problems[0].migration == "letters.0002"
    # (the condition is kept, not dropped)
    assert result.data["query"] == OLDER


def test_a_value_of_a_type_with_no_such_codec_is_left_alone(codec):
    literals._registered.remove(codec)
    try:
        result = upgrade(
            c.RemoveField(model="Person", name="age", field_kind="literal")
        )
    finally:
        literals._registered.insert(0, codec)
    assert result.problems == [] and result.data["query"] == OLDER
