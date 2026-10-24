"""The database's own structure (indexes and constraints) as changes"""

import copy
from typing import no_type_check

from migration_support import snapshot_of
from pangloss_models.migrations import changes as c
from pangloss_models.migrations import data_view, diff, replay, snapshot_hash
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, Migration, MigrationGraph
from pangloss_models.migrations.planner import plan
from pangloss_models.migrations.reverse import reverse_changes
from pangloss_models.model_bases.entity import Entity

NAME = {"kind": "label+property", "label": "Thing", "properties": ["name"]}
TEXT = {"kind": "text", "label": "Thing", "properties": ["label"], "name": "thing_text"}
UNIQUE = {"kind": "unique", "label": "Thing", "properties": ["name"]}
USERS = {
    "kind": "unique",
    "label": "PGUser",
    "properties": ["username"],
    "app": "users",
}


@no_type_check
def snapshot(indexes=(), constraints=()):
    def declare():
        class Thing(Entity):
            name: str

    snap = snapshot_of(declare)
    snap["indexes"] = copy.deepcopy(list(indexes))
    snap["constraints"] = copy.deepcopy(list(constraints))
    return snap


def test_structure_added_and_removed_is_found_and_replays():
    old = snapshot(indexes=[NAME], constraints=[UNIQUE])
    new = snapshot(indexes=[TEXT], constraints=[])
    result = diff(old, new)
    assert result.changes == [
        c.AddIndex(index=TEXT),
        c.RemoveIndex(index=NAME),
        c.RemoveConstraint(constraint=UNIQUE),
    ]
    assert replay(old, result.changes) == data_view(new)
    # (nothing is found where nothing changed, whatever order they are in)
    assert (
        diff(snapshot(indexes=[NAME, TEXT]), snapshot(indexes=[TEXT, NAME])).changes
        == []
    )


def test_which_app_makes_it_is_not_what_is_stored():
    with_app, without = (
        snapshot(constraints=[USERS]),
        snapshot(constraints=[{**USERS, "app": "other"}]),
    )
    assert data_view(with_app) == data_view(without)
    assert snapshot_hash(with_app) == snapshot_hash(without)
    assert diff(with_app, without).changes == []


def test_a_snapshot_without_structure_has_none():
    assert data_view(snapshot_of(lambda: None))["indexes"] == []
    assert data_view(EMPTY_SNAPSHOT)["constraints"] == []


def test_structure_is_undone_by_its_opposite_and_loses_nothing():
    changes = [
        c.AddIndex(index=NAME),
        c.AddConstraint(constraint=UNIQUE),
        c.RemoveIndex(index=TEXT),
    ]
    state = data_view(snapshot(indexes=[TEXT]))
    reversal = reverse_changes(changes, state)
    assert reversal.changes == [
        c.AddIndex(index=TEXT),
        c.RemoveConstraint(constraint=UNIQUE),
        c.RemoveIndex(index=NAME),
    ]
    assert not reversal.lossy


def test_a_migration_is_made_for_the_app_the_database_names_and_for_the_one_that_made_it():
    new = snapshot(constraints=[USERS], indexes=[NAME])
    for model in new["models"].values():
        model["module"] = "main.models"
    result = plan(MigrationGraph(), new, ["main", "users"])
    by_app = {m.app: [type(ch) for ch in m.changes] for m in result.migrations}
    assert c.AddConstraint in by_app["users"] and c.AddConstraint not in by_app["main"]
    assert c.AddIndex in by_app["main"]  # (no app named: the first)

    # dropping it later is for the app that made it
    graph = MigrationGraph.of(result.migrations)
    gone = snapshot(indexes=[NAME])
    for model in gone["models"].values():
        model["module"] = "main.models"
    later = plan(graph, gone, ["main", "users"])
    assert [(m.app, [type(ch) for ch in m.changes]) for m in later.migrations] == [
        ("users", [c.RemoveConstraint])
    ]
    assert graph.owners()["unique:PGUser(username)"] == "users"


def test_structure_is_part_of_what_the_migrations_come_to():
    migration = Migration(
        app="x", name="0001_initial", changes=(c.AddIndex(index=NAME),)
    )
    graph = MigrationGraph.of([migration])
    assert graph.state()["indexes"] == [NAME]
