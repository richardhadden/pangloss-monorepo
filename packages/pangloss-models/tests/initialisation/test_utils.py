from datetime import date, datetime
from typing import Annotated, Generic

from annotated_types import MaxLen
from pydantic import BaseModel
from pydantic_meta_kit import WithMeta

from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.base_models import _BaseObject, _DeclaredClass
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document, DocumentMeta
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded, EmbeddedMeta
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.model_bases.reified_relation import (
    ReifiedRelation,
    ReifiedRelationDocument,
)
from pangloss_models.model_bases.relation import Relation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import (
    NonHeritableTrait,
    Trait,
    _Trait,
)
from pangloss_models.utils import (
    generic_get_subclasses,
    get_all_parent_classes,
    get_concrete_types,
    get_direct_instantiations_of_trait,
    get_parent_class,
    get_top_level_classes,
    is_embedded,
    is_list_of_literal,
    is_list_relatable,
    is_literal,
    is_relatable,
    is_union_of_embedded,
)


def test_is_literal():
    """Verify that primitives and builtin types are treated as literals."""

    class Statement(Document):
        pass

    assert is_literal(str)
    assert is_literal(int)
    assert is_literal(float)
    assert is_literal(date)
    assert is_literal(datetime)
    assert is_literal(str | None)

    assert not is_literal(Statement)
    assert not is_literal(None)


def test_is_list_of_literal():
    """Verify that only list[...] of literals are treated as literal lists."""

    class Statement(Document):
        pass

    assert not is_list_of_literal(str)

    assert is_list_of_literal(list[str])

    assert not is_list_of_literal(list[Statement])

    assert is_list_of_literal(list[Annotated[str, MaxLen(1)]])

    assert not is_list_of_literal(list[str | int])


def test_is_relatable():
    """Validate that various types are recognized as relatables for relation fields."""

    class ToDogEdge(EdgeModel):
        when: date

    class Factoid(Document):
        pass

    class Statement(Document):
        concerns_dog: Dog
        concerns_dog_list: list[Dog]
        concerns_dog_annotated: Annotated[
            list[ViaEdge[Dog, ToDogEdge]],
            RelationConfig(reverse_name="is_concerned_in"),
        ]
        concerns_animal_multiple: Annotated[
            list[ViaEdge[Dog, ToDogEdge]] | Cat,
            RelationConfig(reverse_name="is_animal_in"),
        ]

    class Dog(Entity):
        name: str

    class Cat(Entity):
        name: str

    assert is_relatable(Statement)
    assert is_relatable(Dog)
    assert is_relatable(Factoid)
    assert is_relatable(ViaEdge[Dog, ToDogEdge])
    assert is_relatable(Dog | Cat)
    assert is_list_relatable(list[ViaEdge[Dog, ToDogEdge]])
    assert is_list_relatable(list[Dog])
    assert is_list_relatable(list[Statement])
    assert is_list_relatable(list[Factoid])


def test_is_relatable_on_semantic_space():
    class Negative[Content](SemanticSpace[Content]):
        pass

    class Statement(Document):
        pass

    assert is_relatable(Negative[Statement])


def test_is_relatable_on_conjunction():
    class Action(Document):
        pass

    class Alternative[T](Conjunction):
        alternatives: T

    assert is_relatable(Alternative)
    assert is_relatable(Alternative[Action])


def test_is_embedded():
    class Thing(Embedded):
        pass

    assert is_embedded(Thing)


def test_is_union_embedded():
    class Thing(Embedded):
        pass

    class Thong(Embedded):
        pass

    assert is_union_of_embedded(Thing | Thong)


def test_get_generic_subclasses():
    class Statement(Document):
        pass

    class Action(Statement):
        pass

    class CreationOfArtwork(Action):
        pass

    class CreationOfPainting(CreationOfArtwork):
        pass

    assert generic_get_subclasses(Statement) == set(
        [Action, CreationOfArtwork, CreationOfPainting]
    )


def test_get_concrete_types_simple():
    class Statement(Document):
        pass

    class Other(Document):
        pass

    class Action(Statement):
        pass

    class CreationOfArtwork(Action):
        _meta = DocumentMeta(abstract=True)

    class CreationOfPainting(CreationOfArtwork):
        pass

    assert get_concrete_types(Statement) == set([Statement, Action, CreationOfPainting])

    assert get_concrete_types(Statement, include_abstract=True) == set(
        [Statement, Action, CreationOfArtwork, CreationOfPainting]
    )

    # Throw in a union type here to check it works
    assert get_concrete_types(Statement | Other) == set(
        [Statement, Action, CreationOfPainting, Other]
    )


def test_get_concrete_types_with_abstract():
    class Statement(Document):
        _meta = DocumentMeta(abstract=True)

    class Thing(Statement):
        pass

    assert get_concrete_types(Statement) == set([Thing])


def test_get_concrete_types_with_abstract_in_union():
    class Statement(Document):
        _meta = DocumentMeta(abstract=True)

    class Thing(Document):
        pass

    assert get_concrete_types(Statement | Thing) == set([Thing])


def test_get_concrete_types_with_embedded_abstract_in_union():
    class Date(Embedded):
        _meta = EmbeddedMeta(abstract=True)
        when: datetime

    class Statement(Document):
        date: Date

    class SpecialDate(Date):
        pass

    assert get_concrete_types(Date) == set([SpecialDate])
    assert get_concrete_types(SpecialDate) == set([SpecialDate])
    assert get_concrete_types(Date | SpecialDate) == set([SpecialDate])


def test_get_concrete_types_with_semantic_spaces():
    class Negative[Contents](SemanticSpace[Contents]):
        pass

    class ReallyNegative(Negative):
        pass

    assert get_concrete_types(Negative) == set([Negative, ReallyNegative])


def test_get_concrete_types_with_semantic_spaces_does_not_return_parametrised():
    class Negative[Contents](SemanticSpace[Contents]):
        pass

    class ReallyNegative(Negative):
        pass

    class Statement(Document):
        action: Negative[Task]

    class Task(Document):
        pass

    assert get_concrete_types(Negative) == set([Negative, ReallyNegative])


def test_usable_declared_classes():
    assert get_top_level_classes() == set(
        [
            Conjunction,
            Document,
            EdgeModel,
            Embedded,
            Entity,
            ReifiedRelation,
            ReifiedRelationDocument,
            SemanticSpace,
            Relation,
            Trait,
            NonHeritableTrait,
            _BaseObject,
            _DeclaredClass,
            WithMeta,
            _Trait,
            BaseModel,
            object,
            Generic,
            AnnotatedValue,
        ]
    )


def test_get_parent_class():
    class Statement(Document):
        pass

    class Action(Statement):
        pass

    parent_class = get_parent_class(Action)

    assert parent_class is Statement


def test_get_all_parent_classes():
    class Statement(Document):
        something: int

    class Action(Statement):
        pass

    class Task(Action):
        pass

    assert get_all_parent_classes(Task) == [Action, Statement]


def test_get_all_parent_classes_with_heritable_trait():
    class Statement(Document):
        something: int

    class WithPrimaryAgent(Trait):
        pass

    class Action(Statement, WithPrimaryAgent):
        pass

    class Task(Action):
        pass

    assert get_all_parent_classes(Task) == [Action, Statement, WithPrimaryAgent]


def test_is_subclass_of_heritable_trait():
    class Purchaseable(NonHeritableTrait):
        pass

    class Dog(Entity, Purchaseable):
        pass

    class Beagle(Dog):
        pass

    assert get_direct_instantiations_of_trait(Purchaseable) == {Dog}
