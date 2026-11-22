"""Which classes have names, and which of their fields are names (`_names_meta`, implementation_docs/similarity-build-plan.md,
step 8.3). No database."""

from typing import no_type_check

import pytest
from pangloss_models import Document, Entity, PanglossMetaError, Trait, initialise
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_names import NamesMeta
from pangloss_names.meta import named
from pangloss_vectors import VectorsMeta


@no_type_check
def test_with_no_slot_an_entity_has_its_label_as_a_name_and_a_document_has_none():
    class Person(Entity):
        pass

    class Letter(Document):
        pass

    initialise()
    assert named() == {"Person": ["label"]}


@no_type_check
def test_a_document_has_names_if_its_class_says_so():
    class Letter(Document):
        _names_meta = NamesMeta(include=True)

    class Note(Document):
        pass

    initialise()
    assert named() == {"Letter": ["label"]}


@no_type_check
def test_the_slot_is_inherited_and_a_subclass_s_own_overrides_it():
    class Person(Entity):
        nickname: str | None = None
        _names_meta = NamesMeta(fields=["label", "nickname"])

    class Saint(Person):
        pass

    class Place(Entity):
        _names_meta = NamesMeta(include=False)

    class Town(Place):
        _names_meta = NamesMeta()

    class Village(Place):
        pass

    initialise()
    assert named() == {
        "Person": ["label", "nickname"],
        "Saint": ["label", "nickname"],
        "Town": ["label"],
    }


@no_type_check
def test_a_trait_s_setting_counts_for_the_classes_that_have_it():
    class Unnamed(Trait):
        _names_meta = NamesMeta(include=False)

    class Ship(Entity, Unnamed):
        pass

    class Person(Entity):
        pass

    initialise()
    assert named() == {"Person": ["label"]}


@no_type_check
def test_a_list_of_text_and_optional_text_are_taken_as_names():
    class Person(Entity):
        aliases: list[str] = []
        nickname: str | None = None
        title: str = ""
        _names_meta = NamesMeta(fields=["label", "aliases", "nickname", "title"])

    initialise()
    assert named() == {"Person": ["label", "aliases", "nickname", "title"]}


@no_type_check
def test_a_field_named_twice_is_one_name_field():
    class Person(Entity):
        _names_meta = NamesMeta(fields=["label", "label"])

    initialise()
    assert named() == {"Person": ["label"]}


@no_type_check
@pytest.mark.parametrize("annotation", [int, list[int], bool])
def test_a_field_that_is_not_text_is_refused_by_the_class_that_says_it(annotation):
    class Person(Entity):
        __annotations__ = {"age": annotation}
        _names_meta = NamesMeta(fields=["label", "age"])

    class Saint(Person):
        pass

    with pytest.raises(PanglossMetaError, match="Person: .*'age', which is not text"):
        initialise()


@no_type_check
def test_a_relation_is_not_a_name():
    class Place(Entity):
        pass

    class Person(Entity):
        born_in: Place | None = None
        _names_meta = NamesMeta(fields=["born_in"])

    with pytest.raises(PanglossMetaError, match="'born_in', which is not text"):
        initialise()


@no_type_check
def test_a_field_the_class_has_not_is_refused_and_a_close_one_offered():
    class Person(Entity):
        nickname: str = ""
        _names_meta = NamesMeta(fields=["label", "nickame"])

    with pytest.raises(
        PanglossMetaError,
        match=r"Person: .*'nickame', which is not a field of Person\. Did you mean 'nickname'\?",
    ):
        initialise()


@no_type_check
def test_a_field_a_subclass_inherits_the_setting_for_and_has_not_is_refused_by_the_parent_s_name():
    class Named(Trait):
        _names_meta = NamesMeta(fields=["label", "nickname"])

    class Person(Entity, Named):
        nickname: str = ""

    class Ship(Entity, Named):
        pass

    with pytest.raises(
        PanglossMetaError, match="Named: .*'nickname', which is not a field of Ship"
    ):
        initialise()


@no_type_check
def test_no_field_at_all_is_refused():
    class Person(Entity):
        _names_meta = NamesMeta(fields=[])

    with pytest.raises(PanglossMetaError, match="names no field"):
        initialise()


@no_type_check
def test_a_string_for_the_fields_is_refused():
    class Person(Entity):
        _names_meta = NamesMeta(fields="label")

    with pytest.raises(PanglossMetaError, match="is a list of the fields"):
        initialise()


@no_type_check
def test_the_slot_on_a_wrapper_is_refused():
    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str
        _names_meta = NamesMeta()

    class Note(Document):
        about: list[InRole[Person]]

    with pytest.raises(PanglossMetaError, match="InRole: NamesMeta is for a class"):
        initialise()


@no_type_check
def test_a_class_that_has_no_vectors_has_no_names():
    class Person(Entity):
        pass

    class Secret(Entity):
        _vectors_meta = VectorsMeta(include=False)

    initialise()
    assert named() == {"Person": ["label"]}


@no_type_check
def test_a_class_the_settings_leave_out_of_the_vectors_has_no_names(
    project_settings,
):
    from pangloss_core.settings import configure

    configure(project_settings(VECTORS_EXCLUDE=["Person"]))

    class Person(Entity):
        pass

    class Saint(Person):
        pass

    class Place(Entity):
        pass

    initialise()
    assert named() == {"Place": ["label"]}


@no_type_check
def test_an_abstract_class_is_not_listed_and_its_concrete_subclasses_are():
    class Agent(Entity):
        _meta = Entity.Meta(abstract=True)

    class Person(Agent):
        pass

    initialise()
    assert named() == {"Person": ["label"]}
