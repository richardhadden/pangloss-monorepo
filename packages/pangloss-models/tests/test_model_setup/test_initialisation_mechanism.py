import datetime
from typing import Annotated

from pangloss_models import initialise
from pangloss_models.field_definitions import FieldBinding
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_registry import ModelRegistry


def test_initialisation_of_single_model():

    class Factoid(Document):
        pass

    assert "Factoid" in ModelRegistry.all_models()


def test_initialisation_of_referenced_model():

    class Factoid(Document):
        statements: Statement

    class Statement(Document):
        title: str

    initialise()

    assert "Factoid" in ModelRegistry.all_models()
    assert "Statement" in ModelRegistry.all_models()

    assert Factoid._meta.fields["statements"]
    assert Statement._meta.fields["title"]

    assert Factoid.Create
    assert Factoid.Create.model_fields["statements"]

    assert Statement.Create
    assert Statement.Create.model_fields["title"]


def test_initialisation_of_referenced_model_reverse_order():

    class Statement(Document):
        title: str

    class Factoid(Document):
        statements: Statement

    initialise()

    assert "Factoid" in ModelRegistry.all_models()
    assert "Statement" in ModelRegistry.all_models()

    assert Factoid._meta.fields["statements"]
    assert Statement._meta.fields["title"]

    assert Factoid.Create
    assert Factoid.Create.model_fields["statements"]

    assert Statement.Create
    assert Statement.Create.model_fields["title"]


def test_initialisation_of_random_ordered_declaration_1():
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order():
    """Test with alternating document and generic declarations"""

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_1():
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_2():
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_3():
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_4():
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_5():
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_6():
    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_7():
    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_8():
    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_9():
    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_10():
    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_11():
    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_12():
    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_13():
    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_14():
    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_15():
    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_16():
    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_17():
    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_18():
    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_19():
    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_20():
    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_21():
    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_22():
    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_23():
    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_24():
    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_25():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_26():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_27():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_28():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_29():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_30():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_31():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_32():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_33():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_34():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_35():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_36():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_37():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_38():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_39():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_40():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_41():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_42():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_43():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_44():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_45():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_46():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_47():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_48():
    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_49():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_50():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_51():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_52():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_53():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_54():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_55():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_56():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_57():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_58():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_59():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_60():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_61():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_62():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_63():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_64():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_65():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_66():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_67():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_68():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_69():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_70():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_71():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_72():
    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_73():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_74():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_75():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_76():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_77():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_78():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_79():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_80():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_81():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_82():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_83():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_84():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_85():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_86():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_87():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_88():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_89():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_90():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_91():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_92():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_93():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_94():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_95():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_96():
    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_97():
    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_98():
    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_99():
    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_100():
    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_101():
    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_102():
    class Action(Document):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_103():
    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_104():
    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_105():
    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_106():
    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_107():
    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_108():
    class Action(Document):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_109():
    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_110():
    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_111():
    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_112():
    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_113():
    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_114():
    class Action(Document):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_115():
    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_116():
    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_117():
    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    class Subjunctive[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_118():
    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_119():
    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_interleaved_order_120():
    class Action(Document):
        pass

    class Order(Document):
        thing_ordered: Subjunctive[Action]

    class Subjunctive[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        statements: list[Negative[Order]]

    class Negative[T](SemanticSpace[T]):
        pass

    initialise()

    assert Factoid._meta.fields["statements"]

    assert Factoid.Create
    assert Order.Create
    assert Action.Create

    assert Factoid.Create.model_fields["statements"]
    assert Order.Create.model_fields["thing_ordered"]


def test_initialisation_with_bound_self_reference():
    """Tests that we don't have an infinite recursion creating
    bound field model variant"""

    class Action(Document):
        action_when: datetime.date
        subaction: Action

    class Negative[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        when: datetime.date
        action: Annotated[
            Negative[Action],
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(
                        bound_field="when",
                        child_fields=["action_when"],
                        allowed_type_names=["Action"],
                        converter=lambda x: x + datetime.timedelta(days=1),
                    ),
                ]
            ),
        ]

    initialise()
