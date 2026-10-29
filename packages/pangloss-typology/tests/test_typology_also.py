"""A type that is also another entity (`also=Role`)"""

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossMetaError
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.labels import labels_for_model
from pangloss_typology import Typed, Typology, TypologyMeta


def test_the_entity_is_a_subclass_of_the_other_class():
    class Role(Entity):
        has_type: list[Typed[RoleTypology]]
        held: bool = False

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType", also=Role)

    initialise(bind_database=False)
    assert issubclass(RoleTypology.Type, Role)
    assert "Role" in labels_for_model(RoleTypology.Type, "Entity")


def test_a_required_field_of_the_other_class_needs_a_default():
    class Role(Entity):
        has_type: list[Typed[RoleTypology]]
        holder_known: bool

    with pytest.raises(PanglossMetaError, match="requires holder_known"):

        class RoleTypology(Typology):
            _typology_meta = TypologyMeta(name="RoleType", also=Role)


def test_the_defaults_fill_them_and_lists_are_empty():
    class Role(Entity):
        has_type: list[Typed[RoleTypology]]
        holder_known: bool

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(
            name="RoleType", also=Role, defaults={"holder_known": False}
        )

    initialise(bind_database=False)
    assert RoleTypology.new_values() == {
        "is_subtype_of": [],
        "holder_known": False,
        "has_type": [],
    }
    made = RoleTypology.Type.Create(label="Secretary", **RoleTypology.new_values())
    assert made.holder_known is False


def test_defaults_for_fields_the_class_does_not_have_are_refused():
    class Role(Entity):
        has_type: list[Typed[RoleTypology]]

    with pytest.raises(PanglossMetaError, match="has fields that Role does not: nope"):

        class RoleTypology(Typology):
            _typology_meta = TypologyMeta(
                name="RoleType", also=Role, defaults={"nope": 1}
            )


def test_per_type_has_a_switch_and_leaves_the_labels_to_the_service():
    class Role(Entity):
        has_type: list[Typed[RoleTypology]]

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType", also=Role)

    initialise(bind_database=False)
    made = RoleTypology.Type.Create(label="Secretary", **RoleTypology.new_values())
    assert made.is_concrete is None  # (off)
    assert RoleTypology.Type.__labels_unmanaged__ == ("Role",)


def test_always_has_no_switch_and_the_label():
    class Role(Entity):
        has_type: list[Typed[RoleTypology]]

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType", also=Role, concrete="always")

    initialise(bind_database=False)
    assert "is_concrete" not in RoleTypology.Type.Create.model_fields
    assert not hasattr(RoleTypology.Type, "__labels_unmanaged__")
