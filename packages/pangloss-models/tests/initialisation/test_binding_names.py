"""The names a binding or an index gives are checked against the models: a misspelt one would never apply"""

from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Document,
    Entity,
    FieldBinding,
    PanglossMetaError,
    PanglossModelError,
    RelationConfig,
    initialise,
)


class _Declared:
    @staticmethod
    @no_type_check
    def models(binding: FieldBinding):
        class Place(Entity):
            pass

        class Statement(Document):
            when: str | None = None
            at: Annotated[list[Place], RelationConfig(bind_to_child_field=[binding])]

        class Child(Document):
            action_when: str | None = None


@no_type_check
def test_a_binding_of_fields_and_models_that_exist_is_accepted():
    _Declared.models(
        FieldBinding(
            bound_field="when",
            child_fields=["action_when"],
            allowed_type_names=["Child"],
            excluded_type_names=["Place"],
        )
    )
    initialise(bind_database=False)


@no_type_check
def test_a_bound_field_that_is_not_a_field_is_refused_with_a_suggestion():
    _Declared.models(FieldBinding(bound_field="whn", child_fields=["action_when"]))

    with pytest.raises(PanglossModelError) as error:
        initialise(bind_database=False)

    assert "Statement.at" in str(error.value)
    assert "Did you mean 'when'?" in str(error.value)
    assert error.value.at_string.option == "bound_field"
    assert error.value.at_string.value == "whn"


@no_type_check
def test_a_child_field_that_no_model_has_is_refused():
    _Declared.models(FieldBinding(bound_field="when", child_fields=["action_whn"]))

    with pytest.raises(PanglossModelError) as error:
        initialise(bind_database=False)

    assert "no model has a field of that name" in str(error.value)
    assert "Did you mean 'action_when'?" in str(error.value)


@no_type_check
@pytest.mark.parametrize("option", ["allowed_type_names", "excluded_type_names"])
def test_a_type_name_that_is_not_a_model_is_refused(option):
    _Declared.models(
        FieldBinding(
            bound_field="when", child_fields=["action_when"], **{option: ["Chidl"]}
        )
    )

    with pytest.raises(PanglossModelError) as error:
        initialise(bind_database=False)

    assert "there is no model of that name" in str(error.value)
    assert "Did you mean 'Child'?" in str(error.value)
    assert error.value.at_string.option == option


@no_type_check
def test_the_name_of_a_class_above_a_model_is_a_model_name():
    class Agent(Entity):
        pass

    class Person(Agent):
        pass

    class Statement(Document):
        when: str | None = None
        by: Annotated[
            list[Person],
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(
                        bound_field="when",
                        child_fields=["x"],
                        allowed_type_names=["Agent"],
                    )
                ]
            ),
        ]
        x: str | None = None

    initialise(bind_database=False)


@no_type_check
def test_an_index_that_is_not_a_field_is_refused_with_a_suggestion():
    class Person(Entity):
        _meta = Entity.Meta(indexes=["nmae"])
        name: str

    with pytest.raises(PanglossMetaError) as error:
        initialise(bind_database=False)

    assert "Did you mean 'name'?" in str(error.value)
    assert error.value.at_string.candidates == ("name", "label")


@no_type_check
def test_an_extra_field_that_is_not_a_literal_field_is_refused_with_a_suggestion():
    class Person(Entity):
        _meta = Entity.Meta(reference_view_extra_fields=["nmae"])
        name: str

    with pytest.raises(PanglossModelError) as error:
        initialise(bind_database=False)

    assert "Did you mean 'name'?" in str(error.value)
    assert error.value.at_string.option == "reference_view_extra_fields"
