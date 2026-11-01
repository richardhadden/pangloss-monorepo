"""Changes written by hand: `RunCypher`, `RunPython` and `StateOnly`"""

from typing import no_type_check

import pytest
from migration_support import snapshot_of
from pangloss_models.exceptions import PanglossMigrationError
from pangloss_models.migrations import changes as c
from pangloss_models.migrations import data_view, replay
from pangloss_models.migrations.affected import affected_models
from pangloss_models.migrations.files import (
    EMPTY_SNAPSHOT,
    changes_from_data,
    checksum_of,
    empty_hint,
)
from pangloss_models.migrations.reverse import reverse_changes
from pangloss_models.model_bases.entity import Entity


def a_function(tx, state):
    pass


@no_type_check
def snapshot():
    def declare():
        class Person(Entity):
            name: str

        class Place(Entity):
            name: str

    return snapshot_of(declare)


def test_changes_by_hand_are_data_that_can_be_written_and_read():
    changes = [
        c.RunCypher(
            query="MATCH (n:Person) SET n.x = $x", parameters={"x": 1}, note="set x"
        ),
        c.RunPython(function=a_function, lossy=True, affects=["Person"]),
        c.StateOnly(
            changes=(c.AlterModelKind(model="Person", old="entity", new="document"),)
        ),
    ]
    again = [c.change_from_dict(change.to_dict()) for change in changes]
    assert again == changes
    assert checksum_of(again) == checksum_of(changes)
    # (a migration file may give the changes as data, or as the changes)
    assert changes_from_data([changes[0], changes[1].to_dict()]) == changes[:2]


def test_a_function_is_kept_as_its_name_and_found_again():
    change = c.RunPython(function=a_function)
    assert change.function == f"{__name__}:a_function"
    assert change.resolve() is a_function


def test_a_change_by_hand_loses_data_when_it_says_so():
    assert c.RunCypher(query="RETURN 1").safety == "transforming"
    assert c.RunCypher(query="RETURN 1", lossy=True).safety == "lossy"
    assert c.RunCypher(query="RETURN 1", lossy=True).to_dict()["safety"] == "lossy"
    assert c.RunPython(function="a:b", lossy=True).safety == "lossy"


def test_only_state_only_changes_the_models():
    old = data_view(snapshot())
    assert (
        replay(old, [c.RunCypher(query="RETURN 1"), c.RunPython(function="a:b")]) == old
    )

    rename = c.RenameModel(old="Place", new="Location")
    after = replay(old, [c.StateOnly(changes=(rename,))])
    assert "Location" in after["models"] and "Place" not in after["models"]
    assert after == replay(old, [rename])


def test_what_is_read_afterwards_is_what_the_change_says():
    models = snapshot()
    assert affected_models([c.RunCypher(query="RETURN 1")], models) == {
        "Person",
        "Place",
    }
    assert affected_models(
        [c.RunCypher(query="RETURN 1", affects=["Place"])], models
    ) == {"Place"}
    assert affected_models([c.RunPython(function="a:b", affects=[])], models) == set()
    # (a StateOnly is what the changes in it are)
    renamed = c.StateOnly(
        changes=(c.AlterModelLabels(model="Person", added=["Extra"]),)
    )
    assert affected_models([renamed], models) == {"Person"}
    assert (
        affected_models([c.StateOnly(changes=(c.CreateEnum(enum="E"),))], models)
        == set()
    )


def test_a_migration_that_is_only_by_hand_is_fine_for_the_graph():
    from pangloss_models.migrations.files import Migration, MigrationGraph

    first = Migration(app="x", name="0001_initial", changes=())
    second = Migration(
        app="x", name="0002_by_hand", changes=(c.RunCypher(query="RETURN 1"),)
    )
    graph = MigrationGraph.of([first, second])
    assert graph.state() == data_view(EMPTY_SNAPSHOT)


# --- a query is written for one backend -----------------------------------------------------------


def test_a_query_without_a_backend_has_the_checksum_it_had():
    """(a file written before `dialect` was there is not taken for one that was changed)"""
    change = c.RunCypher(query="RETURN 1")
    assert "dialect" not in change.to_dict()
    assert c.change_from_dict(change.to_dict()) == change
    named = c.RunCypher(query="RETURN 1", dialect="neo4j")
    assert c.change_from_dict(named.to_dict()) == named
    assert checksum_of([named]) != checksum_of([change])


def test_a_query_for_another_backend_is_refused_without_one_for_this_next_to_it():
    memgraph = c.RunCypher(query="RETURN 1", dialect="memgraph")
    neo4j = c.RunCypher(query="RETURN 2", dialect="neo4j")
    unnamed = c.RunCypher(query="RETURN 3")
    other = c.RunPython(function="a:b")

    assert c.check_dialects([memgraph, neo4j], "neo4j") == []
    assert c.check_dialects([neo4j, memgraph, other, unnamed], "memgraph") == [unnamed]
    with pytest.raises(PanglossMigrationError) as refused:
        c.check_dialects([memgraph], "neo4j")
    assert str(refused.value) == (
        "Run a query (Memgraph): RETURN 1: this migration was written for Memgraph; give a Neo4j version with "
        '`RunCypher(..., dialect="neo4j")` next to it'
    )
    # (versions that are not next to each other are not versions of one query)
    with pytest.raises(PanglossMigrationError):
        c.check_dialects([memgraph, other, neo4j], "neo4j")


def test_a_backend_that_does_not_run_cypher_refuses_every_query():
    with pytest.raises(PanglossMigrationError, match="write it as a `RunPython`"):
        c.check_dialects([c.RunCypher(query="RETURN 1")], None)
    assert c.check_dialects([c.RunPython(function="a:b")], None) == []


def test_undoing_a_query_is_for_the_same_backend():
    change = c.RunCypher(query="SET a", reverse_query="SET b", dialect="neo4j")
    (undo,) = reverse_changes([change], data_view(EMPTY_SNAPSHOT)).changes
    assert (undo.query, undo.dialect) == ("SET b", "neo4j")


def test_the_hint_of_an_empty_migration_names_the_backend():
    assert any("dialect='neo4j'" in line for line in empty_hint("neo4j"))
    assert not any(
        "dialect=" in line for line in empty_hint(None) if "RunCypher(" in line
    )
