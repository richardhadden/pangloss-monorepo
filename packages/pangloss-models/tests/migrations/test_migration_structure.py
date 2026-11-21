"""The database's own structure (indexes and constraints) as changes"""

import copy
import re
from typing import no_type_check

import pytest
from migration_support import snapshot_of
from pangloss_models import PanglossMigrationError
from pangloss_models.migrations import Migration, data_view, diff, replay, snapshot_hash
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, MigrationGraph
from pangloss_models.migrations.planner import plan
from pangloss_models.migrations.reverse import reverse_changes
from pangloss_models import Entity

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


# ---------------------------------------------------------------------------
# A vector index
# ---------------------------------------------------------------------------

VECTOR = {
    "kind": "vector",
    "name": "thing_vectors",
    "label": "Thing",
    "properties": ["vector"],
    "dimension": 4,
    "metric": "cos",
    "capacity": 64,
}


def test_a_vector_index_is_described_with_its_settings():
    assert (
        c.AddIndex(index=VECTOR).describe()
        == "Create the vector index thing_vectors on :Thing(vector) (dimension 4, metric cos)"
    )
    assert (
        c.RemoveIndex(index=VECTOR)
        .describe()
        .startswith("Drop the vector index thing_vectors on :Thing(vector)")
    )
    # (the others as they were)
    assert (
        c.AddIndex(index=TEXT).describe()
        == "Create the text index thing_text on :Thing(label)"
    )
    assert c.AddIndex(index=NAME).describe() == "Create the index :Thing(name)"


@pytest.mark.parametrize(
    "change, says",
    [
        ({"name": None}, "has no name"),
        ({"dimension": None}, "has no dimension"),
        ({"metric": None}, "has no metric"),
        ({"label": None}, "has no label"),
        ({"name": None, "dimension": None}, "has no name, dimension"),
        ({"properties": []}, "exactly one property"),
        ({"properties": ["a", "b"]}, "exactly one property"),
        ({"metric": "l2sq"}, "metric must be one of cos"),
        ({"dimension": 0}, "dimension must be a whole number above 0"),
        ({"dimension": "4"}, "dimension must be a whole number above 0"),
        ({"dimension": True}, "dimension must be a whole number above 0"),
        ({"capacity": -1}, "capacity must be a whole number above 0"),
        ({"quantization": "no"}, "quantization must be True or False"),
        ({"quantization": 0}, "quantization must be True or False"),
        ({"name": "two words"}, "a name a query can have"),
        ({"label": "Not-a-label"}, "is not a label"),
    ],
)
def test_a_vector_index_without_what_it_needs_is_refused_naming_it(change, says):
    entry = {
        **{k: v for k, v in VECTOR.items() if change.get(k, "") is not None},
        **{k: v for k, v in change.items() if v is not None},
    }
    for kind in (c.AddIndex, c.RemoveIndex):
        with pytest.raises(PanglossMigrationError, match=re.escape(says)):
            kind(index=entry)
    # (from a migration file too)
    with pytest.raises(PanglossMigrationError, match=re.escape(says)):
        c.change_from_dict({"change": "AddIndex", "index": entry})


def test_a_vector_index_needs_no_capacity():
    entry = {k: v for k, v in VECTOR.items() if k != "capacity"}
    assert c.AddIndex(index=entry).index == entry


def test_a_vector_index_may_say_whether_it_is_quantized_and_a_change_of_it_is_a_remove_and_an_add():
    plain = {**VECTOR, "quantization": False}
    assert c.AddIndex(index=plain).index == plain
    assert c.AddIndex(index={**VECTOR, "quantization": True}).index["quantization"]
    old, new = snapshot(indexes=[VECTOR]), snapshot(indexes=[plain])
    assert diff(old, new).changes == [
        c.RemoveIndex(index=VECTOR),
        c.AddIndex(index=plain),
    ]
    # (from a migration file too)
    assert c.change_from_dict({"change": "AddIndex", "index": plain}) == c.AddIndex(
        index=plain
    )


def test_a_vector_index_with_another_dimension_is_a_remove_and_an_add_the_remove_first():
    other = {**VECTOR, "dimension": 8}
    old, new = snapshot(indexes=[NAME, VECTOR]), snapshot(indexes=[NAME, other])
    result = diff(old, new)
    # (the same name: the old one has to be gone before the new is made)
    assert result.changes == [c.RemoveIndex(index=VECTOR), c.AddIndex(index=other)]
    assert replay(old, result.changes) == data_view(new)
    # ... and undone in the same order: the new one dropped, the old made again
    reversal = reverse_changes(result.changes, data_view(old))
    assert reversal.changes == [c.RemoveIndex(index=other), c.AddIndex(index=VECTOR)]
    # (any setting of it: the capacity too)
    assert diff(old, snapshot(indexes=[NAME, {**VECTOR, "capacity": 128}])).changes == [
        c.RemoveIndex(index=VECTOR),
        c.AddIndex(index={**VECTOR, "capacity": 128}),
    ]
    # (nothing where nothing changed)
    assert diff(old, snapshot(indexes=[VECTOR, NAME])).changes == []


def test_a_vector_index_removed_for_good_is_dropped_before_what_is_made():
    old, new = snapshot(indexes=[VECTOR]), snapshot(indexes=[NAME])
    assert diff(old, new).changes == [
        c.RemoveIndex(index=VECTOR),
        c.AddIndex(index=NAME),
    ]
    # (the other kinds are dropped last, as before)
    assert c.RemoveIndex(index=NAME).phase > c.AddIndex(index=NAME).phase


def test_a_vector_index_an_app_asks_for_is_in_its_migration():
    new = snapshot(indexes=[{**VECTOR, "app": "vectors"}])
    for model in new["models"].values():
        model["module"] = "main.models"
    result = plan(MigrationGraph(), new, ["main", "vectors"])
    by_app = {m.app: m.changes for m in result.migrations}
    assert by_app["vectors"] == (c.AddIndex(index=VECTOR),)
    assert MigrationGraph.of(result.migrations).state()["indexes"] == [VECTOR]


# ---------------------------------------------------------------------------
# What installed apps ask for (`<app>.structure`)
# ---------------------------------------------------------------------------


@pytest.fixture
def apps_with_structure(monkeypatch):
    """Installs throwaway apps whose `structure` modules are given: `install({"app": module_attributes})`"""
    import sys
    import types
    from types import SimpleNamespace

    from pangloss_core import settings as core_settings

    def install(structures: dict[str, dict]) -> None:
        for app, attributes in structures.items():
            monkeypatch.setitem(sys.modules, app, types.ModuleType(app))
            module = types.ModuleType(f"{app}.structure")
            for name, value in attributes.items():
                setattr(module, name, value)
            monkeypatch.setitem(sys.modules, f"{app}.structure", module)
        monkeypatch.setattr(
            core_settings,
            "SETTINGS",
            SimpleNamespace(INSTALLED_APPS=[*structures, "pg_test_no_such_app"]),
            raising=False,
        )

    return install


def test_an_app_s_structure_is_its_lists_and_what_its_functions_give_stamped_with_the_app(
    apps_with_structure,
):
    from pangloss_models.indexes import installed_app_structure

    apps_with_structure(
        {
            "pg_test_lists": {"INDEXES": [NAME], "CONSTRAINTS": [UNIQUE]},
            "pg_test_functions": {
                "INDEXES": [TEXT],
                "indexes": lambda: [VECTOR],
                "constraints": lambda: [{**UNIQUE, "label": "Other"}],
            },
        }
    )
    indexes, constraints = installed_app_structure()
    assert indexes == [
        {**NAME, "app": "pg_test_lists"},
        {**TEXT, "app": "pg_test_functions"},
        {**VECTOR, "app": "pg_test_functions"},
    ]
    assert constraints == [
        {**UNIQUE, "app": "pg_test_lists"},
        {**UNIQUE, "label": "Other", "app": "pg_test_functions"},
    ]


def test_an_entry_that_names_an_installed_app_is_that_app_s_and_one_naming_another_is_refused(
    apps_with_structure,
):
    from pangloss_models.indexes import installed_app_structure

    apps_with_structure(
        {
            "pg_test_project": {},
            "pg_test_library": {
                "indexes": lambda: [{**VECTOR, "app": "pg_test_project"}]
            },
        }
    )
    indexes, _ = installed_app_structure()
    assert indexes == [{**VECTOR, "app": "pg_test_project"}]

    apps_with_structure(
        {"pg_test_library": {"indexes": lambda: [{**VECTOR, "app": "elsewhere"}]}}
    )
    with pytest.raises(
        PanglossMigrationError, match="'elsewhere', which is not installed"
    ):
        installed_app_structure()
