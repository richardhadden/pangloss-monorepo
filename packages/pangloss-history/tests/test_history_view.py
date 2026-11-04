"""A version in the read form (as the interface shows it), and what changed in each version (the list's summary)"""

import asyncio
from uuid import uuid7

from history_support import record
from pangloss_history.summary import field_changes, summarise
from pangloss_history.view import labels_of, to_view

ENTITIES = {"Person", "Place"}

WRITTEN = {
    "id": "s1",
    "type": "Statement",
    "label": "S",
    "context_labels": [],
    "semantic_spaces": [],
    "carried_out_by": {
        "id": "p1",
        "type": "Person",
        "label": None,
        "edge_properties": {"how_sure": 1},
    },
    "places": [{"id": "p2", "type": "Place", "label": None}],
    "parts": [
        {
            "id": "a",
            "type": "Part",
            "create_new": False,
            "page_number": 3,
            "db_labels": ["Part"],
        }
    ],
}


def test_the_read_form_has_camel_case_keys_and_no_bookkeeping():
    view = to_view(WRITTEN, {"p1": "John", "p2": None}, ENTITIES, WRITTEN)
    assert set(view) == {"id", "type", "label", "carriedOutBy", "places", "parts"}
    assert view["parts"] == [{"id": "a", "type": "Part", "pageNumber": 3}]
    assert view["carriedOutBy"] == {
        "id": "p1",
        "type": "Person",
        "label": "John",
        "edgeProperties": {"howSure": 1},
    }
    # (an entity that is not there now)
    assert view["places"] == [
        {"id": "p2", "type": "Place", "label": None, "missing": True}
    ]


def test_the_head_node_keeps_its_own_label_when_it_is_an_entity():
    person = {
        "id": "p1",
        "type": "Person",
        "label": "John then",
        "known_as": [{"id": "x", "type": "Person", "label": None}],
    }
    view = to_view(person, {"x": "Jim"}, ENTITIES, person)
    assert view["label"] == "John then" and view["knownAs"][0]["label"] == "Jim"


def test_each_entity_is_looked_up_once_for_all_versions():
    asked = []

    async def look_up(type_name, id):
        asked.append((type_name, id))
        return id.upper()

    second = {**WRITTEN, "places": [{"id": "p3", "type": "Place", "label": None}]}
    labels = asyncio.run(labels_of([WRITTEN, second, WRITTEN], look_up, ENTITIES))
    assert labels == {"p1": "P1", "p2": "P2", "p3": "P3"}
    assert sorted(asked) == [("Person", "p1"), ("Place", "p2"), ("Place", "p3")]


def test_the_changes_of_a_version_are_by_field_of_the_head_node():
    before = {
        "label": "S",
        "text": "one",
        "parts": [{"id": "a", "n": 1}],
        "places": [{"id": "p"}],
        "year": 1,
    }
    after = {
        "label": "S",
        "text": "two",
        "parts": [{"id": "a", "n": 2}, {"id": "b", "n": 1}],
        "places": [],
        "new_field": 1,
        "semantic_spaces": ["X"],
    }
    changes = {c["key"]: (c["kind"], c["count"]) for c in field_changes(before, after)}
    assert changes == {
        "text": ("changed", 1),
        "parts": ("changed", 2),  # (one changed, one added)
        "places": ("removed", 1),
        "year": ("removed", 1),
        "newField": ("added", 1),
    }


def test_a_summary_compares_each_version_with_content_to_the_one_before():
    id = uuid7()
    records = [
        record(id, 1, content={"label": "One", "text": "a"}, seq=1),
        record(id, 2, "update", content={"label": "Two", "text": "a"}, seq=2),
        record(id, 2, "delete", seq=3),
        record(id, 3, "restore", content={"label": "One", "text": "a"}, seq=4),
    ]
    by_seq = {r.seq: r for r in records}
    summary = summarise(records, lambda r: by_seq[r.seq].data())
    assert summary == {
        1: {"label": "One", "changes": []},
        2: {
            "label": "Two",
            "changes": [{"key": "label", "kind": "changed", "count": 1}],
        },
        4: {
            "label": "One",
            "changes": [{"key": "label", "kind": "changed", "count": 1}],
        },
    }
