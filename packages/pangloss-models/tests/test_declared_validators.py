"""`mode="after"` model validators a class declares are copied to the models that are written"""

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.embedded import Embedded
from pydantic import ValidationError, model_validator


def make_models():
    class Counted(Embedded):
        year: int
        double: int | None = None

        @model_validator(mode="after")
        def fill(self):
            self.double = self.year * 2
            return self

    class Counted2(Counted):
        extra: int = 0

    class Note(Document):
        when: Counted

    class Checked(Embedded):
        year: int

        @model_validator(mode="after")
        def positive(self):
            if self.year < 0:
                raise ValueError("year must not be negative")
            return self

    class Other(Document):
        when: Checked

    initialise()
    return Note, Other


def test_the_validator_runs_on_the_models_that_are_written_and_overwrites_what_a_client_sent():
    Note, _ = make_models()
    payload = {
        "label": "a",
        "when": {"type": "Counted2", "year": 2, "extra": 0, "double": 99},
    }
    assert Note.Create(**payload).when.double == 4
    update = Note.Update(**payload, id="00000000-0000-0000-0000-000000000000")
    assert update.when.double == 4
    created = Note.CreateDB.model_validate(
        {"label": "a", "when": {"type": "Counted", "year": 3}}
    )
    assert created.when.double == 6


def test_a_validator_that_refuses_refuses_the_whole_document():
    _, Other = make_models()
    Other.Create(label="a", when={"type": "Checked", "year": 1})
    with pytest.raises(ValidationError, match="must not be negative"):
        Other.Create(label="a", when={"type": "Checked", "year": -1})


def test_the_validators_of_pangloss_itself_are_not_copied_twice():
    Note, _ = make_models()
    # (a document with create_with_id keeps its one check that id and create_new go together)
    names = set(Note.Create.__pydantic_decorators__.model_validators)
    assert (
        "fill" not in names
    )  # the date's is on the date's model, not on the document's
