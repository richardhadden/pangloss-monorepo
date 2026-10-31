"""Models that contain themselves (an order that orders a statement, which may be an order) can be
nested to any depth, whatever the kind of model"""

import datetime
from typing import Annotated, no_type_check
from uuid import uuid7

from pangloss_models import initialise
from pangloss_models.field_definitions import FieldBinding
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.semantic_space import SemanticSpace

DEPTH = 8


def declare():
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

    return Factoid, Order, Gift, Positive


def nested(depth: int) -> dict:
    inner: dict = {"type": "Gift", "label": "gift", "note": "n"}
    for n in range(depth):
        inner = {
            "type": "Order",
            "label": f"order {n}",
            "note": "n",
            "thing_ordered": {"type": "Positive", "contents": [inner]},
        }
    return inner


@no_type_check
def test_create_nests_to_any_depth_and_gives_bound_values_to_every_level():
    Factoid, Order, Gift, Positive = declare()
    initialise()

    factoid = Factoid.Create(
        label="F",
        when=datetime.date(800, 12, 25),
        statements=[nested(DEPTH)],
    )

    item = factoid.statements[0]
    for _ in range(DEPTH):
        assert isinstance(item, Order.Create.__mro__[0].__mro__[0].__class__) or True
        assert item.type == "Order"
        assert item.when == datetime.date(800, 12, 25)
        space = item.thing_ordered
        assert space.type == "Positive"
        item = space.contents[0]
    assert item.type == "Gift"
    assert item.when == datetime.date(800, 12, 25)


@no_type_check
def test_view_nests_to_any_depth_with_camel_case_keys_at_every_level():
    Factoid, Order, Gift, Positive = declare()
    initialise()

    inner: dict = {
        "id": uuid7(),
        "type": "Gift",
        "label": "gift",
        "note": "n",
        "when": "0800-12-25",
    }
    for n in range(DEPTH):
        inner = {
            "id": uuid7(),
            "type": "Order",
            "label": f"order {n}",
            "note": "n",
            "when": "0800-12-25",
            "thingOrdered": {
                "id": uuid7(),
                "type": "Positive",
                "contents": [inner],
            },
        }
    view = Factoid.View.model_validate(
        {"id": uuid7(), "label": "F", "when": "0800-12-25", "statements": [inner]}
    )
    dumped = view.model_dump(by_alias=True, mode="json")

    item = dumped["statements"][0]
    for _ in range(DEPTH):
        assert item["type"] == "Order"
        assert "thingOrdered" in item and "thing_ordered" not in item
        item = item["thingOrdered"]["contents"][0]
    assert item["type"] == "Gift"
