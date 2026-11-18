"""`@create_validator` and `@update_validator` are on the models written to the database (`CreateDB`, `UpdateDB`)
only; pydantic's validators are on `Create` and `Update` only, run once, and a `before` one is given snake_case keys.
(`@before_create` and `@before_update`, which a write runs: `pangloss_testing/conformance/test_write_checks_live.py`)"""

import asyncio
from typing import Annotated

import pytest
from pangloss_models import (
    DBField,
    Document,
    Embedded,
    Entity,
    PanglossWriteRefused,
    Trait,
    before_create,
    before_update,
    create_validator,
    initialise,
    update_validator,
)
from pangloss_models.write_checks import (
    check_before_create,
    check_before_update,
    marked,
    nodes_of,
)
from pydantic import model_validator

ID = "00000000-0000-0000-0000-000000000001"


def test_a_create_validator_is_on_create_db_and_an_update_validator_on_update_db():
    class Note(Document):
        text: str
        words: Annotated[int | None, DBField] = None
        seen_by: Annotated[str | None, DBField] = None

        @create_validator
        def count(self):
            self.words = len(self.text.split())

        @update_validator
        def recount(self):
            self.words = -len(self.text.split())

        @create_validator
        @update_validator
        def stamp(self):
            self.seen_by = type(self).__name__

    initialise()

    assert Note.Create(label="n", text="a b")._to_db_model().words == 2
    assert Note.Update(id=ID, label="n", text="a b c")._to_db_model().words == -3
    assert Note.Create(label="n", text="a")._to_db_model().seen_by == "NoteCreateDB"
    assert (
        Note.Update(id=ID, label="n", text="a")._to_db_model().seen_by == "NoteUpdateDB"
    )
    for kind in ("Create", "Update"):
        names = set(getattr(Note, kind).__pydantic_decorators__.model_validators)
        assert not names & {"count", "recount", "stamp"}, kind
    # (they are validators, not methods of the models)
    assert not hasattr(Note.HeadView, "count")


def test_they_are_inherited_and_a_subclass_replaces_one_by_its_name():
    class Counted(Trait):
        text: str
        words: Annotated[int | None, DBField] = None

        @create_validator
        def count(self):
            self.words = len(self.text.split())

    class Note(Document, Counted):
        pass

    class Doubled(Document, Counted):
        @create_validator
        def count(self):
            self.words = 2 * len(self.text.split())

    initialise()

    assert Note.Create(label="n", text="a b")._to_db_model().words == 2
    assert Doubled.Create(label="n", text="a b")._to_db_model().words == 4


def test_a_model_validator_runs_once_on_a_create_and_its_db_model():
    calls = []

    class Note(Document):
        text: str

        @model_validator(mode="after")
        def note(self):
            calls.append(type(self).__name__)
            return self

    initialise()

    Note.Create(label="n", text="a")._to_db_model()
    assert calls == ["NoteCreate"]


def test_a_before_validator_is_given_snake_case_keys():
    class Note(Document):
        born_in: str

        @model_validator(mode="before")
        @classmethod
        def shout(cls, data):
            data["born_in"] = data["born_in"].upper()
            return data

    initialise()

    assert Note.Create.model_validate({"label": "n", "bornIn": "x"}).born_in == "X"
    assert Note.Create.model_validate({"label": "n", "born_in": "y"}).born_in == "Y"


def test_before_create_and_before_update_must_be_async():
    with pytest.raises(
        TypeError,
        match=r"^@before_create is for an `async def` \(.*Note.check is not\): it may read the database$",
    ):

        class Note(Document):
            @before_create
            def check(self):
                pass

    with pytest.raises(TypeError, match=r"^@before_update is for an `async def`"):

        class Other(Document):
            @before_update
            def check(self, previous):
                pass


# --- `@before_create` and `@before_update`, with no database (found by mutation testing) ----------------------------------

OTHER = "00000000-0000-0000-0000-000000000002"
PERSON = "00000000-0000-0000-0000-000000000003"


def order_models(calls: list):
    """An order with nested actions (documents), a date (an embedded object) and a person (a reference); each class's
    checks note what they are given, and refuse a text "no" """

    class Person(Entity):
        pass

    class When(Embedded):
        year: int

        @before_create
        async def when_new(self):
            calls.append(("when_new", self.year))

    class Action(Document):
        text: str

        @before_create
        async def action_new(self):
            calls.append(("action_new", self.text))
            if self.text == "no":
                raise PanglossWriteRefused("not this", field="text")

        @before_update
        async def action_again(self, previous):
            calls.append(("action_again", self.text, previous.text))
            if self.text == "no":
                raise PanglossWriteRefused("not this either")

    class Order(Document):
        when: When
        thing: list[Action]
        by: list[Person]

        @before_create
        async def order_new(self):
            calls.append(("order_new", self.label))

        @before_update
        async def order_again(self, previous):
            calls.append(("order_again", self.label, previous.label))

    initialise()
    return Order, Action


def test_what_a_write_is_made_of_is_the_head_and_each_model_in_it_but_not_a_reference():
    Order, _ = order_models([])
    order = Order.Create(
        label="O",
        when={"type": "When", "year": 1500},
        thing=[
            {"type": "Action", "label": "a", "text": "x"},
            {"type": "Action", "label": "b", "text": "y"},
        ],
        by=[{"type": "Person", "id": PERSON}],
    )._to_db_model()
    found = nodes_of(order)
    assert [path for path, _ in found] == [(), ("when",), ("thing", 0), ("thing", 1)]
    assert [type(node).__name__ for _, node in found] == [
        "OrderCreateDB",
        "WhenCreateDB",
        "ActionCreateDB",
        "ActionCreateDB",
    ]
    assert found[0][1] is order


def test_the_checks_of_a_new_head_run_on_it_and_on_all_in_it_in_order():
    calls = []
    Order, _ = order_models(calls)
    order = Order.Create(
        label="O",
        when={"type": "When", "year": 1500},
        thing=[
            {"type": "Action", "label": "a", "text": "x"},
            {"type": "Action", "label": "b", "text": "y"},
        ],
        by=[],
    )._to_db_model()
    asyncio.run(check_before_create(order))
    assert calls == [
        ("order_new", "O"),
        ("when_new", 1500),
        ("action_new", "x"),
        ("action_new", "y"),
    ]


def test_a_refusal_says_where_in_the_write_it_is():
    calls = []
    Order, _ = order_models(calls)
    order = Order.Create(
        label="O",
        when={"type": "When", "year": 1500},
        thing=[
            {"type": "Action", "label": "a", "text": "x"},
            {"type": "Action", "label": "b", "text": "no"},
        ],
        by=[],
    )._to_db_model()
    with pytest.raises(PanglossWriteRefused, match="^not this$") as refused:
        asyncio.run(check_before_create(order))
    assert refused.value.path == ("thing", 1, "text")


def test_an_update_checks_what_was_there_against_itself_as_it_was_and_what_is_new_as_new():
    calls = []
    reads = []
    Order, _ = order_models(calls)

    def payload(texts, ids):
        return {
            "id": ID,
            "label": "O",
            "when": {"type": "When", "year": 1500},
            "thing": [
                {"type": "Action", "label": t, "text": t, **({"id": i} if i else {})}
                for t, i in zip(texts, ids, strict=True)
            ],
            "by": [],
        }

    previous = Order.Update(**payload(["was"], [OTHER]))._to_db_model()
    previous.label = "Before"

    async def read_previous():
        reads.append(1)
        return previous

    update = Order.Update(**payload(["now", "new"], [OTHER, None]))._to_db_model()
    asyncio.run(check_before_update(update, read_previous))
    # (the head is read once, for all the checks of what was there)
    assert reads == [1]
    assert calls == [
        ("order_again", "O", "Before"),
        ("when_new", 1500),
        ("action_again", "now", "was"),
        ("action_new", "new"),
    ]

    # one that the head does not have is not checked (the write refuses it)
    calls.clear()
    asyncio.run(check_before_update(update, _nothing))
    assert calls == [("when_new", 1500), ("action_new", "new")]

    with pytest.raises(PanglossWriteRefused, match="^not this either$") as refused:
        asyncio.run(
            check_before_update(
                Order.Update(**payload(["no"], [OTHER]))._to_db_model(), read_previous
            )
        )
    assert refused.value.path == ("thing", 0)
    with pytest.raises(PanglossWriteRefused, match="^not this$") as refused:
        asyncio.run(
            check_before_update(
                Order.Update(**payload(["now", "no"], [OTHER, None]))._to_db_model(),
                read_previous,
            )
        )
    assert refused.value.path == ("thing", 1, "text")


async def _nothing():
    return None


def test_an_update_with_nothing_to_check_does_not_read_the_head():
    class Plain(Document):
        pass

    initialise()

    async def read_previous():
        raise AssertionError("read")

    asyncio.run(
        check_before_update(
            Plain.Update(id=ID, label="P")._to_db_model(), read_previous
        )
    )


def test_a_check_is_replaced_by_a_method_of_its_name_in_a_subclass():
    class Base(Document):
        @before_create
        async def first(self):
            pass

        @before_create
        async def second(self):
            pass

    class Child(Base):
        def second(self):
            return "a method, not a check"

    initialise()
    assert list(marked(Base, "before_create")) == ["first", "second"]
    assert list(marked(Child, "before_create")) == ["first"]
