"""The member of a union of models is chosen from what is given, once (`initialise_models/tagged_union.py`),
not by trying each in turn: the time to check something nested must not grow with the depth, and the member
chosen is the one that the plain union chose."""

import datetime
import time
from typing import Annotated, no_type_check
from uuid import uuid7

import pytest
from pangloss_models import initialise
from pangloss_models.field_definitions import FieldBinding
from pangloss_models.initialise_models.tagged_union import TaggedUnion
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pydantic import ValidationError


def tagged_unions(field) -> list[TaggedUnion]:
    """The tagged unions that a field has (in the field itself, or in the list round it)"""
    found = [m for m in field.metadata if isinstance(m, TaggedUnion)]
    stack = [field.annotation]
    while stack:
        annotation = stack.pop()
        found += [
            m
            for m in getattr(annotation, "__metadata__", ())
            if isinstance(m, TaggedUnion)
        ]
        stack += list(getattr(annotation, "__args__", ()))
    return found


@no_type_check
def test_a_union_of_models_is_a_tagged_union_in_every_kind():
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Dude(Person):
        pass

    class Statement(Document):
        one: Person
        many: list[Person]

    initialise()

    for kind in ("Create", "CreateDB", "Update", "UpdateDB"):
        model = getattr(Statement, kind)
        for name in ("one", "many"):
            assert tagged_unions(model.model_fields[name]), (kind, name)


@no_type_check
def test_reference_new_and_update_are_told_apart_though_they_have_one_type():
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        one: Person
        many: list[Person]

    initialise()

    existing, fresh = uuid7(), uuid7()
    statement = Statement.Update(
        id=uuid7(),
        label="S",
        one={"type": "Person", "id": fresh, "label": "New", "create_new": True},
        many=[
            {"type": "Person", "id": existing},
            {"type": "Person", "id": existing, "label": "A name for clarity"},
            {"type": "Person", "label": "No id: new"},
        ],
    )
    assert isinstance(statement.one, Person.Create)
    assert isinstance(statement.many[0], Person.ReferenceSet)
    assert isinstance(statement.many[1], Person.ReferenceSet)
    assert isinstance(statement.many[2], Person.Create)

    db = statement._to_db_model()
    assert isinstance(db.one, Person.CreateDB)
    assert isinstance(db.many[0], Person.ReferenceSet)
    assert isinstance(db.many[2], Person.CreateDB)


@no_type_check
def test_an_update_is_told_from_a_create_by_its_id():
    class Note(Document):
        text: str

    class Statement(Document):
        notes: list[Note]

    initialise()

    note_id = uuid7()
    statement = Statement.Update(
        id=uuid7(),
        label="S",
        notes=[
            {"type": "Note", "id": note_id, "label": "Old", "text": "kept"},
            {"type": "Note", "label": "New", "text": "added"},
        ],
    )
    assert isinstance(statement.notes[0], Note.Update)
    assert isinstance(statement.notes[1], Note.Create)
    db = statement._to_db_model()
    assert isinstance(db.notes[0], Note.UpdateDB)
    assert isinstance(db.notes[1], Note.CreateDB)
    assert db.notes[1].id


@no_type_check
def test_models_already_made_are_accepted_in_place_of_dicts():
    class Note(Document):
        text: str

    class Statement(Document):
        notes: list[Note]
        one: Note

    initialise()

    note = Note.Create(label="N", text="t")
    statement = Statement.Create(label="S", notes=[note], one=note)
    assert statement.notes[0] is note or statement.notes[0] == note
    assert isinstance(statement.one, Note.Create)


def test_none_is_accepted_where_a_union_may_be_none():
    """(a field that a parent gives a value to is made `| None`: the tagged union is inside the nullable)"""
    from pydantic import BaseModel, Field

    class A(BaseModel):
        type: str = Field("A")
        a: int

    class B(BaseModel):
        type: str = Field("B")
        b: int

    class Holder(BaseModel):
        one: Annotated[A | B, TaggedUnion([A, B])] | None

    assert Holder(one=None).one is None
    assert isinstance(Holder(one={"b": 1}).one, B)
    assert isinstance(Holder(one={"type": "A", "a": 1}).one, A)
    assert isinstance(Holder(one=B(b=2)).one, B)


@no_type_check
def test_a_subclass_is_chosen_by_its_type():
    class Person(Entity):
        pass

    class Dude(Person):
        pass

    class Lass(Person):
        pass

    class Statement(Document):
        who: Person

    initialise()

    for name, model in (("Person", Person), ("Dude", Dude), ("Lass", Lass)):
        statement = Statement.Create(label="S", who={"type": name, "id": uuid7()})
        assert isinstance(statement.who, model.ReferenceSet)


@no_type_check
def test_a_wrong_input_is_an_error_that_says_what_is_wrong():
    class Note(Document):
        text: str

    class Task(Document):
        done: bool

    class Statement(Document):
        what: Note | Task

    initialise()

    # a type that is not one of them
    with pytest.raises(ValidationError) as error:
        Statement.Create(label="S", what={"type": "Nonsense", "label": "x"})
    assert error.value.errors()

    # the right type, a field missing: the error is that field of that model
    with pytest.raises(ValidationError) as error:
        Statement.Create(label="S", what={"type": "Task", "label": "x"})
    locations = [e["loc"] for e in error.value.errors()]
    assert any("done" in loc for loc in locations), locations
    assert not any("text" in loc for loc in locations), locations

    # something that is not an object
    with pytest.raises(ValidationError):
        Statement.Create(label="S", what="a string")
    with pytest.raises(ValidationError):
        Statement.Create(label="S", what=5)


@no_type_check
def test_an_embedded_object_is_chosen_by_its_type():
    class Exact(Embedded):
        when: datetime.date

    class Vague(Embedded):
        text: str

    class Statement(Document):
        date: Exact | Vague

    initialise()

    assert isinstance(
        Statement.Create(label="S", date={"type": "Vague", "text": "spring"}).date,
        Vague.Create,
    )
    assert isinstance(
        Statement.Create(
            label="S", date={"type": "Exact", "when": datetime.date(800, 1, 1)}
        ).date,
        Exact.Create,
    )
    # (a type that is left out: by the fields that are given)
    assert isinstance(
        Statement.Create(label="S", date={"text": "spring"}).date, Vague.Create
    )


def nesting():
    class Positive[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True)
        note: str
        when: datetime.date

    class Order(Statement):
        thing_ordered: Positive[Statement]

    class Gift(Statement):
        pass

    class Factoid(Document):
        when: datetime.date
        statements: Annotated[
            list[Statement | Positive[Statement]],
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(bound_field="when", child_fields=["when"])
                ]
            ),
        ]

    return Factoid


def deeply(depth: int) -> dict:
    inner = {"type": "Gift", "label": "gift", "note": "n"}
    for n in range(depth):
        inner = {
            "type": "Order",
            "label": f"order {n}",
            "note": "n",
            "thing_ordered": {"type": "Positive", "contents": [inner]},
        }
    return inner


@no_type_check
def test_the_time_to_check_does_not_grow_with_the_depth_of_the_nesting():
    Factoid = nesting()
    initialise()

    def check(depth: int) -> float:
        started = time.perf_counter()
        Factoid.Create(
            label="F", when=datetime.date(800, 1, 1), statements=[deeply(depth)]
        )
        return time.perf_counter() - started

    check(3)  # (the first check builds validators that are made when first used)
    shallow, deep = check(5), check(60)
    # (with a plain union the time doubled with each level: 60 levels would not end)
    assert deep < 5 + 20 * shallow, (shallow, deep)


@no_type_check
def test_a_mistake_far_down_is_found_and_said_where_it_is():
    Factoid = nesting()
    initialise()

    bad = deeply(12)
    inner = bad
    for _ in range(12):
        inner = inner["thing_ordered"]["contents"][0]
    inner["note"] = 5  # a note is text

    with pytest.raises(ValidationError) as error:
        Factoid.Create(label="F", when=datetime.date(800, 1, 1), statements=[bad])
    errors = error.value.errors()
    assert len(errors) == 1, errors
    assert errors[0]["loc"][-1] == "note"
    assert errors[0]["loc"].count("contents") == 12
