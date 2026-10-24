"""Changes as data, and applied to a snapshot"""

import json
from typing import no_type_check

import pytest
from migration_support import changes, snapshot_of
from pangloss_models.migrations import (
    apply_change,
    change_from_dict,
    data_view,
    replay,
)
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.state import HANDLERS
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation


def all_change_types() -> list[type[c.Change]]:
    types, pending = [], list(c.Change.__subclasses__())
    while pending:
        cls = pending.pop()
        types.append(cls)
        pending.extend(cls.__subclasses__())
    return types


def test_every_change_can_be_applied_to_a_snapshot():
    # (adding a change without saying what it does to the snapshot would break `replay`)
    missing = [cls.__name__ for cls in all_change_types() if cls not in HANDLERS]
    assert missing == []


@no_type_check
def test_changes_are_data_that_can_be_written_and_read():
    def before():
        class Person(Entity):
            pass

        class Statement(Document):
            person: Person

    def after():
        class IdentifiedAs[T](ReifiedRelation[T]):
            certainty: int

        class Person(Entity):
            born: int

        class Statement(Document):
            person: IdentifiedAs[Person]

    found = changes(before, after).changes
    assert found  # (a wrap, a new model and a new field)
    written = json.loads(json.dumps([change.to_dict() for change in found]))
    read = [change_from_dict(entry) for entry in written]
    assert read == found
    assert all("safety" in entry and "change" in entry for entry in written)

    # ... and a change that was read applies like the one that was found
    old = snapshot_of(before)
    assert replay(old, read) == replay(old, found)


def test_an_unknown_change_is_refused():
    with pytest.raises(ValueError, match="no change called Nonsense"):
        change_from_dict({"change": "Nonsense"})


@no_type_check
def test_applying_a_change_does_not_change_the_snapshot_given():
    def declare():
        class Person(Entity):
            name: str

    snapshot = data_view(snapshot_of(declare))
    before = json.dumps(snapshot, sort_keys=True)
    after = apply_change(
        snapshot, c.RemoveField(model="Person", name="name", field_kind="literal")
    )
    assert json.dumps(snapshot, sort_keys=True) == before
    assert after["models"]["Person"]["fields"] == []


@no_type_check
def test_answers_are_kept_with_the_change():
    change = c.AddField(
        model="Person",
        name="born",
        field_kind="literal",
        needs_value=True,
        default=1900,
    )
    assert change_from_dict(change.to_dict()).default == 1900
    wrap = c.WrapRelation(
        model="Statement",
        name="person",
        wrapper="IdentifiedAs",
        wrapper_kind="reifiedRelation",
        defaults={"certainty": 3},
    )
    assert change_from_dict(wrap.to_dict()).defaults == {"certainty": 3}
