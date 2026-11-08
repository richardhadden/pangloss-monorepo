"""`@create_validator` and `@update_validator` are on the models written to the database (`CreateDB`, `UpdateDB`)
only; pydantic's validators are on `Create` and `Update` only, run once, and a `before` one is given snake_case keys.
(`@before_create` and `@before_update`, which a write runs: `pangloss_testing/conformance/test_write_checks_live.py`)"""

from typing import Annotated

import pytest
from pangloss_models import (
    DBField,
    Document,
    Trait,
    before_create,
    create_validator,
    initialise,
    update_validator,
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


def test_before_create_must_be_async():
    with pytest.raises(TypeError, match="is for an `async def`"):

        class Note(Document):
            @before_create
            def check(self):
                pass
