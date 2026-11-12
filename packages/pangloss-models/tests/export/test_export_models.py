import json
from enum import Enum
from typing import Annotated

from annotated_types import Ge
from pangloss_models import (
    AnnotatedValue,
    Companion,
    CompanionPart,
    Conjunction,
    CopyFromOuter,
    Document,
    Embedded,
    Entity,
    ReifiedRelation,
    RelationConfig,
    SemanticSpace,
    Standalone,
    Within,
    export_models,
    initialise,
)


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


def test_a_relation_says_which_fields_of_its_ancestors_it_stands_for():
    from pangloss_models import FieldSubclassing

    class Agent(Entity):
        pass

    class Person(Agent):
        pass

    class PhysicalObject(Entity):
        pass

    class Artwork(PhysicalObject):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True)
        involves: list[Agent]

    class Creation(Statement):
        created_by: Annotated[
            Person,
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing(field_name="involves", field_on_model=Statement)
                ]
            ),
        ]
        object_created: PhysicalObject

    class CreationOfArtwork(Creation):
        artwork_created: Annotated[
            Artwork, RelationConfig(subclasses_parent_fields=["object_created"])
        ]

    initialise()
    models = export_models()["models"]
    creation = by_name(models["Creation"])
    assert creation["created_by"]["subclasses"] == ["involves"]
    assert creation["object_created"]["subclasses"] == []
    artwork = by_name(models["CreationOfArtwork"])
    # (what it stands for, and what that stood for in turn: here nothing)
    assert artwork["artwork_created"]["subclasses"] == ["object_created"]
    assert "object_created" not in artwork
    assert by_name(models["Statement"])["involves"]["subclasses"] == []


def test_a_relation_says_what_reified_relation_an_entity_found_is_put_in():
    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Alternative[T](Conjunction):
        alternatives: list[T]

    class Identification[T](ReifiedRelation[T]):
        identified_by: str

    class Meeting(Document):
        # (the class, or the class as used: both are its name)
        attendees: Annotated[
            list[InRole[Person] | Identification[Alternative[Person]]],
            RelationConfig(default_reified_type=InRole),
        ]
        chair: Annotated[
            InRole[Person] | Identification[Alternative[Person]],
            RelationConfig(default_reified_type=Identification[Alternative[Person]]),
        ]
        host: Person

    initialise()
    meeting = by_name(export_models()["models"]["Meeting"])
    assert meeting["attendees"]["defaultReifiedType"] == "InRole"
    assert meeting["chair"]["defaultReifiedType"] == "Identification"
    assert meeting["host"]["defaultReifiedType"] is None


def test_a_model_says_whether_it_can_be_made_on_its_own():
    class Person(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(create_directly=False)
        about: Person

    class Gift(Statement):
        pass

    class Factoid(Document):
        statements: list[Statement]

    initialise()
    models = export_models()["models"]

    assert models["Person"]["createDirectly"] is True
    assert models["Factoid"]["createDirectly"] is True
    assert models["Statement"]["createDirectly"] is False
    assert models["Gift"]["createDirectly"] is False


def test_an_entity_says_what_companions_it_is_offered_with_by_the_names_and_keys_of_their_fields():
    class Source(Entity):
        pass

    class AtPage[T](ReifiedRelation[T]):
        page: str

    class Person(Entity):
        _meta = Entity.Meta(
            companions=[
                Companion(
                    name="naming",
                    document="Factoid",
                    field="statements",
                    parts=[CompanionPart(type="Naming", entity_field="named_person")],
                    copies=[CopyFromOuter(field="source_at_page", to="source_at_page")],
                    offered=[
                        Within(
                            heads=["Factoid"],
                            fields=["Naming.named_person"],
                            holders=["Naming"],
                        ),
                        Standalone(),
                    ],
                ),
                Companion(name="note", document="Note", entity_field="about_person"),
            ]
        )

    class Place(Entity):
        pass

    class Naming(Document):
        named_person: Person
        first_name: str | None = None

    class Factoid(Document):
        source_at_page: AtPage[Source]
        statements: list[Naming]

    class Note(Document):
        about_person: Person

    initialise()
    models = export_models()["models"]

    assert "companions" not in models["Place"]
    assert models["Person"]["companions"] == [
        {
            "name": "naming",
            "document": "Factoid",
            "field": {"name": "statements", "key": "statements"},
            "parts": [
                {
                    "type": "Naming",
                    "entityField": {"name": "named_person", "key": "namedPerson"},
                }
            ],
            "entityField": None,
            "copies": [
                {
                    "field": {"name": "source_at_page", "key": "sourceAtPage"},
                    "to": {"name": "source_at_page", "key": "sourceAtPage"},
                }
            ],
            "offered": [
                {
                    "kind": "within",
                    "heads": ["Factoid"],
                    "fields": [
                        {
                            "model": "Naming",
                            "name": "named_person",
                            "key": "namedPerson",
                        }
                    ],
                    "holders": ["Naming"],
                },
                {"kind": "standalone"},
            ],
        },
        {
            "name": "note",
            "document": "Note",
            "field": None,
            "parts": [],
            "entityField": {"name": "about_person", "key": "aboutPerson"},
            "copies": [],
            "offered": [],
        },
    ]
    # (not data: a change to a companion is not a migration)
    from pangloss_models.migrations.snapshot import NOT_DATA_KEYS

    assert "companions" in NOT_DATA_KEYS


def test_nothing_is_exported_before_there_are_models():
    assert export_models() == {"models": {}, "enums": {}}
