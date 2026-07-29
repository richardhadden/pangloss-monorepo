from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.semantic_space import SemanticSpace

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
async def test_read_nested_object(clear_database):
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    class Statement(Document):
        _meta = Document.Meta(abstract=True)

    class Order(Statement):
        order_given_by: Person
        order_received_by: Person
        thing_ordered: list[Action]

    class Action(Statement):
        action_carried_out_by: Person

    class Person(Entity):
        pass

    initialise()

    js = Person.Create(label="John Smith")
    js = await js.save()
    assert js.id

    km = Person.Create(label="Kaiser Maximilian")
    km = await km.save()
    assert km.id

    factoid = Factoid.Create(
        label="A Factoid",
        statements=[
            {
                "type": "Negative",
                "contents": [
                    {
                        "type": "Order",
                        "label": "KM orders JS to take an action",
                        "order_given_by": {"type": "Person", "id": km.id},
                        "order_received_by": {"type": "Person", "id": js.id},
                        "thing_ordered": [
                            {
                                "type": "Action",
                                "label": "JS carries out an action",
                                "action_carried_out_by": {
                                    "type": "Person",
                                    "id": js.id,
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    )

    factoid_ref = await factoid.save(return_type="Full")
    assert isinstance(factoid_ref, Factoid.HeadView)
    assert factoid_ref.id

    assert factoid_ref.statements[0].contents[0].type == "Order"

    order_id = factoid_ref.statements[0].contents[0].id

    order_from_db = await Order.get(id=str(order_id))

    assert order_from_db.meta.head_node_type == "Factoid"
    assert order_from_db.meta.head_node_id == factoid_ref.id

    assert order_from_db.meta.created_by == "pangloss_default_user"
    assert order_from_db.meta.semantic_spaces == ["Negative"]
    assert order_from_db.meta.semantic_space_labels == ["Factoid -> Negative"]
    assert order_from_db.order_given_by.id == km.id
    assert order_from_db.order_given_by.label == "Kaiser Maximilian"
    assert order_from_db.order_received_by.id == js.id
    assert order_from_db.order_received_by.label == "John Smith"

    thing_ordered = order_from_db.thing_ordered[0]
    assert thing_ordered

    assert thing_ordered.type == "Action"

    assert thing_ordered.meta.semantic_spaces == ["Negative"]
    assert thing_ordered.meta.semantic_space_labels == ["Factoid -> Negative"]

    assert thing_ordered.action_carried_out_by.id == js.id
