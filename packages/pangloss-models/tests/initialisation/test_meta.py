import datetime

from pangloss_models.model_bases.document import Document, DocumentMeta
from pangloss_models.model_bases.embedded import Embedded, EmbeddedMeta


def test_meta_inheritance_of_abstract():
    class Statement(Document):
        _meta = DocumentMeta(abstract=True)

    class Action(Statement):
        pass

    class CreationOfArtwork(Action):
        _meta = DocumentMeta(abstract=True)

    class CreationOfPainting(CreationOfArtwork):
        pass

    assert Statement._meta.abstract is True
    assert Action._meta.abstract is False
    assert CreationOfArtwork._meta._owner_class is CreationOfArtwork
    assert CreationOfArtwork._meta.abstract is True
    assert CreationOfPainting._meta.abstract is False


def test_meta_inheritance_of_abstract_on_embedded():
    class Date(Embedded):
        _meta = EmbeddedMeta(abstract=True)
        when: datetime.datetime

    class Statement(Document):
        date: Date

    class SpecialDate(Date):
        pass

    assert Date._meta.abstract is True
    assert SpecialDate._meta.abstract is False


def test_an_entity_inherits_the_meta_of_its_parent():
    from pangloss_models.model_bases.entity import Entity

    class Base(Entity):
        _meta = Entity.Meta(create_with_id=True, create_inline=True, view_extra_fields=["a"])

    class Child(Base):
        pass

    class Grandchild(Child):
        _meta = Entity.Meta(view_extra_fields=["b"], accept_url_as_id=False)

    class Great(Grandchild):
        pass

    # (a value is inherited, and a list is added to)
    assert (Child._meta.create_with_id, Child._meta.create_inline) == (True, True)
    assert Child._meta.view_extra_fields == ["a"]
    assert (Grandchild._meta.create_with_id, Grandchild._meta.create_inline) == (True, True)
    assert Grandchild._meta.view_extra_fields == ["a", "b"]
    assert Grandchild._meta.accept_url_as_id is False
    # (from the nearest parent, not the farthest)
    assert Great._meta.accept_url_as_id is False
    assert Great._meta.view_extra_fields == ["a", "b"]


def test_a_document_inherits_the_meta_of_its_parent():
    class Base(Document):
        _meta = Document.Meta(create_with_id=True, require_label=False, view_extra_fields=["a"])

    class Child(Base):
        _meta = Document.Meta(view_extra_fields=["b"])

    assert Child._meta.create_with_id is True
    assert Child._meta.require_label is False
    assert Child._meta.view_extra_fields == ["a", "b"]
    assert Base._meta.view_extra_fields == ["a"]


def test_each_model_has_its_own_meta_that_names_it_as_the_owner():
    class Statement(Document):
        pass

    class Left(Statement):
        pass

    class Right(Statement):
        pass

    assert Statement._meta._owner_class is Statement
    assert Left._meta._owner_class is Left
    assert Right._meta._owner_class is Right
    # (what is made for a model is not shared with its parent or its siblings)
    assert Left._meta is not Statement._meta
    assert Left._meta.field_definitions is not Right._meta.field_definitions
    assert Left._meta.field_definitions is not Statement._meta.field_definitions


def test_a_parametrisation_of_a_generic_has_a_meta_of_its_own():
    from pangloss_models.model_bases.annotated_value import AnnotatedValue

    class WithSource[T](AnnotatedValue[T]):
        source: str

    narrow = WithSource[str]
    assert narrow._meta._owner_class is narrow
    assert WithSource._meta._owner_class is WithSource
    assert narrow._meta is not WithSource._meta


def test_a_trait_has_a_meta_of_its_own():
    from pangloss_models.model_bases.trait import NonHeritableTrait, Trait

    class Agent(Trait):
        pass

    class SpecialAgent(Agent):
        pass

    class Marker(NonHeritableTrait):
        pass

    assert Agent._meta._owner_class is Agent
    assert SpecialAgent._meta._owner_class is SpecialAgent
    assert SpecialAgent._meta is not Agent._meta
    assert Marker._meta._owner_class is Marker


def test_every_kind_of_model_has_its_own_meta_made_from_its_parents():
    from pangloss_models.model_bases.conjunction import Conjunction, ConjunctionMeta
    from pangloss_models.model_bases.edge_model import EdgeModel
    from pangloss_models.model_bases.embedded import Embedded
    from pangloss_models.model_bases.reified_relation import (
        ReifiedRelation,
        ReifiedRelationDocument,
        ReifiedRelationDocumentMeta,
    )
    from pangloss_models.model_bases.semantic_space import SemanticSpace, SemanticSpaceMeta

    class Date(Embedded):
        _meta = EmbeddedMeta(abstract=True)

    class ExactDate(Date):
        pass

    class Link[T](ReifiedRelation[T]):
        pass

    class Doc[T](ReifiedRelationDocument[T]):
        _meta = ReifiedRelationDocumentMeta(view_extra_fields=["a"])

    class SubDoc[T](Doc[T]):
        _meta = ReifiedRelationDocumentMeta(view_extra_fields=["b"], require_label=False)

    class Space[T](SemanticSpace[T]):
        _meta = SemanticSpaceMeta(require_label=True)

    class SubSpace[T](Space[T]):
        pass

    class Joins(Conjunction):
        _meta = ConjunctionMeta(require_label=True)

    class SubJoins(Joins):
        pass

    class Weight(EdgeModel):
        pass

    class Heavy(Weight):
        pass

    assert Date._meta.abstract is True and ExactDate._meta.abstract is False
    assert SubDoc._meta.view_extra_fields == ["a", "b"] and SubDoc._meta.require_label is False
    assert Doc._meta.view_extra_fields == ["a"]
    assert SubSpace._meta.require_label is True
    assert SubJoins._meta.require_label is True
    for model, parent in ((ExactDate, Date), (SubDoc, Doc), (SubSpace, Space), (SubJoins, Joins), (Heavy, Weight)):
        assert model._meta._owner_class is model
        assert model._meta is not parent._meta
        assert model._meta.field_definitions is not parent._meta.field_definitions
    assert Link._meta._owner_class is Link
    assert Link[int]._meta._owner_class is Link[int]
