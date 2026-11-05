"""Which items a `FieldBinding` applies to"""

from types import SimpleNamespace
from typing import Annotated, no_type_check
from uuid import uuid7

import pytest
from pangloss_models import (
    Document,
    Entity,
    FieldBinding,
    FieldSubclassing,
    RelationConfig,
    Trait,
    initialise,
)
from pangloss_models.model_bases.binding import (
    allow_bind_on_this_item,
    binding_applies,
    class_names,
    names_stood_for,
)
from pydantic import ValidationError


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


# (a binding's types are matched with the classes below them: a thing, a painting, a portrait of the painting)
class Thing:
    pass


class Painting(Thing):
    pass


class Portrait(Painting):
    pass


class Sculpture(Thing):
    pass


@pytest.mark.parametrize(
    ("allowed", "excluded", "cls", "applies"),
    [
        # a class below one allowed is allowed
        (["Thing"], [], Portrait, True),
        (["Painting"], [], Portrait, True),
        (["Painting"], [], Sculpture, False),
        # one above it is not
        (["Portrait"], [], Painting, False),
        # a class below one excluded is excluded
        ([], ["Painting"], Portrait, False),
        ([], ["Painting"], Sculpture, True),
        ([], ["Portrait"], Painting, True),
        # below one allowed and one excluded: excluded
        (["Thing"], ["Painting"], Portrait, False),
        (["Thing"], ["Painting"], Sculpture, True),
        (["Painting"], ["Thing"], Portrait, False),
    ],
)
def test_a_binding_applies_to_the_classes_below_those_it_names(
    allowed, excluded, cls, applies
):
    binding = FieldBinding(
        bound_field="year",
        child_fields=["year"],
        allowed_type_names=allowed,
        excluded_type_names=excluded,
    )
    assert binding_applies(binding, class_names(cls, cls.__name__)) is applies


def test_without_its_class_an_item_is_matched_by_its_type_name_alone():
    assert class_names(None, "Portrait") == {"Portrait"}
    assert class_names(Portrait, "Portrait") == {"Portrait", "Painting", "Thing"}


@no_type_check
def test_the_names_are_the_classes_of_the_project_and_its_traits_not_the_library_s():
    class Dated(Trait):
        pass

    class Made(Document, Dated):
        pass

    class PaintingMade(Made):
        pass

    initialise()
    assert class_names(PaintingMade, "PaintingMade") == {
        "PaintingMade",
        "Made",
        "Dated",
    }


def made_models():
    """An order of documents of a year: the year is given to every thing ordered but a sculpture (or a kind of one)"""

    class Made(Document):
        year: int

    class PaintingMade(Made):
        pass

    class PortraitMade(PaintingMade):
        pass

    class SculptureMade(Made):
        pass

    class BustMade(SculptureMade):
        pass

    class Order(Document):
        year: int
        things: Annotated[
            list[Made],
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(
                        bound_field="year",
                        child_fields=["year"],
                        allowed_type_names=["Made"],
                        excluded_type_names=["SculptureMade"],
                    )
                ]
            ),
        ]

    initialise()
    return Order


def things_of(order) -> dict[str, int | None]:
    return {thing.type: thing.year for thing in order.things}


@no_type_check
def test_a_binding_gives_its_value_to_subclasses_of_those_allowed_but_not_of_those_excluded():
    Order = made_models()
    order = Order.Create(
        label="An order",
        year=1500,
        things=[
            {"type": "Made", "label": "A thing"},
            {"type": "PaintingMade", "label": "A painting"},
            {"type": "PortraitMade", "label": "A portrait"},
            {"type": "SculptureMade", "label": "A sculpture", "year": 1600},
            {"type": "BustMade", "label": "A bust", "year": 1610},
        ],
    )
    assert things_of(order) == {
        "Made": 1500,
        "PaintingMade": 1500,
        "PortraitMade": 1500,
        "SculptureMade": 1600,
        "BustMade": 1610,
    }


@no_type_check
def test_a_bound_field_need_not_be_given_in_a_subclass_but_must_be_where_the_binding_does_not_apply():
    Order = made_models()
    # (a portrait's year is given by the order, so it may be left out)
    Order.Create(
        label="An order",
        year=1500,
        things=[{"type": "PortraitMade", "label": "A portrait"}],
    )
    # (a bust's is not: it is below a class excluded)
    for excluded in ("SculptureMade", "BustMade"):
        with pytest.raises(ValidationError):
            Order.Create(
                label="An order",
                year=1500,
                things=[{"type": excluded, "label": "A sculpture"}],
            )


@no_type_check
def test_an_update_applies_the_binding_to_subclasses_too():
    Order = made_models()
    order = Order.Update(
        id=uuid7(),
        label="An order",
        year=1500,
        things=[
            {"type": "PortraitMade", "label": "A portrait"},
            {"type": "BustMade", "label": "A bust", "year": 1610},
        ],
    )
    assert things_of(order) == {"PortraitMade": 1500, "BustMade": 1610}
    with pytest.raises(ValidationError):
        Order.Update(
            id=uuid7(),
            label="An order",
            year=1500,
            things=[{"type": "BustMade", "label": "A bust"}],
        )


def creation_models():
    """A commission of a thing, given to the creations it holds: into `object_created`, which each narrower creation
    has under another name (`artwork_created`, `painting_created`)"""

    class PhysicalObject(Entity):
        pass

    class Artwork(PhysicalObject):
        pass

    class Painting(Artwork):
        pass

    class CreationOfPhysicalObject(Document):
        object_created: PhysicalObject

    class CreationOfArtwork(CreationOfPhysicalObject):
        artwork_created: Annotated[
            Artwork,
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing(
                        "object_created", field_on_model=CreationOfPhysicalObject
                    )
                ]
            ),
        ]

    class CreationOfPainting(CreationOfArtwork):
        painting_created: Annotated[
            Painting,
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing(
                        "artwork_created", field_on_model=CreationOfArtwork
                    )
                ]
            ),
        ]

    class Commission(Document):
        thing: PhysicalObject
        works: Annotated[
            list[CreationOfPhysicalObject],
            RelationConfig(
                bind_to_child_field=[
                    FieldBinding(bound_field="thing", child_fields=["object_created"])
                ]
            ),
        ]

    initialise()
    return SimpleNamespace(
        Commission=Commission,
        CreationOfArtwork=CreationOfArtwork,
        CreationOfPainting=CreationOfPainting,
    )


def ref(type_name: str) -> dict:
    return {"type": type_name, "id": uuid7()}


def made(work) -> tuple[str, str]:
    """The type of a creation, and the type of what it made, by whichever field it has"""
    thing = next(
        getattr(work, name)
        for name in ("painting_created", "artwork_created", "object_created")
        if getattr(work, name, None) is not None
    )
    return work.type, thing.type


@no_type_check
def test_a_field_stands_for_all_the_fields_above_it_that_it_narrows():
    models = creation_models()
    assert names_stood_for(
        models.CreationOfPainting._meta.fields["painting_created"]
    ) == {"artwork_created", "object_created"}
    assert names_stood_for(
        models.CreationOfArtwork._meta.fields["artwork_created"]
    ) == {"object_created"}


@no_type_check
def test_a_binding_into_a_field_reaches_the_fields_that_stand_for_it_in_narrower_classes():
    models = creation_models()
    painting = ref("Painting")
    commission = models.Commission.Create(
        label="A commission",
        thing=painting,
        works=[
            {"type": "CreationOfPhysicalObject", "label": "Made"},
            {"type": "CreationOfArtwork", "label": "Made as art"},
            {"type": "CreationOfPainting", "label": "Painted"},
        ],
    )
    assert [made(work) for work in commission.works] == [
        ("CreationOfPhysicalObject", "Painting"),
        ("CreationOfArtwork", "Painting"),
        ("CreationOfPainting", "Painting"),
    ]
    assert commission.works[2].painting_created.id == painting["id"]


@no_type_check
def test_a_field_that_stands_for_a_bound_one_need_not_be_given():
    models = creation_models()
    # (inside a commission, the narrower field may be left out: the binding fills it, after the model is validated)
    for name in ("CreationOfArtwork", "CreationOfPainting"):
        commission = models.Commission.Create(
            label="A commission",
            thing=ref("Painting"),
            works=[{"type": name, "label": "Made"}],
        )
        assert made(commission.works[0]) == (name, "Painting")
    # (on its own, not inside a commission, it is required)
    with pytest.raises(ValidationError):
        models.CreationOfPainting.Create(label="Painted")


@no_type_check
def test_a_value_given_to_the_narrower_field_is_kept():
    models = creation_models()
    own = ref("Painting")
    commission = models.Commission.Create(
        label="A commission",
        thing=ref("Painting"),
        works=[
            {"type": "CreationOfPainting", "label": "Painted", "painting_created": own}
        ],
    )
    assert commission.works[0].painting_created.id == own["id"]


@no_type_check
def test_a_bound_value_the_narrower_field_cannot_hold_is_refused():
    models = creation_models()
    # (an artwork is not a painting: the painting created cannot be it)
    with pytest.raises(ValidationError) as raised:
        models.Commission.Create(
            label="A commission",
            thing=ref("Artwork"),
            works=[{"type": "CreationOfPainting", "label": "Painted"}],
        )
    assert "painting_created" in str(raised.value)
    # (it can be the artwork created)
    commission = models.Commission.Create(
        label="A commission",
        thing=ref("Artwork"),
        works=[{"type": "CreationOfArtwork", "label": "Made"}],
    )
    assert made(commission.works[0]) == ("CreationOfArtwork", "Artwork")


@no_type_check
def test_an_update_binds_into_the_narrower_field_too():
    models = creation_models()
    commission = models.Commission.Update(
        id=uuid7(),
        label="A commission",
        thing=ref("Painting"),
        works=[{"type": "CreationOfPainting", "label": "Painted"}],
    )
    assert made(commission.works[0]) == ("CreationOfPainting", "Painting")
