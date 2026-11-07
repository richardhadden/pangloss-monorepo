"""An embedded model with a relation, on a document that a `FieldBinding` reaches through an abstract class, is
made when it is first needed (PROBLEMS.md #37 of the smoke test: `initialise()` raised `AttributeError: Create`)"""

from typing import Annotated, no_type_check
from uuid import uuid7

from pangloss_models import (
    Document,
    Embedded,
    Entity,
    FieldBinding,
    RelationConfig,
    SemanticSpace,
    Trait,
    initialise,
)


def declare():
    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        pass

    class Act(Document):
        _meta = Document.Meta(abstract=True)
        text: str

    class Positive[T](SemanticSpace[T]):
        pass

    # (made after `Order`: the order of making models follows their direct dependencies, and `Order` reaches
    # `SealedLetter`, and so `Seal`, only through the abstract `Act`)
    class SealMatrix(Embedded):
        engraved_by: Person
        motto: str

    class Seal(Embedded):
        condition: str
        matrix: SealMatrix

    class SealedLetter(Act):
        sealed_by: Agent
        seal: Seal

    class Order(Act):
        ordered_to: Agent
        thing_ordered: Annotated[
            Positive[Act],
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(bound_field="ordered_to", child_fields=["sealed_by"])
                ]
            ),
        ]

    return Person, Seal, SealedLetter, Order


@no_type_check
def test_an_embedded_model_with_a_relation_is_made_when_a_binding_reaches_it_first():
    Person, Seal, SealedLetter, Order = declare()
    initialise()

    person = {"type": "Person", "id": uuid7()}
    order = Order.Create(
        label="Order",
        text="Seal it",
        ordered_to=person,
        thing_ordered={
            "type": "Positive",
            "contents": [
                {
                    "type": "SealedLetter",
                    "label": "Letter",
                    "text": "Sealed",
                    # (`sealed_by` is bound from `ordered_to`, so it need not be given)
                    "seal": {
                        "type": "Seal",
                        "condition": "good",
                        "matrix": {
                            "type": "SealMatrix",
                            "engraved_by": person,
                            "motto": "Semper",
                        },
                    },
                }
            ],
        },
    )
    letter = order.thing_ordered.contents[0]
    assert letter.type == "SealedLetter"
    assert letter.seal.matrix.engraved_by.id == person["id"]
    # (the embedded model has all its fields, in every kind, though its `Create` was asked for early)
    assert set(Seal.Create.model_fields) >= {"condition", "matrix"}
    assert set(Seal.View.model_fields) >= {"condition", "matrix"}
    assert set(Seal.Update.model_fields) >= {"condition", "matrix"}
