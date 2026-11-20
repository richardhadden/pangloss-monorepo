"""A field that names a wrapper takes the classes below it (implementation_docs/reified-relation-inheritance-plan.md):
which classes those are, and that the field is what the union written out was. With a database:
`conformance/test_wrapper_classes_below_live.py`"""

from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Conjunction,
    Document,
    Entity,
    ReifiedRelation,
    RelationConfig,
    SemanticSpace,
    initialise,
)
from pangloss_models.export import export_models
from pydantic import ValidationError

JOHN = "0194a1b2-0000-7000-8000-000000000001"


def names(model, field) -> set[str]:
    return {
        (getattr(option, "base_type", None) or option.annotated_type).__name__
        for option in model._meta.fields[field].type_options
    }


@no_type_check
def test_the_classes_below_at_any_depth_and_the_class_below_the_very_use():
    class Person(Entity):
        pass

    class Group(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class Finer[T](InRole[T]):
        fine: int = 0

    class Finest[T](Finer[T]):
        finest: int = 0

    class JohnRole(InRole[Person]):
        pass

    class Doc(Document):
        who: list[InRole[Person]]
        lower: list[Finer[Person]]
        either: list[InRole[Person | Group]]

    initialise(bind_database=False)
    assert names(Doc, "who") == {"InRole", "Finer", "Finest", "JohnRole"}
    # (a field takes what is below the class it names, not what is above or beside it)
    assert names(Doc, "lower") == {"Finer", "Finest"}
    # (`JohnRole` is below `InRole[Person]`, another use than `InRole[Person | Group]`)
    assert names(Doc, "either") == {"InRole", "Finer", "Finest"}

    made = Doc.Create(
        label="x",
        who=[
            {"type": "Finest", "finest": 2, "target": [{"type": "Person", "id": JOHN}]}
        ],
        lower=[],
        either=[{"type": "Finer", "target": [{"type": "Group", "id": JOHN}]}],
    )
    assert made.who[0].finest == 2
    with pytest.raises(ValidationError):
        Doc.Create(
            label="x",
            who=[],
            lower=[{"type": "InRole", "target": [{"type": "Person", "id": JOHN}]}],
            either=[],
        )


@no_type_check
def test_a_class_below_that_the_use_does_not_settle_is_not_taken():
    class Person(Entity):
        pass

    class Group(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        pass

    # (a parameter of its own, which `InRole[Person]` says nothing of)
    class Both[A, B](InRole[A]):
        other: list[B] = []

    # (below another use)
    class GroupRole(InRole[Group]):
        pass

    # (below a class with no parameters)
    class JohnRole(InRole[Person]):
        pass

    class Sub(JohnRole):
        pass

    class Doc(Document):
        who: list[InRole[Person]]
        # (each can still be named)
        named: list[InRole[Person] | Both[Person, Group] | GroupRole | Sub]

    initialise(bind_database=False)
    assert names(Doc, "who") == {"InRole", "JohnRole"}
    assert names(Doc, "named") == {"InRole", "JohnRole", "Both", "GroupRole", "Sub"}
    for other in ("Both", "GroupRole", "Sub"):
        with pytest.raises(ValidationError):
            Doc.Create(
                label="x",
                who=[{"type": other, "target": [{"type": "Person", "id": JOHN}]}],
                named=[],
            )


@no_type_check
def test_a_semantic_space_and_a_conjunction_likewise():
    class Person(Entity):
        pass

    class Negative[T](SemanticSpace[T]):
        pass

    class Strongly[T](Negative[T]):
        pass

    class Pair[T](Conjunction):
        items: list[T]

    class Ordered[T](Pair[T]):
        order: int = 0

    class Doc(Document):
        not_who: list[Negative[Person]]
        pairs: list[Pair[Person]]

    initialise(bind_database=False)
    assert names(Doc, "not_who") == {"Negative", "Strongly"}
    assert names(Doc, "pairs") == {"Pair", "Ordered"}


@no_type_check
def test_the_field_is_what_the_union_written_out_was():
    """(so what reads a field's options, the interface's forms among them, has nothing new to cope with)"""

    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class Finer[T](InRole[T]):
        fine: int = 0

    class Doc(Document):
        alone: list[InRole[Person]]
        written: list[InRole[Person] | Finer[Person]]
        # (the default of a new value may be the class above or one below)
        above: Annotated[
            list[InRole[Person]], RelationConfig(default_reified_type=InRole)
        ]
        below: Annotated[
            list[InRole[Person]], RelationConfig(default_reified_type=Finer)
        ]

    initialise(bind_database=False)
    assert (
        Doc._meta.fields["alone"].type_options
        == Doc._meta.fields["written"].type_options
    )
    fields = {
        field["name"]: field for field in export_models()["models"]["Doc"]["fields"]
    }

    def options(field):
        return sorted(fields[field]["options"], key=lambda option: option["type"])

    assert [option["type"] for option in options("alone")] == ["Finer", "InRole"]
    assert options("alone") == options("written")
    assert fields["above"]["defaultReifiedType"] == "InRole"
    assert fields["below"]["defaultReifiedType"] == "Finer"
