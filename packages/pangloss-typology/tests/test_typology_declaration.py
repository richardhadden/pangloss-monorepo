"""Declaring a typology: the entity it makes, and what is refused"""

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossMetaError, PanglossModelError
from pangloss_models.model_bases.entity import Entity
from pangloss_typology import Typed, Typology, TypologyMeta


def test_a_typology_makes_an_entity_named_in_its_meta():
    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType")

    assert issubclass(RoleTypology.Type, Entity)
    assert RoleTypology.Type.__name__ == "RoleType"
    assert Typology.registry["RoleType"] is RoleTypology


def test_the_entity_has_what_an_entity_has():
    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType")

    initialise(bind_database=False)
    created = RoleTypology.Type.Create(label="Secretary", is_subtype_of=[])
    assert created.label == "Secretary"
    fields = RoleTypology.Type._meta.fields
    assert fields["is_subtype_of"].reverse_name == "is_supertype_of"
    assert "description" in fields


@pytest.mark.parametrize("name", ["Type", "Role", "RoleTypes", "roleType", "Role Type"])
def test_the_name_must_end_in_type_and_be_more_than_that(name):
    with pytest.raises(PanglossMetaError, match="ending in 'Type'"):
        TypologyMeta(name=name)


def test_a_typology_cannot_be_subclassed():
    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType")

    with pytest.raises(PanglossMetaError, match="inherit directly from Typology"):

        class NarrowTypology(RoleTypology):
            _typology_meta = TypologyMeta(name="NarrowType")


def test_a_typology_needs_a_meta():
    with pytest.raises(PanglossMetaError, match="_typology_meta"):

        class RoleTypology(Typology):
            pass


def test_the_class_name_must_end_in_typology():
    with pytest.raises(PanglossMetaError, match="end in 'Typology'"):

        class Roles(Typology):
            _typology_meta = TypologyMeta(name="RoleType")


def test_a_name_that_is_already_a_model_is_refused():
    class RoleType(Entity):
        pass

    with pytest.raises(PanglossMetaError, match="already a model called RoleType"):

        class RoleTypology(Typology):
            _typology_meta = TypologyMeta(name="RoleType")


def test_defaults_and_concrete_are_for_a_typology_that_is_also_something():
    with pytest.raises(PanglossMetaError, match="`also`"):
        TypologyMeta(name="RoleType", defaults={"a": 1})
    with pytest.raises(PanglossMetaError, match="'per_type' or 'always'"):
        TypologyMeta(name="RoleType", concrete="sometimes")  # ty: ignore[invalid-argument-type]


def test_typed_is_the_entity_of_the_typology():
    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType")

    assert Typed[RoleTypology] is RoleTypology.Type
    with pytest.raises(PanglossMetaError):
        Typed[int]


def test_an_entity_can_have_types_through_has_type():
    class Role(Entity):
        has_type: list[Typed[RoleTypology]]

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType")

    initialise(bind_database=False)
    field = Role._meta.fields["has_type"]
    assert field.reverse_name == "type_of"
    assert field.wrapper is list
    Role.Create(label="Maximilian's secretary", has_type=[])


def test_the_relation_to_a_type_must_be_called_has_type():
    class Role(Entity):
        kind: list[Typed[RoleTypology]]

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType")

    with pytest.raises(PanglossModelError, match="call the field 'has_type'"):
        initialise(bind_database=False)


def test_one_has_type_can_go_to_several_typologies():
    class Post(Entity):
        has_type: list[Typed[RoleTypology] | Typed[OfficeTypology]]

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType")

    class OfficeTypology(Typology):
        _typology_meta = TypologyMeta(name="OfficeType")

    initialise(bind_database=False)
    assert len(Post._meta.fields["has_type"].type_options) == 2


def test_labels_in_other_languages_come_from_the_settings():
    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType")

    initialise(bind_database=False)
    fields = RoleTypology.Type.Create.model_fields
    assert {"label_de", "label_pt_br"} <= set(fields)
    assert "label_en" not in fields  # (the default language is `label`)
    assert (
        RoleTypology.Type.Create(
            label="Secretary", label_de="Sekretär", is_subtype_of=[]
        ).label_de
        == "Sekretär"
    )


def test_the_languages_can_be_given_in_the_meta():
    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType", languages=["fr"])

    initialise(bind_database=False)
    fields = RoleTypology.Type.Create.model_fields
    assert "label_fr" in fields
    assert "label_de" not in fields


def test_the_entity_is_given_the_pages_of_the_interface_module():
    pytest.importorskip("pangloss_interface")
    from pangloss_interface.meta import resolved_meta

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType")

    initialise(bind_database=False)
    meta = resolved_meta(RoleTypology.Type)
    assert meta["listPage"] == {"module": "pangloss_typology", "name": "TypeTree"}
    assert meta["itemPage"] == {"module": "pangloss_typology", "name": "TypeItem"}
    assert meta["viewCard"] == {"module": "pangloss_typology", "name": "TypeCard"}


def test_a_type_that_is_also_a_class_keeps_what_that_class_sets_apart_from_the_pages():
    pytest.importorskip("pangloss_interface")
    from pangloss_interface import InterfaceMeta
    from pangloss_interface.meta import resolved_meta

    class Role(Entity):
        has_type: list[Typed[RoleTypology]]
        _interface_meta = InterfaceMeta(colour="amber", view_card="app:RoleCard")

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType", also=Role)

    initialise(bind_database=False)
    meta = resolved_meta(RoleTypology.Type)
    assert meta["colour"] == "amber"
    assert meta["viewCard"] == {"module": "pangloss_typology", "name": "TypeCard"}
