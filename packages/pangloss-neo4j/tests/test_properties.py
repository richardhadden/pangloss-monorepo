"""Flattening the maps that Neo4j cannot store as properties, and nesting them again"""

import datetime

import pytest
from pangloss_models.exceptions import PanglossWriteError
from pangloss_neo4j.databases.neo4j import properties as p

WHEN = datetime.datetime(2026, 10, 29, 12, 0, tzinfo=datetime.UTC)


def meta(**more):
    return {
        "created_by": "ann",
        "created_when": WHEN,
        "updated_by": "bob",
        "updated_when": WHEN,
        "semantic_spaces": ["Hypothetical"],
        "context_labels": [{"type": "Hypothetical", "certainty": 2}],
        **more,
    }


def test_a_map_is_flattened_by_its_path():
    flat = p.flatten({"id": "a", "label": "x", "meta": meta()})
    assert flat["id"] == "a"
    assert flat["meta.created_by"] == "ann"
    assert flat["meta.created_when"] == WHEN
    assert flat["meta.semantic_spaces"] == ["Hypothetical"]
    assert not any(isinstance(v, dict) for v in flat.values())


def test_a_list_of_maps_is_json_and_its_types_are_kept_flat_for_queries():
    flat = p.flatten({"meta": meta()})
    assert isinstance(flat["meta.context_labels#json"], str)
    assert "meta.context_labels" not in flat
    assert flat["meta.context_label_types"] == ["Hypothetical"]


def test_nesting_again_gives_back_what_was_written():
    original = {"id": "a", "label": "x", "meta": meta()}
    assert p.unflatten(p.flatten(original)) == original


def test_what_is_kept_flat_for_queries_is_not_given_back():
    assert "meta.context_label_types" not in str(
        p.unflatten(p.flatten({"meta": meta()}))
    )


def test_an_annotated_value_is_two_properties():
    flat = p.flatten({"date": {"value": "1500", "certainty": 3}})
    assert flat == {"date.value": "1500", "date.certainty": 3}
    assert p.unflatten(flat) == {"date": {"value": "1500", "certainty": 3}}


def test_maps_are_flattened_to_any_depth():
    original = {"a": {"b": {"c": 1, "d": [1, 2]}, "e": "x"}}
    flat = p.flatten(original)
    assert flat == {"a.b.c": 1, "a.b.d": [1, 2], "a.e": "x"}
    assert p.unflatten(flat) == original


def test_none_and_empty_maps_are_no_property():
    assert p.flatten(
        {"a": None, "b": {}, "c": {"d": None}, "e": 0, "f": "", "g": []}
    ) == {
        "e": 0,
        "f": "",
        "g": [],
    }


def test_lists_of_one_type_are_stored_as_they_are():
    for value in (["a", "b"], [1, 2], [1, 2.5], [True, False], [], [WHEN]):
        assert p.flatten({"x": value}) == {"x": value}


def test_any_list_of_maps_is_stored_as_json_under_a_name_that_says_so():
    original = {
        "items": [{"a": 1, "b": [1, 2]}, {"a": 2}],
        "mixed": [1, "a"],
        "nested": [[1], [2]],
    }
    flat = p.flatten(original)
    assert set(flat) == {"items#json", "mixed#json", "nested#json"}
    assert all(isinstance(v, str) for v in flat.values())
    assert p.unflatten(flat) == original


def test_a_list_of_maps_inside_a_map_keeps_its_path():
    original = {"dims": {"all": [{"w": 1}, {"w": 2}], "one": {"w": 3}}}
    flat = p.flatten(original)
    assert set(flat) == {"dims.all#json", "dims.one.w"}
    assert p.unflatten(flat) == original


def test_a_list_that_cannot_be_written_as_json_is_refused_and_says_which():
    with pytest.raises(PanglossWriteError, match="stuff"):
        p.flatten({"stuff": [{"a": object()}]})


def test_text_that_is_json_in_another_property_is_left_as_text():
    assert p.unflatten({"note": '[{"type": "x"}]'}) == {"note": '[{"type": "x"}]'}


def test_decode_nests_maps_anywhere_in_a_result():
    row = {
        "results": [{"id": "a", "date.value": "1500", "date.certainty": 3}],
        "n": 1,
    }
    assert p.decode(row) == {
        "results": [{"id": "a", "date": {"value": "1500", "certainty": 3}}],
        "n": 1,
    }


def test_decode_reads_context_labels_that_a_query_gave_as_text():
    given = {
        "meta": {"created_by": "ann", "context_labels": '[{"type":"Hypothetical"}]'}
    }
    assert p.decode(given)["meta"]["context_labels"] == [{"type": "Hypothetical"}]
    assert p.decode({"meta": {"context_labels": None}}) == {
        "meta": {"context_labels": None}
    }


def test_the_meta_a_query_builds_names_the_flat_properties():
    text = p.meta_map("n")
    assert "created_by: n.`meta.created_by`" in text
    assert "context_labels: n.`meta.context_labels#json`" in text


def test_prop_writes_a_flat_name_for_cypher():
    assert p.prop("n", "meta.semantic_spaces") == "n.`meta.semantic_spaces`"
