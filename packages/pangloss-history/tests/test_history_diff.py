from pangloss_history.diff import Change, diff
from pangloss_history.gaps import find_gaps
from history_support import record


def test_values_that_are_added_removed_and_changed():
    assert diff({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 5, "d": 4}) == [
        Change("b", "changed", old=2, new=5),
        Change("c", "removed", old=3),
        Change("d", "added", new=4),
    ]


def test_nothing_changed():
    assert diff({"a": [1, {"b": 2}]}, {"a": [1, {"b": 2}]}) == []


def test_nested_objects_with_ids_are_compared_by_id_not_place():
    old = {"parts": [{"id": "1", "text": "a"}, {"id": "2", "text": "b"}]}
    new = {"parts": [{"id": "3", "text": "c"}, {"id": "2", "text": "B"}]}
    assert diff(old, new) == [
        Change("parts[1]", "removed", old={"id": "1", "text": "a"}),
        Change("parts[2].text", "changed", old="b", new="B"),
        Change("parts[3]", "added", new={"id": "3", "text": "c"}),
    ]


def test_lists_without_ids_are_compared_by_place():
    assert diff({"x": [1, 2, 3]}, {"x": [1, 9]}) == [
        Change("x[1]", "changed", old=2, new=9),
        Change("x[2]", "removed", old=3),
    ]


def test_a_value_that_changes_type():
    assert diff({"a": 1}, {"a": {"b": 1}}) == [Change("a", "changed", old=1, new={"b": 1})]


def test_gaps_are_the_versions_that_have_no_record_of_content():
    records = [record(version=1), record(version=2, op="update"), record(version=2, op="delete"),
               record(version=5, op="update")]
    assert find_gaps(records, 5) == [3, 4]
    assert find_gaps(records, 2) == []
    assert find_gaps([record(version=2, op="delete")], 2) == [1, 2]
