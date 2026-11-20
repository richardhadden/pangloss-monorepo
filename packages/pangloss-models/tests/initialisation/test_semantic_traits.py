"""`SemanticTrait` and `SemanticNonHeritableTrait`: traits that mean something as a class (`Agent`, "a person or a
group"). They are stored and labelled exactly as `Trait` and `NonHeritableTrait`; the model layer can tell them apart
and the export lists them in `semanticTraits`"""

import importlib
import sys
from typing import no_type_check

import pytest
from pangloss_models import (
    Entity,
    ModelRegistry,
    NonHeritableTrait,
    SemanticNonHeritableTrait,
    SemanticTrait,
    Trait,
    initialise,
)
from pangloss_models.export import export_models
from pangloss_models.model_bases.labels import labels_for_model
from pangloss_models.utils import model_is_semantic_trait, model_is_trait


@no_type_check
def declare(trait_base, non_heritable_base):
    """A trait and a non-heritable trait of the given bases, a class of each, and a class below that"""

    class Agent(trait_base):
        pass

    class Named(non_heritable_base):
        pass

    class Person(Entity, Agent, Named):
        pass

    class Child(Person):
        pass

    class Group(Entity, Agent):
        pass

    initialise()
    return {"Person": Person, "Child": Child, "Group": Group}


def stored_labels(models) -> dict[str, list[str]]:
    """The labels of each class's nodes: those of the model, and those of what is written of one"""
    found = {}
    for name, model in models.items():
        written = model.CreateDB(label=f"A {name}")._labels
        assert written == labels_for_model(model, "Entity")
        found[name] = written
    return found


@no_type_check
def test_a_class_with_a_semantic_trait_has_the_labels_it_has_with_a_plain_trait():
    plain = stored_labels(declare(Trait, NonHeritableTrait))
    ModelRegistry._reset()
    semantic = stored_labels(declare(SemanticTrait, SemanticNonHeritableTrait))

    assert semantic == plain
    assert semantic["Person"] == ["Person", "Agent", "Named", "Entity"]
    # (no label of the base's own name)
    assert not any(
        "Semantic" in label for labels in semantic.values() for label in labels
    )


@no_type_check
def test_a_semantic_non_heritable_trait_labels_only_the_class_that_names_it():
    models = declare(SemanticTrait, SemanticNonHeritableTrait)

    assert "Named" in labels_for_model(models["Person"], "Entity")
    assert labels_for_model(models["Child"], "Entity") == [
        "Child",
        "Person",
        "Agent",
        "Entity",
    ]


@no_type_check
def test_the_bases_are_not_models():
    declare(SemanticTrait, SemanticNonHeritableTrait)

    names = {model.__name__ for model in ModelRegistry._models}
    assert {"Agent", "Named", "Person"} <= names
    assert not names & {"SemanticTrait", "SemanticNonHeritableTrait"}
    assert set(export_models()["models"]) == {"Person", "Child", "Group"}


@no_type_check
def test_a_trait_below_a_semantic_trait_is_semantic():
    class Agent(SemanticTrait):
        pass

    class Organisation(Agent):
        pass

    class Plain(Trait):
        pass

    class Below(Plain):
        pass

    class Company(Entity, Organisation, Below):
        pass

    initialise()

    assert model_is_semantic_trait(Organisation)
    assert not model_is_semantic_trait(Below)
    exported = export_models()["models"]["Company"]
    assert exported["traits"] == ["Agent", "Below", "Organisation", "Plain"]
    assert exported["semanticTraits"] == ["Agent", "Organisation"]
    assert labels_for_model(Company, "Entity") == [
        "Company",
        "Organisation",
        "Agent",
        "Below",
        "Plain",
        "Entity",
    ]


@no_type_check
def test_the_export_lists_semantic_traits_beside_the_traits():
    class Agent(SemanticTrait):
        pass

    class Named(SemanticNonHeritableTrait):
        pass

    class Dated(Trait):
        pass

    class Person(Entity, Agent, Named, Dated):
        pass

    class Child(Person):
        pass

    class Place(Entity):
        pass

    initialise()

    models = export_models()["models"]
    assert models["Person"]["traits"] == ["Agent", "Dated", "Named"]
    # (a plain trait is in `traits` and not in `semanticTraits`)
    assert models["Person"]["semanticTraits"] == ["Agent", "Named"]
    # (the semantic ones of the traits listed, whatever the list is: a class below lists a non-heritable trait above
    # it, as `traits` always has, though its nodes do not have the label)
    for name in ("Person", "Child", "Place"):
        assert set(models[name]["semanticTraits"]) <= set(models[name]["traits"])
    assert models["Child"]["traits"] == ["Agent", "Dated", "Named"]
    assert models["Child"]["semanticTraits"] == ["Agent", "Named"]
    assert models["Place"]["traits"] == [] and models["Place"]["semanticTraits"] == []


@no_type_check
def test_each_kind_of_trait_is_a_trait_and_only_the_semantic_ones_are_semantic():
    class Plain(Trait):
        pass

    class PlainNotInherited(NonHeritableTrait):
        pass

    class Meaning(SemanticTrait):
        pass

    class MeaningNotInherited(SemanticNonHeritableTrait):
        pass

    class Person(Entity, Plain, PlainNotInherited, Meaning, MeaningNotInherited):
        pass

    initialise()

    for trait in (Plain, PlainNotInherited, Meaning, MeaningNotInherited):
        assert model_is_trait(trait), trait
    assert not model_is_semantic_trait(Plain)
    assert not model_is_semantic_trait(PlainNotInherited)
    assert model_is_semantic_trait(Meaning)
    assert model_is_semantic_trait(MeaningNotInherited)
    # (a class a trait is applied to is neither)
    assert not model_is_trait(Person)
    assert not model_is_semantic_trait(Person)


def test_the_stubs_of_a_model_with_a_semantic_trait_compile(tmp_path, monkeypatch):
    from pangloss_models.typestubs import stub_for_module

    (tmp_path / "agentsapp.py").write_text(
        "from pangloss_models import Entity, SemanticNonHeritableTrait, SemanticTrait\n\n\n"
        "class Agent(SemanticTrait):\n    name: str\n\n\n"
        "class Named(SemanticNonHeritableTrait):\n    pass\n\n\n"
        "class Person(Entity, Agent, Named):\n    pass\n\n\n"
        "class Group(Entity, Agent):\n    pass\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("agentsapp", None)
    module = importlib.import_module("agentsapp")
    try:
        initialise()

        for mode in (None, "async", "sync"):
            stub = stub_for_module(
                module,
                [module.Agent, module.Named, module.Person, module.Group],
                None,
                mode,
            )
            compile(stub, "agentsapp.pyi", "exec")
            assert "class Agent(SemanticTrait):" in stub
            assert "class Person(" in stub
    finally:
        sys.modules.pop("agentsapp", None)


@pytest.mark.parametrize("base", [SemanticTrait, SemanticNonHeritableTrait])
def test_the_bases_are_named_in_the_editor_schema(base):
    from pangloss_models.editor_schema import editor_schema

    schema = editor_schema()
    assert schema["aliases"][f"{base.__name__}.Meta"] == "TraitMeta"
