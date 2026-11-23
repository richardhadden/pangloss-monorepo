"""The tree functions of `pangloss_models.rewriting`: nodes of what an `Update` takes replaced, by id or by a test,
in a copy"""

from pangloss_models.rewriting import replaced, replaced_where

DATA = {
    "id": "h",
    "statements": [
        {"id": "a", "by": [{"id": "x", "label": "J", "kind": "m"}, {"id": "y"}]},
        {"id": "b", "by": [{"id": "z", "kind": "m"}]},
    ],
}


def test_a_node_is_replaced_by_its_id_in_a_copy():
    changed, found = replaced(DATA, "x", lambda part: {"was": part["label"]})
    assert found
    assert changed["statements"][0]["by"] == [{"was": "J"}, {"id": "y"}]
    assert DATA["statements"][0]["by"][0] == {"id": "x", "label": "J", "kind": "m"}


def test_nothing_found_is_said_and_nothing_changed():
    assert replaced(DATA, "nowhere", lambda part: part) == (DATA, False)


def test_every_node_chosen_is_replaced():
    changed, found = replaced_where(
        DATA, lambda node: node.get("kind") == "m", lambda node: {"id": node["id"]}
    )
    assert found
    assert changed["statements"][0]["by"] == [{"id": "x"}, {"id": "y"}]
    assert changed["statements"][1]["by"] == [{"id": "z"}]


def test_a_node_replaced_is_not_looked_into():
    seen = []

    def replace(node):
        seen.append(node["id"])
        return node

    replaced_where(DATA, lambda node: node.get("id") in ("a", "x"), replace)
    assert seen == ["a"]
