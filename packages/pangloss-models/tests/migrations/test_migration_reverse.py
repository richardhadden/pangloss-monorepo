"""Going backwards: the changes that undo a migration"""

from typing import no_type_check

import pytest
from migration_support import snapshot_of
from pangloss_models.exceptions import PanglossMigrationIrreversible
from pangloss_models.meta_kit.migrations import changes as c
from pangloss_models.meta_kit.migrations import data_view, diff, replay
from pangloss_models.meta_kit.migrations.questions import collect_questions
from pangloss_models.meta_kit.migrations.reverse import reverse_changes
from pangloss_models.model_bases.entity import Entity


def undo(before, after, **answers):
    old, new = snapshot_of(before), snapshot_of(after)
    found = diff(old, new, **answers).changes
    reversal = reverse_changes(found, data_view(old))
    # (what undoes it brings back the models)
    assert replay(new, reversal.changes) == data_view(old)
    return found, reversal


@no_type_check
def test_a_rename_is_undone_by_the_rename_back():
    def v1():
        class Person(Entity):
            name: str

    def v2():
        class Person(Entity):
            full_name: str

    old, new = snapshot_of(v1), snapshot_of(v2)
    from pangloss_models.meta_kit.migrations import PossibleRename

    rename = PossibleRename(what="field", scope="Person", old="name", new="full_name")
    found = diff(old, new, confirmed=[rename]).changes
    reversal = reverse_changes(found, data_view(old))
    assert reversal.changes == [
        c.RenameField(model="Person", old="full_name", new="name")
    ]
    assert not reversal.lossy


@no_type_check
def test_adding_an_optional_field_is_undone_by_removing_it_and_loses_its_values():
    def v1():
        class Person(Entity):
            name: str

    def v2():
        class Person(Entity):
            name: str
            nickname: str | None

    _, reversal = undo(v1, v2)
    assert [type(ch) for ch in reversal.changes] == [c.RemoveField]
    assert reversal.lossy  # (the values that were written are gone)


@no_type_check
def test_a_field_removed_comes_back_when_it_needs_no_value():
    def v1():
        class Person(Entity):
            name: str
            nickname: str | None

    def v2():
        class Person(Entity):
            name: str

    _, reversal = undo(v1, v2)
    assert [type(ch) for ch in reversal.changes] == [c.AddField]
    assert reversal.lossy  # (the values it had are not brought back)
    assert collect_questions(reversal.changes, data_view(snapshot_of(v2))) == []


@no_type_check
def test_a_required_field_that_comes_back_asks_for_a_value():
    def v1():
        class Person(Entity):
            name: str
            born: int

    def v2():
        class Person(Entity):
            name: str

    old = snapshot_of(v1)
    found = diff(old, snapshot_of(v2)).changes
    reversal = reverse_changes(found, data_view(old))
    questions = collect_questions(reversal.changes, replay(old, found))
    assert [q.field for _, q in questions] == ["default"]


@no_type_check
def test_models_are_undone_and_a_new_one_deleted():
    def v1():
        class Person(Entity):
            name: str

    def v2():
        class Person(Entity):
            name: str

        class Place(Entity):
            name: str

    _, reversal = undo(v1, v2)
    assert reversal.changes == [c.DeleteModel(model="Place", model_kind="Entity")]
    assert reversal.lossy


@no_type_check
def test_changes_are_undone_in_the_opposite_order():
    def v1():
        class Person(Entity):
            name: str

    def v2():
        class Person(Entity):
            name: str
            nickname: str | None

        class Place(Entity):
            name: str

    found, reversal = undo(v1, v2)
    assert len(found) == len(reversal.changes) == 2
    assert [type(ch) for ch in reversal.changes] == [
        {c.CreateModel: c.DeleteModel, c.AddField: c.RemoveField}[type(ch)]
        for ch in reversed(found)
    ]


def test_a_change_made_by_hand_is_undone_only_if_it_says_how():
    state = data_view(snapshot_of(lambda: None))
    with pytest.raises(PanglossMigrationIrreversible, match="reverse_query"):
        reverse_changes([c.RunCypher(query="RETURN 1")], state)
    with pytest.raises(PanglossMigrationIrreversible, match="reverse_function"):
        reverse_changes([c.RunPython(function="a:b")], state)

    reversal = reverse_changes(
        [
            c.RunCypher(
                query="SET 1", reverse_query="SET 2", reverse_parameters={"x": 1}
            ),
            c.RunPython(function="a:b", reverse_function="a:c"),
        ],
        state,
    )
    # (last first, and each undoes the other)
    assert reversal.changes[0] == c.RunPython(function="a:c", reverse_function="a:b")
    assert (
        reversal.changes[1].query == "SET 2"
        and reversal.changes[1].reverse_query == "SET 1"
    )
    assert reversal.changes[1].parameters == {"x": 1}


@no_type_check
def test_a_change_that_was_done_by_hand_cannot_be_undone_by_machine():
    def v1():
        class Thing(Entity):
            pass

    old = data_view(snapshot_of(v1))
    with pytest.raises(PanglossMigrationIrreversible, match="cannot be undone"):
        reverse_changes(
            [c.AlterModelKind(model="Thing", old="entity", new="document")], old
        )


@no_type_check
def test_state_only_changes_are_undone_as_state_only():
    def v1():
        class Thing(Entity):
            pass

    old = data_view(snapshot_of(v1))
    forward = c.StateOnly(changes=(c.RenameModel(old="Thing", new="Item"),))
    reversal = reverse_changes([forward], old)
    assert reversal.changes == [
        c.StateOnly(changes=(c.RenameModel(old="Item", new="Thing"),))
    ]


@no_type_check
def test_what_does_not_come_back_exactly_is_not_hidden():
    def v1():
        class Person(Entity):
            name: str
            age: int

    def v2():
        class Person(Entity):
            name: str
            age: float

    _, reversal = undo(v1, v2)
    assert reversal.lossy  # (a conversion back may not be the same)
