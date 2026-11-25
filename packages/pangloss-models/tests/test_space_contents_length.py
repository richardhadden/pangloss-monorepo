"""The length of a semantic space's `contents` (`limit_contents`). Every space holds at least one item: its `contents`
has `MinLen(1)` in its field definition, so the generated models refuse an empty list with a message that says why.
A unary space (`SemanticSpaceMeta.is_unary`: a "not", a modality of not, or `unary=True`) holds one item at most as
well: `MaxLen(1)`, and a second item is refused with a message that says why. The export gives the lengths as it does
for a list annotated so"""

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


AT_LEAST_ONE = [{"name": "MinLen", "min_length": 1}]
ONE_ONLY = [{"name": "MinLen", "min_length": 1}, {"name": "MaxLen", "max_length": 1}]


def nothing(name: str) -> str:
    return f"{name} holds nothing: a semantic space has at least one item"


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
@pytest.mark.parametrize("kind", ["Create", "Update"])
def test_none_is_refused_for_any_space_by_why(kind):
    """An empty list is refused, of a unary space and of one that is not, with pydantic's error type `too_short`, at
    the contents inside the document's field"""

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
    model = getattr(Statement, kind)
    ids = {"id": ID} if kind == "Update" else {}

    def make(denied, maybe):
        return model(
            label="S",
            denied={"type": "Not", "contents": denied},
            maybe={"type": "Maybe", "contents": maybe},
            **ids,
        )

    make(items(1), items(1))
    for which, name, payload in (
        ("denied", "Not", (items(0), items(1))),
        ("maybe", "Maybe", (items(1), items(0))),
    ):
        with pytest.raises(ValidationError) as raised:
            make(*payload)
        (error,) = raised.value.errors()
        assert error["msg"] == nothing(name)
        assert error["type"] == "too_short"
        assert error["loc"][0] == which and error["loc"][-1] == "contents"


@no_type_check
def test_contents_left_out_is_missing():
    """The field must be given, as before: left out, it is `missing`, not refused as empty"""

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
    for which in ("denied", "maybe"):
        payload = {
            "denied": {"type": "Not", "contents": items(1)},
            "maybe": {"type": "Maybe", "contents": items(1)},
        }
        payload[which] = {"type": payload[which]["type"]}
        with pytest.raises(ValidationError) as raised:
            Statement.Create(label="S", **payload)
        (error,) = raised.value.errors()
        assert error["type"] == "missing"
        assert error["loc"][0] == which and error["loc"][-1] == "contents"


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
    assert contents_validators("Maybe") == AT_LEAST_ONE
    assert contents_validators("Ordered") == AT_LEAST_ONE


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
    assert refusal(create, 0)["msg"] == nothing("Never")
    assert contents_validators("Never") == ONE_ONLY


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
    assert contents_validators("Several") == AT_LEAST_ONE


@no_type_check
def test_a_concrete_subclass_has_the_limit_on_its_own_models():
    """A space of one type of contents, not generic (`class NotPerson(Not[Person])`), is made as any class is, and
    its models refuse none and two as well (and its database models)"""

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
        ids = {"id": ID} if "Update" in kind else {}
        model(contents=items(1), **ids)
        for n, message in (
            (0, nothing("NotPerson")),
            (2, f"NotPerson holds one item only {NOT_REASON}"),
        ):
            with pytest.raises(ValidationError) as raised:
                model(contents=items(n), **ids)
            (error,) = raised.value.errors()
            assert error["msg"] == message
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
    for n, message in (
        (0, nothing("Not")),
        (2, f"Not holds one item only {NOT_REASON}"),
    ):
        error = refusal(create, n)
        assert error["msg"] == message
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
    assert contents_validators("Not") == ONE_ONLY


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
    error = refusal(create, 0)
    assert (error["type"], error["msg"]) == ("too_short", nothing("Not"))
    assert refusal(create, 2)["msg"] == f"Not holds one item only {NOT_REASON}"
    assert contents_validators("Not") == ONE_ONLY


@no_type_check
@pytest.mark.parametrize("least", [1, 2])
def test_a_min_len_of_a_space_that_is_not_unary_is_kept_as_written(least):
    """A project's own `MinLen(1)` or `MinLen(2)` is kept (not doubled, not lowered); none is still refused with the
    space's own message, and one short of a larger least with pydantic's"""

    class Person(Entity):
        pass

    class Several[T](SemanticSpace[T]):
        contents: Annotated[list[T], MinLen(least)]

    class Statement(Document):
        several: Several[Person]

    initialise(bind_database=False)

    def create(contents):
        return Statement.Create(
            label="S", several={"type": "Several", "contents": contents}
        )

    create(items(least))
    assert contents_validators("Several") == [{"name": "MinLen", "min_length": least}]
    error = refusal(create, 0)
    assert (error["type"], error["msg"]) == ("too_short", nothing("Several"))
    if least > 1:
        error = refusal(create, least - 1)
        assert error["type"] == "too_short"
        assert error["ctx"]["min_length"] == least


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

    class Maybe[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        denied: Not[Person]
        maybe: Maybe[Person]
        one: Annotated[list[Person], MinLen(1), MaxLen(1)]
        some: Annotated[list[Person], MinLen(1)]

    initialise(bind_database=False)
    fields = {f["name"]: f for f in export_models()["models"]["Statement"]["fields"]}
    assert contents_validators("Not") == fields["one"]["validators"] == ONE_ONLY
    assert contents_validators("Maybe") == fields["some"]["validators"] == AT_LEAST_ONE
