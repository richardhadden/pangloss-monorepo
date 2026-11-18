"""The functions that turn what the database returns into the input of a view (`build_tree`)"""

import pytest
from pangloss_cypher.build_tree import GraphFragment, build_tree

pytestmark = pytest.mark.asyncio(loop_scope="session")


def edge(source, type, target, labels=("Document",), **properties):
    return {
        "source": source,
        "type": type,
        "properties": properties,
        "target": target,
        "target_labels": list(labels),
    }


async def test_build_tree():
    root = {"id": "root", "label": "Root"}
    tree = build_tree(
        root,
        ["Document"],
        [
            edge("root", "child", {"id": "a", "label": "A"}),
            edge("root", "child", {"id": "b", "label": "B"}),
            edge("a", "grandchild", {"id": "c", "label": "C"}),
            edge("root", "single", {"id": "d", "label": "D"}),
        ],
    )

    assert tree["label"] == "Root"
    assert [c["id"] for c in tree["child"]] == ["a", "b"]
    assert tree["child"][0]["grandchild"] == [{"id": "c", "label": "C"}]
    assert tree["single"] == [{"id": "d", "label": "D"}]
    assert "grandchild" not in tree["child"][1]


async def test_build_tree_does_not_change_its_input():
    root = {"id": "root"}
    build_tree(root, ["Document"], [edge("root", "child", {"id": "a"})])
    assert root == {"id": "root"}


async def test_build_tree_with_nothing_below_the_root():
    assert build_tree({"id": "root", "label": "R"}, ["Document"], []) == {
        "id": "root",
        "label": "R",
    }


async def test_build_tree_does_not_expand_entities():
    tree = build_tree(
        {"id": "root"},
        ["Document"],
        [
            edge("root", "who", {"id": "p", "label": "P"}, labels=("Person", "Entity")),
            # (an entity's own relations are not part of the document)
            edge("p", "lives_in", {"id": "x"}, labels=("Place", "Entity")),
        ],
    )
    assert tree["who"] == [{"id": "p", "label": "P"}]


async def test_build_tree_expands_the_root_even_if_it_is_an_entity():
    tree = build_tree(
        {"id": "p", "label": "P"},
        ["Person", "Entity"],
        [edge("p", "lives_in", {"id": "x"}, labels=("Place", "Entity"))],
    )
    assert tree["lives_in"] == [{"id": "x"}]


async def test_build_tree_edge_properties():
    tree = build_tree(
        {"id": "root"},
        ["Document"],
        [
            edge("root", "with", {"id": "a"}, number=1, note="n"),
            edge("root", "without", {"id": "b"}),
            edge("root", "reverse_only", {"id": "c"}, reverse=True),
        ],
    )
    assert tree["with"][0]["edge_properties"] == {"number": 1, "note": "n"}
    assert "edge_properties" not in tree["without"][0]
    assert "edge_properties" not in tree["reverse_only"][0]


async def test_build_tree_puts_each_list_in_the_order_it_was_written():
    tree = build_tree(
        {"id": "root"},
        ["Document"],
        [
            # (written before there were places: after those that have one, by id)
            edge("root", "child", {"id": "c"}),
            edge("root", "child", {"id": "b"}),
            edge("root", "child", {"id": "a"}, pg_position=2),
            edge("root", "child", {"id": "m"}, pg_position=1),
            edge("root", "child", {"id": "z"}, pg_position=0),
            # (a place that is not a number is taken as the first)
            edge("root", "child", {"id": "y"}, pg_position="first"),
        ],
    )
    assert [c["id"] for c in tree["child"]] == ["y", "z", "m", "a", "b", "c"]
    # (the place is not an edge property of the model)
    assert all("edge_properties" not in c for c in tree["child"])


async def test_a_fragment_is_made_of_a_row_and_its_tree_has_the_meta_and_not_when_it_was_cited():
    fragment = GraphFragment.from_record(
        {
            "root": {"id": "root", "label": "R", "pg_cited": 3},
            "root_labels": ["Document"],
            "edges": [edge("root", "child", {"id": "a"})],
            "meta": {"version": 2},
        }
    )
    assert fragment == GraphFragment(
        root={"id": "root", "label": "R", "pg_cited": 3},
        labels=["Document"],
        edges=[edge("root", "child", {"id": "a"})],
        meta={"version": 2},
    )
    assert fragment.tree() == {
        "id": "root",
        "label": "R",
        "child": [{"id": "a"}],
        "meta": {"version": 2},
    }
    # (and the fragment is as it was)
    assert fragment.root["pg_cited"] == 3
    assert GraphFragment.from_record(
        {
            "root": {"id": "p"},
            "root_labels": ["Person", "Entity"],
            "edges": [],
            "meta": {},
        }
    ).tree() == {"id": "p", "meta": {}}
