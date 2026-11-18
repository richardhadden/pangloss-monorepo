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


def test_a_property_name_is_backticked_and_what_cannot_be_one_is_refused():
    assert fragments.property_name("born_in") == "`born_in`"
    with pytest.raises(ValueError, match=r"^'a\.b' is not the name of a property$"):
        fragments.property_name("a.b")


def test_what_is_listed_is_what_is_seen_and_not_merged_into_another():
    head = fragments.head_of("n", "n_head")
    assert (
        fragments.listed("n") == fragments.visible("n") + "\nAND n.merged_into IS NULL"
    )
    assert (
        fragments.listed("n", head)
        == fragments.visible("n", head) + "\nAND n.merged_into IS NULL"
    )
    assert fragments.listed("n", head, filters=True) == (
        fragments.visible("n", head, filters=True) + "\nAND n.merged_into IS NULL"
    )


def test_a_forward_edge_is_neither_a_reverse_edge_nor_a_shortcut():
    assert fragments.forward("e") == (
        "NOT coalesce(e.reverse, false) AND NOT coalesce(e.derived, false)"
    )


def test_counted_edges_are_tested_only_when_an_app_says_some_are_of_no_field(
    monkeypatch,
):
    from pangloss_models import hooks

    monkeypatch.setattr(hooks, "edges_of_no_field", [lambda: False])
    assert fragments.counted_edge("e") == ""
    monkeypatch.setattr(hooks, "edges_of_no_field", [lambda: False, lambda: True])
    assert fragments.counted_edge("e") == "WHERE NOT coalesce(e.derived, false)"


def test_what_refers_to_something_counts_unless_an_app_says_its_class_does_not(
    monkeypatch,
):
    from pangloss_models import hooks

    monkeypatch.setattr(hooks, "references_not_counted", [])
    assert fragments.counted("h") == ""
    assert "holder <> n\n" in fragments.uses_of("n")

    monkeypatch.setattr(
        hooks,
        "references_not_counted",
        [lambda: ["Derived", "Alpha"], lambda: ["Alpha"]],
    )
    assert fragments.counted("h") == " AND NOT (h:`Alpha` OR h:`Derived`)"
    assert (
        "holder <> n AND NOT (holder:`Alpha` OR holder:`Derived`)\n"
        in fragments.uses_of("n")
    )


def test_what_something_refers_to_is_counted_once_by_what_the_reader_lists(monkeypatch):
    from pangloss_models import hooks

    monkeypatch.setattr(hooks, "references_not_counted", [])
    query = fragments.uses_of("n")
    assert "CALL (n) {" in query
    assert (
        "MATCH (n)-[used_edge]->(used_by)\n      WHERE coalesce(used_edge.reverse, false)"
        in query
    )
    assert fragments.head_of("used_by", "used_head").match in query
    assert f"WHERE {fragments.listed('holder')} AND holder <> n" in query
    assert "RETURN count(DISTINCT used_by) AS uses" in query

    kept = fragments.only_used("n", "a", "b")
    assert kept.startswith(query)
    assert kept.endswith("WITH n, a, b, uses\n    WHERE uses > 0\n    WITH n, a, b\n")
    assert fragments.only_used("n").endswith(
        "WITH n, uses\n    WHERE uses > 0\n    WITH n\n"
    )
