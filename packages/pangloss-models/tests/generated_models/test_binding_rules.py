"""Which items a `FieldBinding` applies to"""

from types import SimpleNamespace

import pytest
from pangloss_models.field_definitions import FieldBinding
from pangloss_models.model_bases.binding import allow_bind_on_this_item


@pytest.mark.parametrize(
    ("allowed", "excluded", "type_name", "applies"),
    [
        ([], [], "Activity", True),
        (["Activity"], [], "Activity", True),
        (["Activity"], [], "Transfer", False),
        ([], ["Transfer"], "Activity", True),
        ([], ["Transfer"], "Transfer", False),
        # both: it must be allowed and not excluded
        (["Activity", "Transfer"], ["Transfer"], "Activity", True),
        (["Activity", "Transfer"], ["Transfer"], "Transfer", False),
        (["Activity"], ["Transfer"], "Place", False),
    ],
)
def test_a_binding_applies_to_the_types_allowed_and_not_excluded(
    allowed, excluded, type_name, applies
):
    binding = FieldBinding(
        bound_field="year",
        child_fields=["year"],
        allowed_type_names=allowed,
        excluded_type_names=excluded,
    )
    assert allow_bind_on_this_item(SimpleNamespace(type=type_name), binding) is applies
