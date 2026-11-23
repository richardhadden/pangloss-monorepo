"""The migrations of `pangloss-library`: applied in order on an empty database they give its models (with the label
index of each class of suggestion), and a project made before `IdentificationFromText` and
`IdentificationByToolchainFromText` is brought up to them with changes that are all safe"""

import copy
import importlib
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_models import Document, Entity
from pangloss_models.migrations import build_snapshot, diff
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, graph_of
from pangloss_models.migrations.startup import structure_of
from pangloss_testing.backends import under_test
from pangloss_testing.under_test import migration_backend as backend

from .helpers import index_labels
from .migration_support import declare, migrate

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEW = ("IdentificationFromText", "IdentificationByToolchainFromText")


def has_label_indexes() -> bool:
    """(Neo4j finds the nodes of a label by its own lookup index: an index of the kind `label` makes nothing there)"""
    return under_test().name != "neo4j"


def library():
    # (the registry was reset, and a module is only run once: the library's models are declared again)
    import pangloss_library.models

    return importlib.reload(pangloss_library.models)


def only_the_library():
    library()
    return SimpleNamespace()


def a_project():
    lib = library()

    class Person(Entity):
        pass

    class Statement(Document):
        by: Person | lib.Identification[Person]  # ty: ignore[invalid-type-form]

    return SimpleNamespace(Person=Person, Statement=Statement)


def without_the_two(snapshot: dict) -> dict:
    """The snapshot as it was before the two classes: neither they, their index, nor an option of them"""
    old = copy.deepcopy(snapshot)
    for name in NEW:
        old["models"].pop(name, None)

    def drop(options: list) -> list:
        kept = [option for option in options if option.get("type") not in NEW]
        for option in kept:
            for param in (option.get("params") or {}).values():
                param["options"] = drop(param["options"])
        return kept

    for model in old["models"].values():
        for field in model.get("fields", []):
            if "options" in field:
                field["options"] = drop(field["options"])
    old["indexes"] = [
        index for index in old.get("indexes", []) if index.get("label") not in NEW
    ]
    return old


@no_type_check
async def test_the_library_migrations_apply_in_order_and_give_its_models(
    db_driver, clear_database
):
    migrations = graph_of(["pangloss_library"]).order()
    assert [m.name[:4] for m in migrations] == ["0001", "0002", "0003", "0004", "0005"]
    await backend.ensure_ready()
    state = await backend.apply(migrations, EMPTY_SNAPSHOT)

    declare(only_the_library)
    models = build_snapshot(structure_of(backend))
    # (the backend's own indexes and keys are its migrations', not the library's)
    models["indexes"] = [
        index for index in models["indexes"] if index["label"] in models["models"]
    ]
    models["constraints"] = []
    # (nothing left between what the migrations made and the models)
    assert not diff(state, models).changes
    assert [index["label"] for index in models["indexes"]] == [
        "IdentificationByToolchain",
        "IdentificationByToolchainFromText",
    ]
    if has_label_indexes():
        assert {"IdentificationByToolchain", "IdentificationByToolchainFromText"} <= (
            index_labels(db_driver)
        )


@no_type_check
async def test_a_project_made_before_the_two_classes_is_brought_up_to_them(
    db_driver, clear_database
):
    m, _ = declare(a_project)
    new = build_snapshot(structure_of(backend))
    old = without_the_two(new)
    # (written before: an identification by hand)
    john = (await m.Person.Create(label="John").save()).id
    before = await m.Statement.Create(
        label="Before",
        by={"type": "Identification", "target": [{"type": "Person", "id": john}]},
    ).save()

    changes = await migrate(old, new)
    assert sorted(change.kind for change in changes) == [
        "AddIndex",
        "AlterRelationTarget",
        "CreateModel",
        "CreateModel",
    ]
    assert {change.safety for change in changes} == {"safe"}
    if has_label_indexes():
        assert "IdentificationByToolchainFromText" in index_labels(db_driver)

    # what was written is read as it was, and the two classes can be written
    assert (await m.Statement.get(before.id)).by.type == "Identification"
    after = await m.Statement.Create(
        label="After",
        by={
            "type": "IdentificationFromText",
            "text": "Jon",
            "target": [{"type": "Person", "id": john}],
        },
    ).save()
    read = (await m.Statement.get(after.id)).by
    assert (read.type, read.text) == ("IdentificationFromText", "Jon")
