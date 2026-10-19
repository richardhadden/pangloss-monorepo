"""The functions that turn what the database returns into the input of a view"""

from enum import Enum

import pytest
from pangloss_memgraph.databases.memgraph.build_tree import build_tree
from pangloss_memgraph.databases.memgraph.read_enums import convert_enums
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossRuntimeError
from pangloss_models.model_bases.document import Document

from .helpers import mg_enum

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


class ReadColour(Enum):
    RED = "red"
    BLUE = "blue"


async def test_convert_enums():
    class Statement(Document):
        colour: ReadColour

    initialise()

    converted = convert_enums(
        {
            "a": mg_enum("ReadColour::RED"),
            "list": [mg_enum("ReadColour::BLUE"), 1, "x"],
            "nested": {"deeper": [{"c": mg_enum("ReadColour::RED")}]},
            "plain": {"__type": "something_else", "__value": "x"},
            "number": 3,
        }
    )

    assert converted["a"] is ReadColour.RED
    assert converted["list"] == [ReadColour.BLUE, 1, "x"]
    assert converted["nested"]["deeper"][0]["c"] is ReadColour.RED
    assert converted["plain"] == {"__type": "something_else", "__value": "x"}
    assert converted["number"] == 3


async def test_convert_enums_leaves_data_with_no_enums_alone():
    data = {"a": [1, {"b": "c"}], "d": None}
    assert convert_enums(data) == data


async def test_convert_enums_of_an_unknown_enum_raises():
    class Statement(Document):
        text: str

    initialise()

    with pytest.raises(PanglossRuntimeError, match="NoSuchEnum::X"):
        convert_enums(mg_enum("NoSuchEnum::X"))
