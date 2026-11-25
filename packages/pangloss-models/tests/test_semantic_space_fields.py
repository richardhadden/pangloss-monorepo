"""The fields of a semantic space that say what it does to its contents (`SemanticSpaceMeta`), and `Modal`"""

import dataclasses

import pytest
from pydantic import ValidationError

from pangloss_models import Modal, SemanticSpace


def test_a_space_that_says_nothing_is_uncommitted_describes_and_holds_many():
    class Reported[T](SemanticSpace[T]):
        pass

    meta = Reported._meta
    assert (meta.veridical, meta.fit, meta.logical, meta.unary, meta.degree) == (
        None,
        "describes",
        None,
        None,
        None,
    )
    assert meta.veridicality == 0
    assert meta.is_unary is False


def test_a_not_denies_its_one_item_unless_the_class_says_otherwise():
    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    assert Not._meta.veridicality == -1
    assert Not._meta.is_unary is True
    # (what is set is what is read: whether it may be set so is checked at `initialise()`)
    assert SemanticSpace.Meta(logical="not", veridical=0, unary=False).veridicality == 0
    assert SemanticSpace.Meta(logical="not", unary=False).is_unary is False


@pytest.mark.parametrize(
    "logical, veridicality, unary",
    [
        (Modal("necessity", "command"), 0, False),
        (Modal("possibility", "epistemic"), 0, False),
        (Modal("necessity", "command", of_not=True), 0, True),
        (Modal("possibility", "deontic", of_not=True), 0, True),
    ],
)
def test_a_modality_is_uncommitted_and_of_not_holds_one_item(
    logical, veridicality, unary
):
    meta = SemanticSpace.Meta(logical=logical)
    assert meta.veridicality == veridicality
    assert meta.is_unary is unary


def test_a_family_sets_its_values_once_and_a_subclass_changes_one():
    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            fit="prescribes", logical=Modal("necessity", "command"), degree="likely"
        )

    class Requested[T](Ordered[T]):
        _meta = SemanticSpace.Meta(degree="possible")

    class Forbidden[T](Ordered[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "command", of_not=True))

    assert Requested._meta.fit == "prescribes"
    assert Requested._meta.logical == Modal("necessity", "command")
    assert Requested._meta.degree == "possible"
    assert Forbidden._meta.fit == "prescribes"
    assert Forbidden._meta.degree == "likely"
    assert Forbidden._meta.is_unary is True
    assert Ordered._meta.degree == "likely"
    assert Ordered._meta.is_unary is False


def test_a_modal_is_a_value_that_cannot_be_changed():
    command = Modal("necessity", "command")
    assert command == Modal(force="necessity", flavour="command", of_not=False)
    assert command != Modal("necessity", "Command")
    assert len({command, Modal("necessity", "command")}) == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        command.flavour = "wish"  # ty: ignore[invalid-assignment]


@pytest.mark.parametrize(
    "arguments",
    [
        ("must", "command"),
        ("necessity", ""),
        ("necessity", "royal command"),
        ("necessity", 3),
    ],
)
def test_a_modal_is_refused_with_another_force_or_a_flavour_that_is_not_a_word(
    arguments,
):
    with pytest.raises(ValidationError):
        Modal(*arguments)


@pytest.mark.parametrize(
    "values",
    [
        {"veridical": 2},
        {"fit": "orders"},
        {"logical": "and"},
        {"degree": "certain"},
        {"unary": "yes please"},
    ],
)
def test_a_value_that_no_field_takes_is_refused(values):
    with pytest.raises(ValidationError):
        SemanticSpace.Meta(**values)
