import json
from enum import Enum
from typing import Annotated

from annotated_types import Ge
from pangloss_models import initialise
from pangloss_models.export import export_models
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace


def by_name(model: dict) -> dict:
    return {f["name"]: f for f in model["fields"]}


def test_models_are_exported_as_plain_data():
    class Colour(Enum):
        RED = "red"
        BLUE = "blue"

    class Place(Entity):
        """A place"""

        name: str | None = None

    class City(Place):
        population: Annotated[int, Ge(0)]

    class Person(Entity):
        born: int | None
        colour: Colour
        nicknames: list[str]
        born_in: Place
        visited: Annotated[list[Place], RelationConfig(reverse_name="visited_by")]

    class Date(Embedded):
        when: str

    class WithCertainty[T](AnnotatedValue[T]):
        certainty: int

    class Negative[Contents](SemanticSpace[Contents]):
        pass

    class WithProxy[Target, Proxy](ReifiedRelation[Target]):
        target: list[Target]
        proxy: list[Proxy]

    class Statement(Document):
        about: Person
        date: Date
        name: WithCertainty[str]
        action: Negative[Person]
        via: WithProxy[Person, Place]

    initialise()
    exported = export_models()
    # (it can be written as JSON)
    assert json.loads(json.dumps(exported)) == exported

    models = exported["models"]
    # The models, not what the library makes of them with parameters
    assert set(models) == {
        "City",
        "Date",
        "Negative",
        "Person",
        "Place",
        "Statement",
        "WithCertainty",
        "WithProxy",
    }

    place = models["Place"]
    assert place["kind"] == "Entity"
    assert place["description"] == "A place"
    assert place["concreteTypes"] == ["City", "Place"]
    assert place["acceptUrlAsId"] is True
    assert models["City"]["parent"] == "Place"
    assert models["Place"]["parent"] is None
    assert models["WithCertainty"]["parent"] is None
    assert models["WithCertainty"]["typeParameters"] == ["T"]

    # literal fields: types, nullability and validators
    person = by_name(models["Person"])
    assert person["born"]["kind"] == "literal"
    assert person["born"]["type"] == {"type": "int"}
    assert person["born"]["nullable"] is True
    assert person["colour"]["type"] == {"type": "enum", "enum": "Colour"}
    assert exported["enums"]["Colour"]["members"] == [
        {"name": "RED", "value": "red"},
        {"name": "BLUE", "value": "blue"},
    ]
    assert person["nicknames"]["kind"] == "list"
    assert person["nicknames"]["item"] == {"type": "str"}
    population = by_name(models["City"])["population"]
    assert population["validators"] == [{"name": "Ge", "ge": 0}]
    assert by_name(models["Place"])["name"]["required"] is False

    # relations: the names in the JSON, the types that can be used, the reverse
    born_in = person["born_in"]
    assert born_in["key"] == "bornIn"
    assert born_in["kind"] == "relation"
    assert born_in["many"] is False
    assert [o["type"] for o in born_in["options"]] == ["City", "Place"]
    assert person["visited"]["many"] is True
    assert person["visited"]["reverseName"] == "visited_by"

    statement = by_name(models["Statement"])
    assert statement["date"] == {
        **statement["date"],
        "kind": "embedded",
        "model": "Date",
        "types": ["Date"],
    }
    assert statement["name"]["kind"] == "annotatedValue"
    assert statement["name"]["model"] == "WithCertainty"
    assert statement["name"]["valueType"] == {"type": "str"}
    (action,) = statement["action"]["options"]
    assert action["kind"] == "semanticSpace"
    assert action["type"] == "Negative"
    assert action["params"]["Contents"]["options"] == [
        {"kind": "entity", "type": "Person", "edgeModel": None}
    ]
    (via,) = statement["via"]["options"]
    assert via["kind"] == "reifiedRelation"
    assert via["params"]["Proxy"]["typeVar"] == "Proxy"
    assert [o["type"] for o in via["params"]["Proxy"]["options"]] == ["City", "Place"]

    # relations to a model, from the others
    incoming = {i["name"]: i for i in models["Person"]["incoming"]}
    assert incoming["about_reverse"]["key"] == "aboutReverse"
    assert incoming["about_reverse"]["sources"] == [
        {"model": "Statement", "field": "about", "viaReified": False}
    ]
    assert incoming["via_reverse"]["sources"][0]["viaReified"] is True


def test_nothing_is_exported_before_there_are_models():
    assert export_models() == {"models": {}, "enums": {}}
