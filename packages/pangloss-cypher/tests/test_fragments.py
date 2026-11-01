"""The pieces of Cypher for model data (`pangloss_cypher.fragments`), and that the rule of what a reader sees is written
only there"""

import re
from pathlib import Path

import pytest
from pangloss_cypher import fragments

PACKAGES = Path(__file__).parents[2]


def test_a_head_node_is_seen_if_not_deleted_and_published_or_unpublished_may_be_seen():
    assert fragments.visible("n") == (
        "NOT coalesce(n.deleted, false) AND ($see_unpublished OR coalesce(n.published, true))"
    )


def test_any_node_is_seen_by_its_head_node_and_an_entity_by_whether_it_is_deleted():
    head = fragments.head_of("n", "n_head")
    assert head.match == "OPTIONAL MATCH (n_head:HeadNode {id: n.head_node_id})"
    assert str(head) == "coalesce(n_head, n)"
    assert fragments.visible("n", head).split("\n") == [
        "NOT coalesce(CASE WHEN n:Entity THEN n.deleted ELSE coalesce(n_head, n).deleted END, false)",
        "AND (n:Entity OR $see_unpublished OR coalesce(coalesce(n_head, n).published, true))",
    ]


def test_a_list_may_ask_for_what_is_published_or_in_a_state_of_review():
    lines = fragments.visible("n", "h", filters=True).split("\n")
    assert lines[2:] == [
        "AND ($published IS NULL OR coalesce(h.published, true) = $published)",
        "AND ($review_status IS NULL OR h.review_status = $review_status)",
    ]


def test_hidden_is_the_negation_of_visible():
    assert fragments.hidden("h") == (
        "h.deleted OR NOT ($see_unpublished OR coalesce(h.published, true))"
    )


@pytest.mark.parametrize("name", ["Event", "_x", "when2"])
def test_names_are_backticked(name):
    assert fragments.label(name) == f"`{name}`"
    assert fragments.field_edge(name) == f"`{name}`"


@pytest.mark.parametrize("name", ["", "Ev`ent", "a b", "x)-[:y]->(z", "2nd"])
def test_what_cannot_be_a_name_is_refused(name):
    with pytest.raises(ValueError, match="is not the name of a class"):
        fragments.label(name)
    with pytest.raises(ValueError, match="is not the name of a field"):
        fragments.field_edge(name)


def test_the_rule_of_what_is_deleted_is_written_only_in_fragments():
    """(Every query that reads model data gets the rule from `fragments`: the kit's, the backends', and the add-ons',
    through `pangloss_core.backend`)"""
    copies = [
        f"{path.relative_to(PACKAGES)}:{number}"
        for path in PACKAGES.glob("*/src/**/*.py")
        if path.name != "fragments.py"
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if re.search(r"coalesce\(.*deleted", line)
    ]
    assert not copies, f"copies of the rule of what is deleted: {copies}"
