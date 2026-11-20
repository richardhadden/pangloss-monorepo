"""A relation that a generic wrapper declares optional (`Person | None`, `Note | None`, `Cites[Note] | None`) may be
left out in each use of the wrapper, as in the wrapper's own models. (The models of a use were given its relations
again without the rule, and so required them: found with `MatchesCriteria.description`)"""

from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Cites,
    Computed,
    Document,
    Entity,
    ReifiedRelation,
    initialise,
)


@pytest.fixture
@no_type_check
def models():
    class Person(Entity):
        pass

    class Note(Document):
        text: str

    class Wrap[T](ReifiedRelation[T]):
        cited: Cites[Note] | None = None
        someone: Person | None = None
        note: Note | None = None
        extra: str | None = None

    class Computing[T](ReifiedRelation[T]):
        cited: Cites[Note] | None = None
        target: Annotated[list[T], Computed()] = []

    class Activity(Document):
        carried_out_by: list[Person | Wrap[Person]]
        computing: list[Computing[Person]]

    initialise()
    return Person, Note, Activity


@no_type_check
def test_an_optional_relation_of_a_generic_wrapper_may_be_left_out_in_its_use(models):
    Person, Note, Activity = models
    made = Activity.Create(
        label="A",
        carried_out_by=[{"type": "Wrap", "target": []}],
        computing=[{"type": "Computing"}],
    )
    wrap = made.carried_out_by[0]
    assert wrap.cited is None and wrap.someone is None and wrap.note is None
    assert made.computing[0].cited is None


@no_type_check
def test_it_may_still_be_given(models):
    Person, Note, Activity = models
    made = Activity.Create(
        label="A",
        carried_out_by=[
            {
                "type": "Wrap",
                "target": [],
                "cited": {"type": "Note", "id": "01a1f88b-50b3-75a2-8959-dc7b99700bc8"},
                "someone": {
                    "type": "Person",
                    "id": "01a1f88b-50b3-75a2-8959-dc7b99700bc9",
                },
            }
        ],
        computing=[],
    )
    wrap = made.carried_out_by[0]
    assert str(wrap.cited.target_id) == "01a1f88b-50b3-75a2-8959-dc7b99700bc8"
    assert wrap.someone.type == "Person"
