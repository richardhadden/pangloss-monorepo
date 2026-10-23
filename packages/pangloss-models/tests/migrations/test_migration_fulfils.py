"""`Fulfils` in the snapshot, and the change that works out the labels again"""

from typing import Annotated, no_type_check

from migration_support import changes, snapshot_of
from pangloss_models.field_definitions import FieldSubclassing
from pangloss_models.migrations import changes as c
from pangloss_models.migrations import data_view, diff, replay
from pangloss_models.migrations.reverse import reverse_changes
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import Fulfils


@no_type_check
def plain():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Dated(Document):
        who: Person
        place: Place

    class Meeting(Document):
        attendee: Person
        place: Place


@no_type_check
def fulfilling():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Dated(Document):
        who: Person
        place: Place

    class Meeting(Document, Fulfils[Dated]):
        attendee: Annotated[
            Person,
            RelationConfig(subclasses_parent_fields=[FieldSubclassing("who", field_on_model=Dated)]),
        ]


@no_type_check
def two_that_fulfil_different_classes():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Dated(Document):
        who: Person
        place: Place

    class Owned(Document):
        owner: Person

    class Meeting(Document, Fulfils[Dated]):
        attendee: Annotated[
            Person,
            RelationConfig(subclasses_parent_fields=[FieldSubclassing("who", field_on_model=Dated)]),
        ]

    class Deed(Document, Fulfils[Owned]):
        holder: Annotated[
            Person,
            RelationConfig(subclasses_parent_fields=[FieldSubclassing("owner", field_on_model=Owned)]),
        ]


def test_a_model_that_fulfils_nothing_has_no_fulfils_in_its_entry():
    snapshot = snapshot_of(plain)
    assert all("fulfils" not in model for model in snapshot["models"].values())


def test_what_a_model_fulfils_is_in_its_entry_and_each_has_its_own():
    snapshot = snapshot_of(two_that_fulfil_different_classes)
    assert [e["class"] for e in snapshot["models"]["Meeting"]["fulfils"]] == ["Dated"]
    assert [e["class"] for e in snapshot["models"]["Deed"]["fulfils"]] == ["Owned"]
    assert snapshot["models"]["Deed"]["fulfils"][0]["fields"] == {"owner": "holder"}


def test_beginning_and_ceasing_to_fulfil_is_found_and_undone():
    old, new = snapshot_of(plain), snapshot_of(fulfilling)

    found = changes(plain, fulfilling).changes  # (replay gives the new snapshot: checked there)
    recompute = [ch for ch in found if isinstance(ch, c.RecomputeFulfils)]
    assert [ch.model for ch in recompute] == ["Meeting"]
    assert recompute[0].before == [] and recompute[0].after[0]["class"] == "Dated"
    assert recompute[0].safety == "transforming"
    assert found[-1] is recompute[0]  # (last: it is worked out from the models as they then are)

    reversal = reverse_changes(found, data_view(old))
    assert replay(replay(old, found), reversal.changes) == data_view(old)
    undone = [ch for ch in reversal.changes if isinstance(ch, c.RecomputeFulfils)]
    assert undone[0].before == recompute[0].after and undone[0].after == []
    assert undone[0].fulfils == []

    # ... and the other way round
    back = diff(new, old).changes
    assert [ch.model for ch in back if isinstance(ch, c.RecomputeFulfils)] == ["Meeting"]


def test_nothing_is_found_when_nothing_about_fulfilment_changed():
    assert not any(isinstance(ch, c.RecomputeFulfils) for ch in changes(fulfilling, fulfilling).changes)
