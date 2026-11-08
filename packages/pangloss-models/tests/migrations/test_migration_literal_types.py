"""What a change of a literal type means to the data: a change between two types stored the same (`UUID` and
`str`, a `Literal` of strings and `str`, a list and a set) is a change to the models only; a new field with a
default the class declares needs no answer for the nodes that exist."""

import uuid
from typing import Literal, no_type_check

from migration_support import changes
from pangloss_models import Document
from pangloss_models.migrations import (
    AddField,
    AlterLiteralType,
    StateOnly,
)
from pangloss_models.migrations.questions import answers_needed


def one(result, cls):
    found = [c for c in result.changes if isinstance(c, cls)]
    assert len(found) == 1, (cls.__name__, result.changes)
    return found[0]


@no_type_check
def test_a_change_between_types_stored_the_same_touches_the_models_only():
    def before():
        class Record(Document):
            code: str
            kind: Literal["a", "b"]
            tags: list[str]

    def after():
        class Record(Document):
            code: uuid.UUID
            kind: str
            tags: set[str]

    result = changes(before, after)
    assert all(isinstance(c, StateOnly) for c in result.changes), result.changes
    inner = [c.changes[0] for c in result.changes]
    # (a list that is now a set is the same list stored: not even a change to the models' snapshot)
    assert {(type(c), c.name) for c in inner} == {
        (AlterLiteralType, "code"),
        (AlterLiteralType, "kind"),
    }
    code = next(c for c in inner if c.name == "code")
    assert code.old == {"type": "str"} and code.new == {"type": "str", "format": "uuid"}


@no_type_check
def test_a_change_of_storage_is_a_conversion_of_the_data():
    def before():
        class Record(Document):
            code: uuid.UUID
            kind: Literal["a", "b"]

    def after():
        class Record(Document):
            code: int
            kind: Literal[1, 2]

    result = changes(before, after)
    assert [type(c) for c in result.changes] == [AlterLiteralType, AlterLiteralType]
    assert {c.name for c in result.changes} == {"code", "kind"}


@no_type_check
def test_a_new_field_with_a_default_needs_no_value_for_the_nodes_that_exist():
    def before():
        class Record(Document):
            text: str

    def after():
        class Record(Document):
            text: str
            count: int = 7
            tags: list[str] = ["a"]
            needed: int

    result = changes(before, after)
    added = {c.name: c for c in result.changes if isinstance(c, AddField)}
    assert added["count"].needs_value and added["count"].default == 7
    assert added["tags"].default == ["a"]
    assert added["needed"].default is None
    state = {"models": {}, "enums": {}}
    assert answers_needed(added["count"], state) == []
    assert answers_needed(added["tags"], state) == []
    assert [q.field for q in answers_needed(added["needed"], state)] == ["default"]


@no_type_check
def test_the_default_is_not_part_of_what_is_stored():
    from pangloss_models.migrations import snapshot_hash

    from migration_support import snapshot_of

    def before():
        class Record(Document):
            count: int

    def after():
        class Record(Document):
            count: int = 3

    assert snapshot_hash(snapshot_of(before)) == snapshot_hash(snapshot_of(after))
    assert changes(before, after).changes == []
