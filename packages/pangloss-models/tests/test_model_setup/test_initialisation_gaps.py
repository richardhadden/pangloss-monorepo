"""Tests for paths of `initialise_models/` that no other test reaches, found by tracing which lines
the suite executes (see `packages/pangloss-models/todo.md`, "initialise_models/: review").

A bug found in the review is first written as a test marked `xfail(strict=True)`: it fails, and the
suite fails when it starts to pass, so the mark is removed with the fix. (All of those found have been
fixed; the last section keeps their tests.)
"""

import datetime
import warnings
from typing import Annotated, no_type_check
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossModelError
from pangloss_models.field_definitions import FieldBinding, FieldSubclassing
from pangloss_models.initialise_models import (
    builder,
    initialise_create_db_model,
    initialise_create_model,
    initialise_update_db_model,
    initialise_update_model,
    initialise_view_model,
)
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import Fulfils, ViaEdge
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import Trait
from pangloss_models.model_registry import ModelRegistry
from pydantic import Field, ValidationError

ACTION_MODELS = ["Create", "CreateDB", "Update", "UpdateDB", "View"]


def names_in(annotation) -> set[str]:
    """The names of the classes in an annotation (through lists, `Annotated` and unions)"""
    from typing import get_args

    found = set()
    if isinstance(annotation, type):
        found.add(annotation.__name__)
    for arg in get_args(annotation):
        found |= names_in(arg)
    return found


def classes_in(annotation) -> list[type]:
    """The classes in an annotation (through lists, `Annotated` and unions), in order"""
    from typing import get_args

    found = [annotation] if isinstance(annotation, type) else []
    for arg in get_args(annotation):
        found.extend(classes_in(arg))
    return found


# --- Generic relations with an edge model ---------------------------------------------------------


@pytest.mark.parametrize("model", ACTION_MODELS)
@no_type_check
def test_a_relation_to_a_generic_with_an_edge_model_has_the_edge_variant(model):
    """`ViaEdge[Wrapper[X], Edge]`: the relation carries properties of its own. Every generated
    model has the variant of the wrapper with the edge's fields (`...ViaWeight`)."""

    class Weight(EdgeModel):
        weight: float

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Statement(Document):
        witnesses: list[ViaEdge[InRole[Person], Weight]]

    initialise()

    field = getattr(Statement, model).model_fields["witnesses"]
    names = names_in(field.annotation)
    assert any(name.endswith("ViaWeight") for name in names), names
    assert all("InRole" in name for name in names), names


@no_type_check
def test_an_edge_variant_of_a_generic_takes_the_edge_properties():
    class Weight(EdgeModel):
        weight: float

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Statement(Document):
        witnesses: list[ViaEdge[InRole[Person], Weight]]

    initialise()

    # (the edge model is the relation to the wrapper's: its targets have none, unless the wrapper
    # declares one of its own)
    properties = {"weight": 0.5}
    statement = Statement.Create(
        label="S",
        witnesses=[
            {
                "type": "InRole",
                "role": "witness",
                "edgeProperties": properties,
                "target": [{"type": "Person", "id": uuid7()}],
            }
        ],
    )
    assert statement.witnesses[0].edge_properties.weight == 0.5
    assert not hasattr(statement.witnesses[0].target[0], "edge_properties")

    with pytest.raises(ValidationError):  # (the properties are required)
        Statement.Create(
            label="S",
            witnesses=[
                {
                    "type": "InRole",
                    "role": "witness",
                    "target": [{"type": "Person", "id": uuid7()}],
                }
            ],
        )


@pytest.mark.parametrize("model", ["Create", "Update", "View", "CreateDB", "UpdateDB"])
@no_type_check
def test_a_generic_inside_a_generic_with_an_edge_model_has_only_the_edge_variant(model):
    """A wrapper in the type argument of another wrapper, with an edge model on it: like every
    other relation with an edge model, only the variant with the edge's properties is offered (the
    plain one as well made the discriminated union of the View model fail when initialising)"""

    class Weight(EdgeModel):
        weight: float

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Negative[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        text: str
        about: Negative[ViaEdge[InRole[Person], Weight]]

    initialise()

    outer = classes_in(getattr(Statement, model).model_fields["about"].annotation)
    negatives = [c for c in outer if c.__name__.startswith("Negative[")]
    assert negatives
    for negative in negatives:
        inner = {c.__name__ for c in classes_in(negative.model_fields["contents"].annotation)}
        roles = {n for n in inner if n.startswith("InRole[")}
        assert roles, inner
        assert all("ViaWeight" in n for n in roles), roles


# --- Models with no label --------------------------------------------------------------------------


@no_type_check
def test_a_document_that_requires_no_label_has_no_label_to_refer_to_it_by():
    """The model that refers to a document when it has been written or is listed (`ReferenceView`) cannot
    require a label of one that has none (saving one failed: `NoteReferenceView label: Field required`).
    (Only documents have the option: an entity always has a label.)"""

    class Thing(Document):
        _meta = Document.Meta(require_label=False)
        text: str

    class Labelled(Document):
        text: str

    initialise()

    thing = Thing.ReferenceView(id=uuid7(), type="Thing")
    assert thing.label is None
    assert not Thing.ReferenceView.model_fields["label"].is_required()
    assert Labelled.ReferenceView.model_fields["label"].is_required()  # (the others, as ever)


# --- Conversion for writing ------------------------------------------------------------------------


@no_type_check
def test_a_fulfilling_class_with_a_relation_to_an_entity_that_can_be_named_can_be_written():
    """`ensure_id` of the database model of an entity was given a model, not a dict, when a union tried
    the entity itself (`create_inline`) on a reference to it: `AttributeError: ... has no attribute
    'get'`, which pydantic does not take as that member not fitting"""

    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True, create_inline=True)

    class Office(Entity):
        pass

    class Appointment(Document):
        holder: Person
        office: Office

    class Grant(Document, Fulfils[Appointment]):
        granted_by: Annotated[
            Person,
            RelationConfig(
                subclasses_parent_fields=[FieldSubclassing("holder", field_on_model=Appointment)]
            ),
        ]

    initialise()

    person, office = uuid7(), uuid7()
    grant = Grant.Create(
        label="G",
        granted_by={"type": "Person", "id": person},
        office={"type": "Office", "id": office},
    )
    written = grant._to_db_model()
    assert written.granted_by.id == person
    assert written.office.id == office


# --- A class that can be given an id may be created without one ----------------------------------


@pytest.mark.parametrize("kind", [Entity, Document])
@no_type_check
def test_a_class_that_can_be_given_an_id_can_be_created_without_one(kind):
    """`create_with_id` allows an id to be given (with `create_new`); it does not require one. A new one
    that was made without an id could not be written: its database model made an id and then
    refused it, as an id without `create_new`"""

    class Thing(kind):
        _meta = kind.Meta(create_with_id=True)

    initialise()

    created = Thing.Create(label="T")
    assert created.id is None

    written = created._to_db_model()
    assert isinstance(written, Thing.CreateDB)
    assert written.id is not None

    # (with an id, as before: the two go together)
    named = Thing.Create(label="T", id=uuid7(), create_new=True)._to_db_model()
    assert named.create_new is True
    with pytest.raises(ValidationError):
        Thing.Create(label="T", id=uuid7())


@no_type_check
def test_the_database_model_of_a_new_thing_has_create_new_when_it_makes_the_id():
    class Thing(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()

    assert Thing.CreateDB(label="T").create_new is True
    assert Thing.CreateDB(label="T", createNew=True).create_new is True
    with pytest.raises(ValidationError, match="create_new=True flag must also be set"):
        Thing.CreateDB(label="T", id=uuid7())


# --- Edge models on relations to documents and wrappers -----------------------------------------


@pytest.mark.parametrize("model", ACTION_MODELS)
@no_type_check
def test_an_edge_variant_has_all_the_fields_of_what_it_is_a_variant_of(model):
    """`ViaEdge[Note, Weight]` and `ViaEdge[InRole[Person], Weight]` offer the document or wrapper with
    the edge's properties added: nothing of the document or wrapper is lost. (The variant had only
    `type` and `edge_properties`, so a note's label and text, and a wrapper's role and targets, were
    silently left out of what was written.)"""

    class Weight(EdgeModel):
        weight: float

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Note(Document):
        text: str

    class Activity(Document):
        witnesses: list[ViaEdge[InRole[Person], Weight]]
        notes: list[ViaEdge[Note, Weight]]

    initialise()

    fields = getattr(Activity, model).model_fields
    for field, expected in (("witnesses", {"role", "target"}), ("notes", {"label", "text"})):
        variants = [
            c for c in classes_in(fields[field].annotation) if c.__name__.endswith("ViaWeight")
        ]
        assert variants, field
        for variant in variants:
            assert "edge_properties" in variant.model_fields
            missing = (expected & set(getattr(variant, "__base__").model_fields)) - set(
                variant.model_fields
            )
            assert not missing, (variant.__name__, missing)
            # (at least, what the document or wrapper itself has)
            assert expected - {"label"} <= set(variant.model_fields), (variant.__name__, field)


@no_type_check
def test_what_is_given_for_a_relation_with_an_edge_model_is_kept():
    class Weight(EdgeModel):
        weight: float

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Note(Document):
        text: str

    class Activity(Document):
        witnesses: list[ViaEdge[InRole[Person], Weight]]
        notes: list[ViaEdge[Note, Weight]]

    initialise()

    person_id = uuid7()
    activity = Activity.Create(
        label="A",
        witnesses=[
            {
                "type": "InRole",
                "role": "witness",
                "target": [
                    {"type": "Person", "id": person_id, "edgeProperties": {"weight": 0.5}}
                ],
                "edgeProperties": {"weight": 0.5},
            }
        ],
        notes=[{"type": "Note", "label": "N", "text": "the text", "edgeProperties": {"weight": 0.9}}],
    )

    witness, note = activity.witnesses[0], activity.notes[0]
    assert witness.role == "witness"
    assert [t.id for t in witness.target] == [person_id]
    assert witness.edge_properties.weight == 0.5
    assert (note.label, note.text, note.edge_properties.weight) == ("N", "the text", 0.9)

    # ... and in what is written
    written = activity._to_db_model()
    assert written.witnesses[0].role == "witness"
    assert [t.id for t in written.witnesses[0].target] == [person_id]
    assert written.notes[0].text == "the text"

    # (a required part is still required)
    with pytest.raises(ValidationError):
        Activity.Create(
            label="A",
            witnesses=[],
            notes=[{"type": "Note", "label": "N", "edgeProperties": {"weight": 0.9}}],
        )


@no_type_check
def test_a_binding_goes_through_a_relation_with_an_edge_model():
    """(this raised `AttributeError: ... has no attribute 'target'`: the variant had no `target`)"""

    class Weight(EdgeModel):
        weight: float

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Activity(Document):
        year: int
        witnesses: list[ViaEdge[InRole[Person], Weight]]

    class Factoid(Document):
        year: int
        activities: Annotated[
            list[Activity],
            RelationConfig(
                bind_to_child_field=[FieldBinding(bound_field="year", child_fields=["year"])]
            ),
        ]

    initialise()

    factoid = Factoid.Create(
        label="F",
        year=1500,
        activities=[
            {
                "type": "Activity",
                "label": "A",
                "witnesses": [
                    {
                        "type": "InRole",
                        "role": "witness",
                        "target": [
                            {"type": "Person", "id": uuid7(), "edgeProperties": {"weight": 0.5}}
                        ],
                        "edgeProperties": {"weight": 0.5},
                    }
                ],
            }
        ],
    )
    assert factoid.activities[0].year == 1500
    assert factoid.activities[0].witnesses[0].role == "witness"


# --- Incoming relations ----------------------------------------------------------------------------


@no_type_check
def test_an_entity_has_an_incoming_relation_for_every_way_it_is_reached():
    """Directly, through a reified relation, a semantic space, a conjunction, or any of them inside
    another, from a document or from an embedded object"""
    from pangloss_models.model_bases.conjunction import Conjunction

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Negative[T](SemanticSpace[T]):
        pass

    class Causes[A, B](Conjunction):
        cause: A
        result: B

    class Date(Embedded):
        spaced_in_date: Negative[Person]

    class Statement(Document):
        direct: Person
        reified: InRole[Person]
        spaced: Negative[Person]
        joined: Causes[Person, Place]
        both: Negative[InRole[Person]]
        spaces: list[Negative[Person]]
        date: Date

    initialise()

    def incoming(entity):
        return {
            name: {(i.source.__name__, i.via_reified) for i in found}
            for name, found in entity._meta.field_definitions.incoming_fields.items()
        }

    assert incoming(Person) == {
        "direct_reverse": {("Statement", False)},
        "reified_reverse": {("Statement", True)},
        "spaced_reverse": {("Statement", True)},
        "joined_reverse": {("Statement", True)},
        "both_reverse": {("Statement", True)},
        "spaces_reverse": {("Statement", True)},
        "spaced_in_date_reverse": {("Statement", True)},
    }
    assert incoming(Place) == {"joined_reverse": {("Statement", True)}}
    assert {n for n in Person.HeadView.model_fields if n.endswith("_reverse")} == set(
        incoming(Person)
    )


@pytest.mark.parametrize("model", ["Update", "UpdateDB"])
@no_type_check
def test_what_a_generic_holds_of_its_own_can_be_given_as_an_update(model):
    """A document or an embedded object that a wrapper has of its own may be given as an update (with
    its id, so it keeps its identity) or as a new one, as it may be when held directly. (The model made for
    a use of the wrapper offered only the new one.)"""

    class Date(Embedded):
        when: datetime.date

    class Note(Document):
        text: str

    class Person(Entity):
        pass

    class Attested[T](ReifiedRelation[T]):
        note: Note
        dated: Date

    class Statement(Document):
        held_directly: Note
        who: Attested[Person]

    initialise()

    def offered(owner, field):
        fields = getattr(owner, model).model_fields
        return {c.__name__ for c in classes_in(fields[field].annotation)}

    # the model itself
    assert {"NoteUpdate", "NoteCreate"} <= {n.replace("DB", "") for n in offered(Statement, "held_directly")}

    # and the model made for a use of the wrapper
    wrapper = next(
        c for c in classes_in(getattr(Statement, model).model_fields["who"].annotation)
        if c.__name__.startswith("Attested[Person]") and c.__name__.endswith(model)
    )
    for field, new, existing in (("note", "NoteCreate", "NoteUpdate"), ("dated", "DateCreate", "DateUpdate")):
        names = {n.replace("DB", "") for n in {c.__name__ for c in classes_in(wrapper.model_fields[field].annotation)}}
        assert {new, existing} <= names, (field, names)


@no_type_check
def test_an_update_of_a_generic_keeps_the_identity_of_what_it_holds():
    class Note(Document):
        text: str

    class Person(Entity):
        pass

    class Attested[T](ReifiedRelation[T]):
        note: Note

    class Statement(Document):
        who: Attested[Person]

    initialise()

    note_id = uuid7()
    person = {"type": "Person", "id": uuid7()}
    # an existing wrapper (it has an id) with an existing note
    update = Statement.Update(
        id=uuid7(),
        label="S",
        who={
            "type": "Attested",
            "id": uuid7(),
            "target": [person],
            "note": {"type": "Note", "id": note_id, "label": "N", "text": "t"},
        },
    )
    assert isinstance(update.who.note, Note.Update)
    assert update.who.note.id == note_id

    # an existing wrapper with a new note
    new_note = Statement.Update(
        id=uuid7(),
        label="S",
        who={
            "type": "Attested",
            "id": uuid7(),
            "target": [person],
            "note": {"type": "Note", "label": "N", "text": "t"},
        },
    )
    assert isinstance(new_note.who.note, Note.Create)


@no_type_check
def test_bindings_reach_what_a_generic_holds_but_not_its_own_fields():
    """A binding fills the fields of the documents a wrapper holds (tested above), not the wrapper's own
    fields, which stay required (a pinned limitation: it is the same in every model)"""

    class Note(Document):
        text: str
        year: int

    class Person(Entity):
        pass

    class Attested[T](ReifiedRelation[T]):
        year: int
        note: Note

    class Factoid(Document):
        year: int
        who: Annotated[
            Attested[Person],
            RelationConfig(
                bind_to_child_field=[FieldBinding(bound_field="year", child_fields=["year"])]
            ),
        ]

    initialise()

    for model in ("Create", "Update", "View"):
        wrapper = next(
            c
            for c in classes_in(getattr(Factoid, model).model_fields["who"].annotation)
            if c.__name__.startswith("Attested[Person]")
        )
        assert wrapper.model_fields["year"].is_required(), model
        note = next(c for c in classes_in(wrapper.model_fields["note"].annotation) if "year" in c.model_fields)
        assert not note.model_fields["year"].is_required(), model


# --- Field bindings --------------------------------------------------------------------------------


class Date(Embedded):
    when: datetime.date


@pytest.mark.parametrize("model", ["Create", "Update", "View"])
@no_type_check
def test_a_binding_makes_an_embedded_field_of_the_child_optional(model):
    class Date(Embedded):
        when: datetime.date

    class Action(Document):
        happened: Date

    class Statement(Document):
        date: Date
        action: Annotated[
            Action,
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(bound_field="date", child_fields=["happened"])
                ]
            ),
        ]

    initialise()

    annotation = getattr(Statement, model).model_fields["action"].annotation
    bound = [c for c in classes_in(annotation) if "happened" in c.model_fields]
    assert bound
    for child in bound:
        field = child.model_fields["happened"]
        assert not field.is_required(), child.__name__
        assert field.default is None


@pytest.mark.parametrize("model", ["Create", "Update", "View"])
@no_type_check
def test_a_binding_makes_an_annotated_value_field_of_the_child_optional(model):
    class Noted[T](AnnotatedValue[T]):
        note: str

    class Action(Document):
        label_text: Noted[str]

    class Statement(Document):
        title: Noted[str]
        action: Annotated[
            Action,
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(bound_field="title", child_fields=["label_text"])
                ]
            ),
        ]

    initialise()

    annotation = getattr(Statement, model).model_fields["action"].annotation
    bound = [c for c in classes_in(annotation) if "label_text" in c.model_fields]
    assert bound
    for child in bound:
        field = child.model_fields["label_text"]
        assert not field.is_required(), child.__name__
        assert field.default is None


@no_type_check
def test_a_binding_reaches_a_document_inside_a_bound_update_generic():
    """Update of a document whose child is inside a wrapper: the bound field is not required there"""

    class Action(Document):
        year: int

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        year: int
        actions: Annotated[
            list[Negative[Action]],
            RelationConfig(
                bind_to_child_field=[FieldBinding(bound_field="year", child_fields=["year"])]
            ),
        ]

    initialise()

    payload = dict(
        label="F",
        year=1500,
        actions=[{"type": "Negative", "contents": [{"type": "Action", "label": "A"}]}],
    )
    assert Factoid.Create(**payload).actions[0].contents[0].type == "Action"
    assert Factoid.Update(id=uuid7(), **payload).actions[0].contents[0].type == "Action"


@no_type_check
def test_the_update_of_a_generic_has_its_own_fields_not_those_of_create():
    """`Negative[Action].Update` is the Update model of the wrapper: it has an `id`, and its fields
    are the Update ones (the bound model was built from `Create`'s fields)"""

    class Action(Document):
        year: int

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        actions: list[Negative[Action]]

    initialise()

    from typing import get_args

    annotation = Factoid.Update.model_fields["actions"].annotation
    updates = [
        a
        for union in get_args(get_args(annotation)[0])
        for a in get_args(union)
        if getattr(a, "__name__", "").endswith("Update")
    ]
    assert updates
    for update in updates:
        assert "id" in update.model_fields
        assert update.model_fields["id"].is_required()


# --- create_new needs an id ------------------------------------------------------------------------


@no_type_check
def test_create_new_without_an_id_is_refused():
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True, create_inline=True)

    initialise()

    with pytest.raises(ValidationError, match="an id must be provided"):
        Person.Create(label="P", create_new=True)
    with pytest.raises(ValidationError, match="create_new=True flag must also be set"):
        Person.Create(label="P", id=uuid7())
    assert Person.Create(label="P", id=uuid7(), create_new=True)


@no_type_check
def test_the_db_model_makes_an_id_when_none_is_given():
    """`CreateDB` has an `ensure_id` validator, so unlike `Create` it never lacks an id: with
    `create_new` and no id, one is made (so the second check of `check_create_and_id_present` in
    `initialise_create_db_model` is never reached)"""

    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True, create_inline=True)

    initialise()

    made = Person.CreateDB(label="P", createNew=True)
    assert made.id is not None
    # an id given without `create_new` is refused, as in `Create`
    with pytest.raises(ValidationError, match="create_new=True flag must also be set"):
        Person.CreateDB(label="P", id=uuid7())
    assert Person.CreateDB(label="P", id=uuid7(), createNew=True)


# --- Models with no label --------------------------------------------------------------------------


@pytest.mark.parametrize("model", ["Create", "CreateDB", "Update", "UpdateDB", "View", "HeadView"])
@no_type_check
def test_a_document_that_requires_no_label_has_none(model):
    class Note(Document):
        _meta = Document.Meta(require_label=False)
        body: str

    initialise()

    assert "label" not in getattr(Note, model).model_fields


# --- Reference models ------------------------------------------------------------------------------


@no_type_check
def test_reference_view_extra_fields_must_be_literal_fields_of_the_model():
    class Person(Entity):
        _meta = Entity.Meta(reference_view_extra_fields=["nope"])
        name: str

    with pytest.raises(PanglossModelError, match="reference_view_extra_fields 'nope'"):
        initialise()


@no_type_check
def test_reference_view_extra_fields_are_added_to_the_reference_view():
    class Person(Entity):
        _meta = Entity.Meta(reference_view_extra_fields=["name"])
        name: str
        age: int

    initialise()

    assert "name" in Person.ReferenceView.model_fields
    assert "age" not in Person.ReferenceView.model_fields


@no_type_check
def test_an_undefined_name_in_an_annotation_is_reported():
    class Person(Entity):
        pass

    class Factoid(Document):
        about: list[Person]
        later: list["NoSuchModel"]

    with pytest.raises(Exception, match="NoSuchModel"):
        initialise()


@no_type_check
def test_a_model_that_refers_to_itself_by_name_has_its_reference_models():
    class Person(Entity):
        pass

    class Factoid(Document):
        about: list[Person]
        see_also: list["Factoid"]

    initialise()

    assert Factoid.ReferenceView
    assert Person.ReferenceSet


# --- Field definitions -----------------------------------------------------------------------------


@no_type_check
def test_a_literal_list_with_a_relation_inside_is_refused():
    class Person(Entity):
        pass

    class Statement(Document):
        mixed: list[Person | int]

    with pytest.raises(PanglossModelError):
        initialise()


@no_type_check
def test_subclassing_a_field_by_name_that_the_parents_do_not_have():
    class Place(Entity):
        pass

    class Statement(Document):
        pass

    class Activity(Statement):
        where: Annotated[Place, RelationConfig(subclasses_parent_fields=["nowhere"])]

    with pytest.raises(PanglossModelError, match="does not exist on a parent class"):
        initialise()


@no_type_check
def test_a_field_of_a_fulfilled_class_can_be_subclassed_by_name():
    class Person(Entity):
        pass

    class Appointment(Document):
        holder: Person

    class Grant(Document, Fulfils[Appointment]):
        granted_to: Annotated[Person, RelationConfig(subclasses_parent_fields=["holder"])]

    initialise()

    definition = Grant._meta.fields["granted_to"]
    assert {s.field_name for s in definition.subclasses_parent_fields} == {"holder"}
    assert "holder" not in Grant.Create.model_fields  # (supplied by granted_to)


@no_type_check
def test_a_relation_cannot_narrow_a_literal_field():
    class Place(Entity):
        pass

    class Statement(Document):
        where: str

    class Activity(Statement):
        place: Annotated[Place, RelationConfig(subclasses_parent_fields=["where"])]

    with pytest.raises(PanglossModelError, match="which is not a relation"):
        initialise()


@no_type_check
def test_an_annotated_value_with_a_relation_is_refused():
    class Person(Entity):
        pass

    class WithPerson[T](AnnotatedValue[T]):
        who: Person

    class Statement(Document):
        text: WithPerson[str]

    with pytest.raises(PanglossModelError, match="does not support relations"):
        initialise()


@no_type_check
def test_a_relation_config_description_is_the_description_of_the_field():
    class Person(Entity):
        pass

    class Statement(Document):
        by: Annotated[Person, RelationConfig(description="Who did it")]

    initialise()

    assert Statement._meta.fields["by"].description == "Who did it"
    assert Statement.Create.model_fields["by"].description == "Who did it"


@no_type_check
def test_a_document_that_implements_a_trait_can_be_a_relation_target():
    class Event(Trait):
        pass

    class Meeting(Document, Event):
        text: str

    class Diary(Document):
        entries: list[Event]

    initialise()

    names = names_in(Diary.Create.model_fields["entries"].annotation)
    assert "MeetingCreate" in names


@no_type_check
def test_an_abstract_document_that_implements_a_trait_is_not_a_relation_target():
    """As an abstract document is not offered for a relation to a Document, it should not be
    offered for a relation to a trait that it implements"""

    class Event(Trait):
        pass

    class Gathering(Document, Event):
        _meta = Document.Meta(abstract=True)
        text: str

    class Meeting(Gathering):
        pass

    class Diary(Document):
        entries: list[Event]

    initialise()

    names = names_in(Diary.Create.model_fields["entries"].annotation)
    assert "MeetingCreate" in names
    assert "GatheringCreate" not in names


# --- Bugs found in the review (each was a strict xfail until fixed) ------------------------------------------


@no_type_check
def test_field_description_from_field():
    class Person(Entity):
        name: str = Field(description="The name")

    initialise()

    assert Person._meta.fields["name"].description == "The name"
    assert Person.Create.model_fields["name"].description == "The name"


@pytest.mark.parametrize(
    "name", ["id", "type", "urls", "meta", "create_new", "db_labels", "edge_properties"]
)
@no_type_check
def test_names_that_the_generated_models_use_are_reserved(name):
    type("Thing", (Entity,), {"__annotations__": {name: str}})

    with pytest.raises(PanglossModelError):
        initialise()


@no_type_check
def test_initialising_twice_does_not_double_the_incoming_relations():
    class Person(Entity):
        pass

    class Statement(Document):
        by: Person

    initialise()
    before = len(Person._meta.field_definitions.incoming_fields["by_reverse"])
    initialise()
    assert len(Person._meta.field_definitions.incoming_fields["by_reverse"]) == before


@no_type_check
def test_the_cache_of_bound_models_is_cleared_with_the_registry():
    class Action(Document):
        year: int

    class Factoid(Document):
        year: int
        actions: Annotated[
            list[Action],
            RelationConfig(
                bind_to_child_field=[FieldBinding(bound_field="year", child_fields=["year"])]
            ),
        ]

    initialise()
    assert builder._bound_models

    ModelRegistry._reset()
    assert not builder._bound_models
    assert not builder._generic_models


@pytest.mark.parametrize(
    "module",
    [
        initialise_create_model,
        initialise_create_db_model,
        initialise_update_model,
        initialise_update_db_model,
        initialise_view_model,
    ],
)
def test_the_name_of_a_generic_model_does_not_depend_on_the_order_of_a_set(module):
    from frozendict import frozendict
    from pangloss_models.field_definitions import ParameterTypeOptions, RelationToEntity

    class Person(Entity):
        pass

    class Group(Entity):
        pass

    def options(order):
        return frozendict(
            T=ParameterTypeOptions(
                annotated_type=Person,
                type_var=None,
                type_var_name="T",
                type_options=[RelationToEntity(annotated_type=c, edge_model=None) for c in order],
            )
        )

    assert module.recursively_get_generic_naming(options([Person, Group])) == (
        module.recursively_get_generic_naming(options([Group, Person]))
    )


def test_models_can_be_made_without_the_database_functions(monkeypatch):
    from pangloss_models.model_registry import ModelRegistry

    def fail():
        raise AssertionError("the database functions should not be bound")

    monkeypatch.setattr(ModelRegistry, "_bind_database_functions", fail)

    class Thing(Entity):
        name: str

    initialise(bind_database=False)

    assert "name" in Thing.Create.model_fields
