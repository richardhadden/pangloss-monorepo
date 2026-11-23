"""What a candidate is named with leaves out what is below a guess no person has confirmed (`reasons.unconfirmed`,
step 10.5c), with no database: with no class of `hooks.unconfirmed` the query is the one it was; with some, both
edges are tested, each class by its label, from a node below a head only. (That it is right on both backends is the
live test, `live/test_reconcile_unconfirmed_live.py`)"""

import pytest
from pangloss_cypher import fragments
from pangloss_reconcile import reasons


class Walking:
    """A dialect that says only how it walks up through wrappers"""

    def through_wrappers(self, name: str, *, backwards: bool = False) -> str:
        assert backwards
        return f"<-[{name} through wrappers]-"


@pytest.fixture
def walking(monkeypatch):
    import pangloss_cypher.transactions

    monkeypatch.setattr(pangloss_cypher.transactions, "dialect", lambda: Walking())


def test_with_no_class_unconfirmed_the_query_is_what_it_was():
    assert reasons.unconfirmed("n1", []) == ""
    query = reasons._query(fragments, [])
    assert query == reasons._query(fragments)
    assert "EXISTS" not in query and "_held" not in query


def test_with_classes_unconfirmed_both_edges_are_tested_by_their_labels_from_a_node_below_a_head(
    walking,
):
    found = reasons.unconfirmed("n1", ["Guess", "Hunch"])
    assert found == (
        " AND (n1.head_node_id IS NULL OR NOT EXISTS { MATCH (n1)<-[n1_up through wrappers]-(n1_held) "
        "WHERE any(label IN labels(n1_held) WHERE label IN ['Guess', 'Hunch']) })"
    )
    query = reasons._query(fragments, ["Guess"])
    assert query.count("NOT EXISTS") == 2
    assert "MATCH (n1)<-[n1_up" in query and "MATCH (n2)<-[n2_up" in query


def test_a_name_that_cannot_be_a_class_is_refused(walking):
    with pytest.raises(ValueError, match="is not the name of a class"):
        reasons.unconfirmed("n1", ["Guess') OR true //"])
