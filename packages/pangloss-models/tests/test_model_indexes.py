"""The indexes that the models ask for: a label index for each class of document and entity, and the fields
that a class names in `indexes`"""

import datetime

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.indexes import model_indexes
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.planner import app_of_change
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import Trait


def label(name):
    return {"kind": "label", "label": name, "properties": []}


def prop(name, field):
    return {"kind": "label+property", "label": name, "properties": [field]}


def test_each_class_of_document_and_entity_has_a_label_index_and_nothing_else_does():
    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Poet(Person):
        pass

    class Date(Embedded):
        when: datetime.date

    class Negative[T](SemanticSpace[T]):
        pass

    class Note(Document):
        _meta = Document.Meta(abstract=True)
        when: Date

    class Letter(Note):
        pass

    initialise()

    # (an abstract parent too: a search of it starts at its label; not a trait, an embedded object or a space)
    assert model_indexes() == [
        label("Letter"),
        label("Note"),
        label("Person"),
        label("Poet"),
    ]


def test_a_class_can_ask_for_an_index_of_a_field_or_of_its_label():
    class Letter(Document):
        _meta = Document.Meta(indexes=["year", "label"])
        year: int
        tags: list[str]

    class Person(Entity):
        _meta = Entity.Meta(indexes=["born"])
        born: datetime.date | None = None

    initialise()

    assert model_indexes() == [
        label("Letter"),
        prop("Letter", "year"),
        prop("Letter", "label"),
        label("Person"),
        prop("Person", "born"),
    ]


def test_the_fields_asked_for_are_not_inherited():
    class Letter(Document):
        _meta = Document.Meta(indexes=["year"])
        year: int

    class Draft(Letter):
        pass

    initialise()

    # (the nodes of a Draft have the label Letter, so the index is of them too)
    assert prop("Draft", "year") not in model_indexes()
    assert prop("Letter", "year") in model_indexes()


@pytest.mark.parametrize(
    "names, message",
    [
        (["nothing"], "'nothing', which is not a field"),
        (["owner"], "cannot be indexed"),
        (["year", "year"], "twice"),
    ],
)
def test_what_cannot_be_indexed_is_refused_when_the_models_are_initialised(
    names, message
):
    class Person(Entity):
        pass

    class Letter(Document):
        _meta = Document.Meta(indexes=names)
        year: int
        owner: Person

    with pytest.raises(PanglossMetaError, match=message):
        initialise()


def test_an_index_of_a_model_is_made_by_the_app_the_model_is_in():
    class Letter(Document):
        pass

    initialise()
    entry = label("Letter")
    new = {
        "models": {"Letter": {"module": "letters.models"}},
        "enums": {},
        "indexes": [entry],
    }
    apps = ["pangloss_memgraph", "letters"]

    assert app_of_change(c.AddIndex(index=entry), new, {}, apps) == "letters"
    # (and one that is not of a model, or whose app made it, as before)
    other = {"kind": "label", "label": "Elsewhere", "properties": []}
    assert app_of_change(c.AddIndex(index=other), new, {}, apps) == "pangloss_memgraph"
    made_by = {"label:Letter()": "pangloss_memgraph"}
    assert (
        app_of_change(c.RemoveIndex(index=entry), new, made_by, apps)
        == "pangloss_memgraph"
    )


def test_an_embedded_class_has_indexes_only_if_it_asks():
    class Date(Embedded):
        _meta = Embedded.Meta(indexes=["sort_day"])
        sort_day: int | None = None

    class ExactDate(Date):
        year: int

    class Plain(Embedded):
        text: str

    class Note(Document):
        when: Date | Plain

    initialise()
    entries = model_indexes()
    assert prop("Date", "sort_day") in entries
    assert not [e for e in entries if e["label"] in ("ExactDate", "Plain")]
    assert label("Note") in entries and label("Date") not in entries


def test_an_embedded_class_cannot_index_a_label_or_an_unknown_field():
    class Bad(Embedded):
        _meta = Embedded.Meta(indexes=["label"])
        year: int

    class Note(Document):
        when: Bad

    with pytest.raises(PanglossMetaError):
        initialise()
