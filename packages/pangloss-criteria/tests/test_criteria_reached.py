"""Which classes the criteria of some description could reach (`holders.reached`): a write of a head of one of them
leaves work for the worker, though it holds no description (implementation_docs/matches-criteria.md, "1. Marking")."""

import importlib

import pangloss_criteria.models
from pangloss_criteria import holders
from pangloss_models import (
    Conjunction,
    Document,
    Embedded,
    Entity,
    ModelRegistry,
    ReifiedRelation,
    initialise,
)


def criteria_class():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    return pangloss_criteria.models.MatchesCriteria


def models():
    MatchesCriteria = criteria_class()

    class Human(Entity):
        """A parent of the class described"""

        _meta = Entity.Meta(abstract=True)

    class Country(Entity):
        pass

    class Place(Entity):
        in_country: Country | None = None

    class Person(Human):
        born_in: Place | None = None

    class Monk(Person):
        """Below the class described"""

    class Role(Entity):
        pass

    class Unit(Entity):
        pass

    class Treaty(Document):
        """Three steps away: a treaty of a country a place is in, where a person was born"""

        between: list[Country]

    class HoldsOffice(Document):
        """Refers to a person: what `$incoming` reaches"""

        holder: Person

    class InRole[T](ReifiedRelation[T]):
        role: Role | None = None

    class Sealed(Document):
        """Refers to a person through a wrapper, which refers to a role of its own"""

        by: list[InRole[Person]]

    class Both[A, B](Conjunction):
        one: A
        other: B

    class Pair(Document):
        """Through a conjunction"""

        of: Both[Person, Unit]

    class Measure(Embedded):
        taken_by: Person

    class Survey(Document):
        """Through an embedded object"""

        measure: Measure

    class Statement(Document):
        _meta = Document.Meta(create_directly=False)
        about: Person

    class Factoid(Document):
        """Holds a document nested in it that refers to a person"""

        statements: list[Statement]

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]

    class Ship(Entity):
        pass

    class Logbook(Document):
        """Joined to nothing a description is of"""

        ships: list[Ship]

    initialise()
    return {
        name: cls
        for name, cls in locals().items()
        if isinstance(cls, type) and name != "MatchesCriteria"
    }


def names(classes) -> list[str]:
    return sorted(cls.__name__ for cls in classes)


def test_what_the_criteria_of_a_description_can_reach_is_marked():
    m = models()

    reached = holders.reached()

    assert names(reached) == sorted(
        [
            # (the class described, the one it is declared below, and one below it)
            "Person",
            "Human",
            "Monk",
            # (a relation of its own, and of that: any number of steps)
            "Place",
            "Country",
            "Treaty",
            # (what refers to it: directly, through a wrapper and what the wrapper refers to, through a
            # conjunction and what else that holds, through an embedded object)
            "HoldsOffice",
            "Sealed",
            "Role",
            "Pair",
            "Unit",
            "Survey",
            # (a nested document, and the head that holds it)
            "Statement",
            "Factoid",
            # (what holds the description)
            "Activity",
        ]
    )
    for name in ("HoldsOffice", "Place", "Factoid", "Statement", "Monk", "Treaty"):
        assert holders.pending_work_of(m[name]) == ["criteria"], name
    # (it holds none: it is marked because criteria could reach it)
    assert holders.can_hold(m["HoldsOffice"]) is False


def test_a_class_joined_to_nothing_described_is_not_reached_and_leaves_no_work():
    m = models()

    assert m["Ship"] not in holders.reached()
    assert m["Logbook"] not in holders.reached()
    assert holders.pending_work_of(m["Ship"]) == []
    assert holders.pending_work_of(m["Logbook"]) == []


def test_a_description_of_one_class_reaches_from_that_class_only():
    MatchesCriteria = criteria_class()

    class Person(Entity):
        pass

    class Ship(Entity):
        pass

    class Voyage(Document):
        ships: list[Ship]
        by: list[Person]

    class Logbook(Document):
        """Refers to a ship only"""

        ships: list[Ship]

    class Harbour(Entity):
        pass

    class Mooring(Document):
        harbour: Harbour

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]

    initialise()

    # (a voyage joins ships to people, and a logbook to ships; nothing joins harbours to them)
    assert names(holders.reached()) == [
        "Activity",
        "Logbook",
        "Person",
        "Ship",
        "Voyage",
    ]
    assert holders.pending_work_of(Mooring) == []
    assert holders.pending_work_of(Harbour) == []


def test_with_no_description_in_the_models_nothing_is_reached():
    class Person(Entity):
        pass

    class HoldsOffice(Document):
        holder: Person

    initialise()

    assert holders.reached() == set()
    assert holders.pending_work_of(HoldsOffice) == []
    assert holders.pending_work_of(Person) == []


def test_with_the_class_declared_and_no_use_of_it_nothing_is_reached():
    criteria_class()

    class Person(Entity):
        pass

    class HoldsOffice(Document):
        holder: Person

    initialise()

    assert holders.description_labels() == ["MatchesCriteria"]
    assert holders.reached() == set()
    assert holders.pending_work_of(HoldsOffice) == []


def test_what_is_reached_is_forgotten_with_the_models():
    m = models()
    assert m["HoldsOffice"] in holders.reached()

    ModelRegistry._reset()

    assert holders._reached is None

    class Person(Entity):
        pass

    class HoldsOffice(Document):
        holder: Person

    initialise()
    assert holders.reached() == set()
