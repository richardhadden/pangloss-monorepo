"""Classes an item is only by use (step 7a.5 of implementation_docs/similarity-build-plan.md): which classes have the
rule and of which classes, which relations count (`by_use.rules`), and which classes of a search are given only by use
(`by_use.given_by_use`). No database; the typology is `pangloss_typology`'s, which makes the class with unmanaged
labels."""

import logging
from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    Embedded,
    Entity,
    ReifiedRelation,
    Trait,
    initialise,
)
from pangloss_vectors import by_use

typology = pytest.importorskip("pangloss_typology")


@pytest.fixture(autouse=True)
def no_typologies():
    typology.Typology.registry.clear()
    yield
    typology.Typology.registry.clear()


@no_type_check
def declare():
    """`Role` (below `Function`, with the trait `Duty`) and its typology `RoleType`, which is also a `Role`; a typology
    that is always one (`OfficeType`, of `Office`); people who hold roles directly, through a wrapper, in an embedded
    tenure and through a wrapper in a wrapper; a note that has a type of role as its type"""
    Typed, Typology, TypologyMeta = (
        typology.Typed,
        typology.Typology,
        typology.TypologyMeta,
    )

    class Duty(Trait):
        pass

    class Function(Entity):
        pass

    class Role(Function, Duty):
        has_type: list[Typed[RoleTypology]]

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType", also=Role)

    class Office(Entity):
        pass

    class OfficeTypology(Typology):
        _typology_meta = TypologyMeta(name="OfficeType", also=Office, concrete="always")

    class Person(Entity):
        has_role: list[Role]

    class InRole[T](ReifiedRelation[T]):
        pass

    class Maybe[T](ReifiedRelation[T]):
        pass

    class Tenure(Embedded):
        role: Role

    class Appointment(Document):
        held: list[InRole[Role]]
        who: list[InRole[Person]]
        tenure: Tenure | None
        guessed: list[Maybe[InRole[Role]]]

    class Charge(Document):
        functions: list[Function]
        duties: list[Duty]

    class Note(Document):
        has_type: list[Typed[RoleTypology]]

    initialise(bind_database=False)
    return RoleTypology.Type


def test_a_type_that_is_switched_on_is_a_role_by_use_and_a_role_type_by_class():
    RoleType = declare()
    assert by_use.by_use_classes(RoleType) == {"Role", "Function", "Duty"}
    assert by_use.by_class(RoleType) == {"RoleType"}
    assert set(by_use.rules()) == {"RoleType"}
    assert by_use.rules()["RoleType"].classes == {"Role", "Function", "Duty"}


def test_a_class_without_unmanaged_labels_has_no_rule():
    declare()
    rules = by_use.rules()
    # (a typology that is always the other class, the other class itself, anything else)
    for name in ("OfficeType", "Office", "Role", "Person"):
        assert name not in rules


def test_the_relations_that_count_are_those_to_the_other_class_or_one_above_it_directly_through_wrappers_and_embedded():
    declare()
    uses = by_use.rules()["RoleType"].uses
    # (a plain relation to the other class, also as inherited by the type itself: `RoleType` is a `Role`... and has
    # none of its own to `Role`)
    assert ("Person", "has_role") in uses
    # (a relation to a class above it, and to a trait of it)
    assert ("Charge", "functions") in uses
    assert ("Charge", "duties") in uses
    # (through a wrapper: the edge onto the entity is the wrapper's, from its node stored as the wrapper's class)
    assert ("InRole", "target") in uses
    assert ("Appointment", "held") not in uses
    # (an embedded object's node)
    assert ("Tenure", "role") in uses
    # (having the type, and the hierarchy, are relations to a `RoleType`: they do not count)
    for pair in (
        ("Role", "has_type"),
        ("RoleType", "has_type"),
        ("Note", "has_type"),
        ("RoleType", "is_subtype_of"),
    ):
        assert pair not in uses
    # (a wrapper in a wrapper: the outer one's edge is onto the inner one, not onto an entity)
    assert ("Maybe", "target") not in uses
    assert by_use.rules()["RoleType"].ambiguous == frozenset()


@pytest.mark.parametrize(
    ("asked", "given"),
    [
        (["Role"], ["RoleType"]),
        (["Function"], ["RoleType"]),
        (["Duty"], ["RoleType"]),
        (["RoleType"], []),
        (["Role", "RoleType"], []),
        (["Person.has_role"], ["RoleType"]),
        (["Appointment.held"], ["RoleType"]),
        (["Note.has_type"], []),
        (["Person.has_role", "RoleType"], []),
    ],
)
def test_a_type_is_given_only_by_use_unless_a_name_asks_it_as_itself(asked, given):
    declare()
    assert by_use.given_by_use(["Role", "RoleType"], asked) == given


def test_a_search_that_does_not_search_the_type_has_nothing_given_by_use():
    declare()
    assert by_use.given_by_use(["Role", "Person"], ["Role", "Person"]) == []


def test_the_query_is_given_the_pairs_of_each_class_given_by_use():
    declare()
    found = by_use.parameters(["RoleType"])
    assert found["by_use_types"] == ["RoleType"]
    assert {"type": "RoleType", "source": "InRole", "edge": "target"} in found["by_use"]
    assert {(u["source"], u["edge"]) for u in found["by_use"]} == set(
        by_use.rules()["RoleType"].uses
    )


@no_type_check
def test_one_wrapper_used_for_the_class_and_for_the_other_gives_a_pair_that_counts_and_says_so(
    caplog,
):
    """(not a typology's: a relation to its type must be called `has_type`, so it is in no wrapper. A class of the
    project's own that leaves a label to the data)"""

    class Office(Entity):
        pass

    class Seat(Office):
        __labels_unmanaged__ = ("Office",)

    class InRole[T](ReifiedRelation[T]):
        pass

    class Sitting(Document):
        offices: list[InRole[Office]]
        seats: list[InRole[Seat]]

    initialise(bind_database=False)
    with caplog.at_level(logging.WARNING, logger="pangloss_vectors.by_use"):
        rule = by_use.rules()["Seat"]
    assert ("InRole", "target") in rule.uses
    assert rule.ambiguous == {("InRole", "target")}
    assert "InRole.target" in caplog.text


def test_the_rules_are_worked_out_again_after_the_models_are_reset():
    declare()
    assert "RoleType" in by_use.rules()
    from pangloss_models import ModelRegistry

    ModelRegistry._reset()
    typology.Typology.registry.clear()
    initialise(bind_database=False)
    assert by_use.rules() == {}
