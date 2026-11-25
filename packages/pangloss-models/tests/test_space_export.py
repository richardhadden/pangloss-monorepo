"""What a semantic space says of its contents, in the export (`export.export_space`): `veridical` and `unary` as
they hold (set, or what `logical` implies), `fit`, `logical` as the interface reads it, and `degree`. Only a space
has the keys"""

from typing import Any, no_type_check

from pangloss_models import (
    Document,
    Entity,
    Modal,
    SemanticSpace,
    export_models,
    initialise,
)
from pangloss_models.export import Exporter

KEYS = ("veridical", "fit", "logical", "unary", "degree")


def said(model: dict) -> dict:
    return {key: model[key] for key in KEYS}


@no_type_check
def declare() -> dict[str, Any]:
    class Person(Entity):
        pass

    class Reported[T](SemanticSpace[T]):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command"),
            fit="prescribes",
            degree="likely",
        )

    class Forbidden[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command", of_not=True), fit="prescribes"
        )

    class Possibly[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))

    class Asserted[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1, unary=True)

    # (inherits every value)
    class Commanded[T](Ordered[T]):
        pass

    # (sets one, inherits the rest)
    class Requested[T](Ordered[T]):
        _meta = SemanticSpace.Meta(degree="possible")

    # (of one type of contents, not generic)
    class NotPerson(Not[Person]):
        pass

    class Statement(Document):
        reported: Reported[Person]
        denied: Not[Person]
        ordered: Ordered[Person]
        forbidden: Forbidden[Person]
        possibly: Possibly[Person]
        asserted: Asserted[Person]
        commanded: Commanded[Person]
        requested: Requested[Person]
        denied_person: NotPerson

    initialise(bind_database=False)
    return {"Not": Not, "Ordered": Ordered, "Person": Person}


def test_a_space_that_says_nothing_is_uncommitted_and_describes():
    declare()
    assert said(export_models()["models"]["Reported"]) == {
        "veridical": 0,
        "fit": "describes",
        "logical": None,
        "unary": False,
        "degree": None,
    }


def test_a_not_denies_one_item_as_it_holds_though_the_class_sets_neither():
    declare()
    assert said(export_models()["models"]["Not"]) == {
        "veridical": -1,
        "fit": "describes",
        "logical": {"not": True},
        "unary": True,
        "degree": None,
    }


def test_a_modal_is_its_force_and_flavour_with_and_without_of_not():
    declare()
    models = export_models()["models"]
    assert said(models["Ordered"]) == {
        "veridical": 0,
        "fit": "prescribes",
        "logical": {"force": "necessity", "flavour": "command", "ofNot": False},
        "unary": False,
        "degree": "likely",
    }
    assert said(models["Forbidden"]) == {
        "veridical": 0,
        "fit": "prescribes",
        "logical": {"force": "necessity", "flavour": "command", "ofNot": True},
        "unary": True,
        "degree": None,
    }
    assert said(models["Possibly"])["logical"] == {
        "force": "possibility",
        "flavour": "epistemic",
        "ofNot": False,
    }


def test_what_the_class_sets_is_what_it_says():
    declare()
    assert said(export_models()["models"]["Asserted"]) == {
        "veridical": 1,
        "fit": "describes",
        "logical": None,
        "unary": True,
        "degree": None,
    }


def test_a_subclass_inherits_and_one_that_sets_a_value_says_it():
    declare()
    models = export_models()["models"]
    assert said(models["Commanded"]) == said(models["Ordered"])
    assert said(models["Requested"]) == said(models["Ordered"]) | {"degree": "possible"}
    # (a concrete subclass, as its generic class)
    assert said(models["NotPerson"]) == said(models["Not"])


def test_a_parametrisation_says_what_its_class_says():
    """`Not[Person]` is not in the export (the field says what a space is used with), but what is exported of it is
    its class's"""
    classes = declare()
    exporter = Exporter()
    for name in ("Not", "Ordered"):
        generic = classes[name]
        parametrised = generic[classes["Person"]]
        assert said(exporter.export_model(parametrised)) == said(
            exporter.export_model(generic)
        )


def test_no_other_kind_of_model_has_the_keys():
    declare()
    models = export_models()["models"]
    for name in ("Person", "Statement"):
        assert not set(KEYS) & set(models[name]), name
    assert all(
        set(KEYS) <= set(m) for m in models.values() if m["kind"] == "SemanticSpace"
    )
