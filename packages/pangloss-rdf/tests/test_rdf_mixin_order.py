"""An outside ontology's class is a plain Python parent (implementation_docs/rdf-export-plan.md, §7). It leaves the data alone, and
Python itself refuses a broader class named before a trait that has it"""

import pytest
from pangloss_models import Entity, Trait, initialise
from pangloss_models.migrations.snapshot import build_snapshot, snapshot_hash
from pangloss_models.model_bases.labels import labels_for_model


class E39_Actor:
    pass


class E21_Person(E39_Actor):
    pass


def test_a_broader_class_before_the_trait_that_has_it_raises():
    class Agent(Trait, E39_Actor):
        pass

    with pytest.raises(TypeError, match="consistent method resolution"):

        class Person(Entity, E39_Actor, Agent):  # ty: ignore[inconsistent-mro]
            pass


def test_a_narrower_class_after_the_trait():
    class Agent(Trait, E39_Actor):
        pass

    class Person(Entity, Agent, E21_Person):
        pass

    initialise()
    assert issubclass(Person, E39_Actor)
    assert labels_for_model(Person, "Entity") == ["Person", "Agent", "Entity"]


def test_a_mixin_is_not_data():
    from pangloss_models import ModelRegistry

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        name: str

    initialise()
    without = snapshot_hash(build_snapshot())

    ModelRegistry._reset()

    class Agent(Trait, E39_Actor):  # noqa: F811
        pass

    class Person(Entity, Agent, E21_Person):  # noqa: F811
        name: str

    initialise()
    assert snapshot_hash(build_snapshot()) == without
