"""What the models know of merging two entities, with no database (`pangloss_models.merging`): which class the
survivor takes, the fields it has if no one chooses, and the relations a merge leaves where they are"""

import asyncio
from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Document,
    Entity,
    FieldMarker,
    FieldSubclassing,
    KeepOnMerge,
    MergeRules,
    PanglossMergeError,
    PanglossModelError,
    PanglossServerOnly,
    RelationConfig,
    export_models,
    initialise,
)
from pangloss_models.markers import keeps_on_merge
from pangloss_models.merging import (
    kept_fields,
    merged_values,
    note_resolved,
    noting_resolved,
    survivor_class,
    survivor_classes,
    without_references_to,
)


def people():
    class Person(Entity):
        _meta = Entity.Meta(merge=MergeRules(label_into="aliases"))
        aliases: list[str] = []
        born: int | None = None
        nickname: str | None = None
        knows: list[Person]
        parent: Person | None = None

    class Poet(Person):
        works: list[str] = []

    class Soldier(Person):
        rank: str | None = None

    class PoetSoldier(Poet, Soldier):
        pass

    class Laureate(PoetSoldier):
        pass

    class Group(Entity):
        pass

    class Shape(Entity):
        _meta = Entity.Meta(abstract=True)

    class Square(Shape):
        pass

    class Circle(Shape):
        pass

    initialise()
    return Person, Poet, Soldier, PoetSoldier, Laureate, Group, Square, Circle


# --- the class of the survivor ------------------------------------------------------------------------------------------


@no_type_check
def test_the_survivor_of_two_of_a_class_is_of_that_class():
    Person, Poet, *_ = people()
    assert survivor_classes(Person, Person) == [Person]
    assert survivor_class(Poet, Poet) is Poet


@no_type_check
def test_the_survivor_takes_the_narrower_class_whichever_way_round_and_the_wider_if_chosen():
    Person, Poet, *_ = people()
    assert survivor_classes(Person, Poet) == [Poet, Person]
    assert survivor_classes(Poet, Person) == [Poet, Person]
    assert survivor_class(Person, Poet) is Poet
    assert survivor_class(Poet, Person) is Poet
    assert survivor_class(Person, Poet, Person) is Person
    with pytest.raises(PanglossMergeError, match="cannot be a Soldier"):
        survivor_class(Person, Poet, _[0])


@no_type_check
def test_siblings_become_the_least_particular_class_that_is_both():
    Person, Poet, Soldier, PoetSoldier, Laureate, *_ = people()
    # (a `Laureate` is both too, but says more than the merge knows)
    assert survivor_classes(Poet, Soldier) == [PoetSoldier, Laureate]
    assert survivor_class(Poet, Soldier) is PoetSoldier
    assert survivor_class(Soldier, Poet, Laureate) is Laureate
    with pytest.raises(PanglossMergeError, match="cannot be a Person"):
        survivor_class(Poet, Soldier, Person)


@no_type_check
def test_classes_with_no_class_that_is_both_cannot_be_merged():
    Person, Poet, Soldier, PoetSoldier, Laureate, Group, Square, Circle = people()
    assert survivor_classes(Person, Group) == []
    with pytest.raises(PanglossMergeError, match="neither is a kind of the other"):
        survivor_class(Person, Group)
    # (siblings under a parent, with no class that is both)
    with pytest.raises(
        PanglossMergeError, match="Change the class of one of them first"
    ):
        survivor_class(Square, Circle)


@no_type_check
def test_when_several_classes_are_both_the_choice_has_to_be_made():
    class Person(Entity):
        pass

    class Poet(Person):
        pass

    class Soldier(Person):
        pass

    class WarPoet(Poet, Soldier):
        pass

    class SingingSoldier(Soldier, Poet):
        pass

    initialise()
    assert survivor_classes(Poet, Soldier) == [SingingSoldier, WarPoet]
    with pytest.raises(
        PanglossMergeError, match="SingingSoldier or WarPoet: say which"
    ):
        survivor_class(Poet, Soldier)
    assert survivor_class(Poet, Soldier, WarPoet) is WarPoet


# --- the fields of the survivor -----------------------------------------------------------------------------------------

A, B, C = (f"00000000-0000-7000-8000-00000000000{n}" for n in "123")


def reference(id, label="x"):
    return {"type": "Person", "id": id, "label": label}


@no_type_check
def test_single_values_are_the_survivors_or_else_the_absorbed_entitys():
    Person, *_ = people()
    values = merged_values(
        Person,
        {
            "id": A,
            "label": "John",
            "born": 1800,
            "nickname": "",
            "aliases": [],
            "knows": [],
            "parent": None,
        },
        {
            "id": B,
            "label": "Jon",
            "born": 1801,
            "nickname": "Jack",
            "aliases": [],
            "knows": [],
            "parent": reference(C),
        },
    )
    assert (values["id"], values["type"], values["label"]) == (A, "Person", "John")
    assert (values["born"], values["nickname"]) == (1800, "Jack")
    assert values["parent"]["id"] == C
    # (a value of 0 or False is a value: only nothing, "" and [] give way)
    assert (
        merged_values(
            Person,
            {"id": A, "label": "John", "born": 0, "aliases": [], "knows": []},
            {"id": B, "label": "Jon", "born": 1801, "aliases": [], "knows": []},
        )["born"]
        == 0
    )


@no_type_check
def test_lists_are_both_without_repeats_and_the_absorbed_label_goes_where_the_class_says():
    Person, *_ = people()
    values = merged_values(
        Person,
        {
            "id": A,
            "label": "John",
            "aliases": ["Johnny", "J."],
            "knows": [reference(C, "Kate")],
            "urls": ["https://e.org/a"],
        },
        {
            "id": B,
            "label": "Jon",
            "aliases": ["J.", "Jonny"],
            # (the same entity, read at another time with another label, is the same reference)
            "knows": [
                reference(C, "Kate Smith"),
                reference("00000000-0000-7000-8000-000000000009"),
            ],
            "urls": ["https://e.org/b", "https://e.org/a"],
        },
    )
    assert values["aliases"] == ["Johnny", "J.", "Jonny", "Jon"]
    assert [k["id"] for k in values["knows"]] == [
        C,
        "00000000-0000-7000-8000-000000000009",
    ]
    assert values["knows"][0]["label"] == "Kate"
    assert values["urls"] == ["https://e.org/a", "https://e.org/b"]


@no_type_check
def test_the_absorbed_label_is_not_added_twice_nor_when_it_is_the_survivors():
    Person, *_ = people()
    same = merged_values(
        Person,
        {"id": A, "label": "John", "aliases": [], "knows": []},
        {"id": B, "label": "John", "aliases": [], "knows": []},
    )
    assert same["aliases"] == []
    there = merged_values(
        Person,
        {"id": A, "label": "John", "aliases": ["Jon"], "knows": []},
        {"id": B, "label": "Jon", "aliases": [], "knows": []},
    )
    assert there["aliases"] == ["Jon"]


@no_type_check
def test_the_survivor_refers_neither_to_itself_nor_to_what_it_absorbed():
    Person, *_ = people()
    values = merged_values(
        Person,
        {
            "id": A,
            "label": "John",
            "aliases": [],
            "knows": [reference(B), reference(C)],
            "parent": reference(B),
        },
        {
            "id": B,
            "label": "Jon",
            "aliases": [],
            "knows": [reference(A)],
            "parent": reference(A),
        },
    )
    assert [k["id"] for k in values["knows"]] == [C]
    assert values["parent"] is None
    assert without_references_to([reference(A), reference(C)], {A}) == [reference(C)]
    assert without_references_to(reference(C), {A}) == reference(C)
    assert without_references_to(None, {A}) is None


@no_type_check
def test_the_fields_of_the_survivor_are_those_of_the_class_it_takes():
    Person, Poet, *_ = people()
    person = {"id": A, "label": "John", "aliases": [], "knows": [], "born": 1800}
    poet = {"id": B, "label": "Jon", "aliases": [], "knows": [], "works": ["Odes"]}
    narrower = merged_values(Poet, person, poet)
    assert (narrower["type"], narrower["works"], narrower["born"]) == (
        "Poet",
        ["Odes"],
        1800,
    )
    wider = merged_values(Person, person, poet)
    assert wider["type"] == "Person" and "works" not in wider
    # and what it gives is what an update of the class takes
    assert Poet.Update(**narrower).works == ["Odes"]
    assert Person.Update(**wider).aliases == ["Jon"]


@no_type_check
def test_a_rule_that_names_no_list_field_is_an_error():
    class Person(Entity):
        _meta = Entity.Meta(merge=MergeRules(label_into="nickname"))
        nickname: str | None = None

    class Place(Entity):
        _meta = Entity.Meta(merge=MergeRules(label_into="names"))

    initialise()
    for model in (Person, Place):
        with pytest.raises(PanglossMergeError, match="does not name a list field"):
            merged_values(model, {"id": A, "label": "a"}, {"id": B, "label": "b"})


@no_type_check
def test_the_rule_of_a_class_is_its_subclasses_too():
    Person, Poet, *_ = people()
    assert Poet._meta.merge == MergeRules(label_into="aliases")
    assert Entity._meta.merge is None


# --- relations a merge leaves where they are ---------------------------------------------------------------------------


@no_type_check
def test_keep_on_merge_is_a_marker_of_a_relation_and_subclasses_of_it_count():
    class Claim(KeepOnMerge):
        pass

    class Person(Entity):
        pass

    class Statement(Document):
        concerns: list[Person]
        names: Annotated[list[Person], KeepOnMerge()]

    class SameAs(Statement):
        entities: Annotated[
            list[Person],
            Claim(),
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing(field_name="concerns", field_on_model=Statement)
                ]
            ),
        ]

    initialise()
    assert isinstance(KeepOnMerge(), FieldMarker)
    fields = Statement._meta.fields.relation_fields
    assert keeps_on_merge(fields["names"]) and not keeps_on_merge(fields["concerns"])
    assert kept_fields(Statement) == {"names"}
    # (a kept field is stored under the names of the fields it narrows as well: those edges stay with it)
    assert kept_fields(SameAs) == {"names", "entities", "concerns"}
    # the export says it of the relations that have it (by what it means, for a subclass of any name), for the
    # interface; it is not data, so the snapshot a migration is made from leaves it out
    exported = export_models()["models"]

    def markers(model: str, field: str):
        return next(f for f in exported[model]["fields"] if f["name"] == field).get(
            "markers"
        )

    assert markers("Statement", "names") == [
        {"name": "KeepOnMerge", "keepOnMerge": True}
    ]
    assert markers("SameAs", "entities") == [{"name": "Claim", "keepOnMerge": True}]
    assert markers("Statement", "concerns") is None
    from pangloss_models.migrations.snapshot import NOT_DATA_KEYS

    assert "markers" in NOT_DATA_KEYS


@no_type_check
def test_keep_on_merge_on_a_value_is_refused_when_the_models_are_exported():
    class Person(Entity):
        name: Annotated[str, KeepOnMerge()]

    initialise()
    with pytest.raises(PanglossModelError, match="KeepOnMerge.. is for a relation"):
        export_models()


# --- what a write resolved, and a storage that cannot merge ---------------------------------------------------------------


def test_resolved_references_are_noted_only_while_someone_listens():
    note_resolved("b", "a")
    with noting_resolved() as noted:
        note_resolved("b", "a")
        note_resolved("b", "a")
        note_resolved("x", "a")
        with noting_resolved() as inner:
            note_resolved("y", "a")
    note_resolved("z", "a")
    assert noted == [("b", "a"), ("x", "a")]
    assert inner == [("y", "a")]


@no_type_check
def test_a_storage_that_cannot_merge_says_so():
    """(what `Entity.merge` and the rest are bound to on a storage that has no such operation)"""
    from pangloss_models.merging import not_on_this_storage

    Person, *_ = people()
    for name in ("merge", "unmerge", "merge_preview", "merges", "propose_merge"):
        refuse = not_on_this_storage(name, "a storage without it")
        with pytest.raises(PanglossServerOnly, match="cannot merge entities"):
            asyncio.run(refuse(Person, absorb=A, into=B))
