"""A unary semantic space (`SemanticSpaceMeta.is_unary`: a "not", a modality of not, or `unary=True`) holds one item
at most: its `contents` has `MaxLen(1)` in its field definition, so the generated models refuse a second item with a
message that says why, and the export gives the length as it does for a list annotated `MaxLen(1)`"""

from typing import Annotated, no_type_check
from uuid import uuid7

import pytest
from annotated_types import MaxLen, MinLen
from pangloss_models import (
    Document,
    Entity,
    Modal,
    PanglossModelError,
    SemanticSpace,
    export_models,
    initialise,
)
from pydantic import ValidationError
from pydantic_core import ErrorDetails

ID = "00000000-0000-0000-0000-000000000000"

NOT_REASON = "(it is unary: of two items under a 'not', neither is denied by itself)"
SET_REASON = "(it is declared unary=True)"


def person() -> dict:
    return {"type": "Person", "id": uuid7()}


def items(n: int) -> list[dict]:
    return [person() for _ in range(n)]


def refusal(make, n: int) -> ErrorDetails:
    with pytest.raises(ValidationError) as raised:
        make(items(n))
    (error,) = raised.value.errors()
    return error


def contents_validators(name: str) -> list[dict]:
    fields = {f["name"]: f for f in export_models()["models"][name]["fields"]}
    return fields["contents"]["validators"]


# --- the three ways to be unary -------------------------------------------------------------------------


@no_type_check
@pytest.mark.parametrize(
    "meta, reason",
    [
        (SemanticSpace.Meta(logical="not"), NOT_REASON),
        (
            SemanticSpace.Meta(logical=Modal("necessity", "command", of_not=True)),
            NOT_REASON,
        ),
        (SemanticSpace.Meta(unary=True), SET_REASON),
    ],
    ids=["not", "of_not", "unary"],
)
def test_one_item_is_taken_and_two_are_refused_by_why(meta, reason):
    class Person(Entity):
        pass

    class Only[T](SemanticSpace[T]):
        _meta = meta

    class Statement(Document):
        about: Only[Person]

    initialise(bind_database=False)

    def create(contents):
        return Statement.Create(label="S", about={"type": "Only", "contents": contents})

    def update(contents):
        return Statement.Update(
            id=ID, label="S", about={"type": "Only", "contents": contents}
        )

    for make in (create, update):
        make(items(1))
        error = refusal(make, 2)
        assert error["msg"] == f"Only holds one item only {reason}"
        assert error["type"] == "too_long"
        # (the path points at the contents, inside the document's field)
        assert error["loc"][0] == "about" and error["loc"][-1] == "contents"


@no_type_check
def test_none_is_taken_as_for_any_space():
    """The least is what it is for any `contents`: none (an empty list), and the field must be given"""

    class Person(Entity):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Maybe[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        denied: Not[Person]
        maybe: Maybe[Person]

    initialise(bind_database=False)
    Statement.Create(
        label="S",
        denied={"type": "Not", "contents": []},
        maybe={"type": "Maybe", "contents": []},
    )
    for which in ("denied", "maybe"):
        payload = {
            "denied": {"type": "Not", "contents": []},
            "maybe": {"type": "Maybe", "contents": []},
        }
        payload[which] = {"type": payload[which]["type"]}
        with pytest.raises(ValidationError) as raised:
            Statement.Create(label="S", **payload)
        assert raised.value.errors()[0]["type"] == "missing"


@no_type_check
def test_a_space_that_is_not_unary_takes_two():
    class Person(Entity):
        pass

    class Maybe[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))

    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "command"))

    class Statement(Document):
        maybe: Maybe[Person]
        ordered: Ordered[Person]

    initialise(bind_database=False)
    Statement.Create(
        label="S",
        maybe={"type": "Maybe", "contents": items(3)},
        ordered={"type": "Ordered", "contents": items(2)},
    )
    assert contents_validators("Maybe") == []
    assert contents_validators("Ordered") == []


# --- what is inherited ----------------------------------------------------------------------------------


@no_type_check
def test_a_subclass_inherits_the_limit_and_says_its_own_name():
    class Person(Entity):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Never[T](Not[T]):
        pass

    class Statement(Document):
        never: Never[Person]

    initialise(bind_database=False)

    def create(contents):
        return Statement.Create(
            label="S", never={"type": "Never", "contents": contents}
        )

    create(items(1))
    assert refusal(create, 2)["msg"] == f"Never holds one item only {NOT_REASON}"
    assert contents_validators("Never") == [{"name": "MaxLen", "max_length": 1}]


@no_type_check
def test_a_subclass_that_sets_unary_false_has_no_limit():
    class Person(Entity):
        pass

    class Single[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(unary=True)

    class Several[T](Single[T]):
        _meta = SemanticSpace.Meta(unary=False)

    class Statement(Document):
        single: Single[Person]
        several: Several[Person]

    initialise(bind_database=False)
    Statement.Create(
        label="S",
        single={"type": "Single", "contents": items(1)},
        several={"type": "Several", "contents": items(2)},
    )
    with pytest.raises(ValidationError, match=r"Single holds one item only"):
        Statement.Create(
            label="S",
            single={"type": "Single", "contents": items(2)},
            several={"type": "Several", "contents": items(2)},
        )
    assert contents_validators("Several") == []


@no_type_check
def test_a_concrete_subclass_has_the_limit_on_its_own_models():
    """A space of one type of contents, not generic (`class NotPerson(Not[Person])`), is made as any class is, and
    its models refuse two as well (and its database models)"""

    class Person(Entity):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class NotPerson(Not[Person]):
        pass

    class Statement(Document):
        denied: NotPerson

    initialise(bind_database=False)
    for kind in ("Create", "Update", "CreateDB", "UpdateDB"):
        model = getattr(NotPerson, kind)
        model(contents=items(1), **({"id": ID} if "Update" in kind else {}))
        with pytest.raises(ValidationError) as raised:
            model(contents=items(2), **({"id": ID} if "Update" in kind else {}))
        (error,) = raised.value.errors()
        assert error["msg"] == f"NotPerson holds one item only {NOT_REASON}"
        assert error["loc"] == ("contents",)


# --- nested ----------------------------------------------------------------------------------------------


@no_type_check
def test_a_space_inside_another_is_refused_where_it_is():
    class Person(Entity):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Maybe[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        maybe: Maybe[Not[Person]]

    initialise(bind_database=False)

    def create(contents):
        return Statement.Create(
            label="S",
            maybe={
                "type": "Maybe",
                "contents": [
                    {"type": "Not", "contents": items(1)},
                    {"type": "Not", "contents": contents},
                ],
            },
        )

    create(items(1))
    error = refusal(create, 2)
    assert error["msg"] == f"Not holds one item only {NOT_REASON}"
    assert error["loc"][:3] == ("maybe", "contents", 1)
    assert error["loc"][-1] == "contents"


# --- the class's own annotation ------------------------------------------------------------------------


@no_type_check
def test_a_larger_max_len_of_the_class_becomes_one():
    class Person(Entity):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")
        contents: Annotated[list[T], MaxLen(3)]

    class Statement(Document):
        denied: Not[Person]

    initialise(bind_database=False)

    def create(contents):
        return Statement.Create(label="S", denied={"type": "Not", "contents": contents})

    create(items(1))
    assert refusal(create, 2)["msg"] == f"Not holds one item only {NOT_REASON}"
    assert contents_validators("Not") == [{"name": "MaxLen", "max_length": 1}]


@no_type_check
def test_max_len_one_and_min_len_one_of_the_class_are_kept():
    class Person(Entity):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")
        contents: Annotated[list[T], MinLen(1), MaxLen(1)]

    class Statement(Document):
        denied: Not[Person]

    initialise(bind_database=False)

    def create(contents):
        return Statement.Create(label="S", denied={"type": "Not", "contents": contents})

    create(items(1))
    assert refusal(create, 0)["type"] == "too_short"
    assert refusal(create, 2)["msg"] == f"Not holds one item only {NOT_REASON}"
    assert contents_validators("Not") == [
        {"name": "MinLen", "min_length": 1},
        {"name": "MaxLen", "max_length": 1},
    ]


@no_type_check
def test_a_min_len_of_more_than_one_is_refused_at_initialise():
    class Person(Entity):
        pass

    class Neither[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(unary=True)
        contents: Annotated[list[T], MinLen(2)]

    class Statement(Document):
        neither: Neither[Person]

    with pytest.raises(PanglossModelError) as raised:
        initialise(bind_database=False)
    assert str(raised.value) == (
        f"Neither.contents: MinLen(2) asks for at least 2 items, but Neither holds one item only {SET_REASON}. "
        "Leave the MinLen out, or make it MinLen(1)"
    )


@no_type_check
def test_a_min_len_of_two_is_refused_for_an_inherited_not():
    class Person(Entity):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class NotBoth[T](Not[T]):
        contents: Annotated[list[T], MinLen(2)]

    with pytest.raises(PanglossModelError, match=r"^NotBoth.contents: MinLen\(2\)"):
        initialise(bind_database=False)


# --- the export ----------------------------------------------------------------------------------------


@no_type_check
def test_the_export_gives_the_length_as_for_an_annotated_list():
    class Person(Entity):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Statement(Document):
        denied: Not[Person]
        one: Annotated[list[Person], MaxLen(1)]

    initialise(bind_database=False)
    fields = {f["name"]: f for f in export_models()["models"]["Statement"]["fields"]}
    assert contents_validators("Not") == fields["one"]["validators"]
    assert contents_validators("Not") == [{"name": "MaxLen", "max_length": 1}]
