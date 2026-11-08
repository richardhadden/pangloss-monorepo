"""A declared class is read as pydantic would read it: its defaults are carried, what it is annotated with is
applied, its validators run on what is written, and a key it has no field for is refused. What cannot be carried
(a method, a `model_config`) is said at `initialise()`, not found later."""

import datetime
import warnings
from typing import Annotated

import pytest
from annotated_types import Predicate
from pangloss_models import (
    Document,
    Embedded,
    Entity,
    PanglossModelError,
    PanglossModelWarning,
    Trait,
    export_models,
    initialise,
)
from pydantic import (
    AfterValidator,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)

# --- defaults ----------------------------------------------------------------------------------------


def test_the_default_a_class_declares_is_carried_to_the_generated_models():
    class Statement(Document):
        count: int = 0
        rank: int | None = 5
        tags: list[str] = []
        names: list[str] = Field(default_factory=list)
        note: str = Field(default="none", description="A note")

    initialise()

    made = Statement.Create(label="x")
    assert (made.count, made.rank, made.tags, made.names, made.note) == (
        0,
        5,
        [],
        [],
        "none",
    )
    # (a mutable default is not shared)
    made.tags.append("a")
    assert Statement.Create(label="x").tags == []
    # (the same on the models that are written and read)
    assert Statement.CreateDB(label="x").count == 0
    assert (
        Statement.Update(id="00000000-0000-0000-0000-000000000000", label="x").rank == 5
    )
    assert (
        Statement.View(id="00000000-0000-0000-0000-000000000000", label="x").note
        == "none"
    )
    # (a value given is taken)
    assert Statement.Create(label="x", count=3, rank=None, tags=["a"]).count == 3

    fields = {f["name"]: f for f in export_models()["models"]["Statement"]["fields"]}
    assert fields["count"]["required"] is False and fields["count"]["default"] == 0
    assert fields["rank"]["default"] == 5 and fields["rank"]["nullable"] is True
    assert fields["tags"]["default"] == [] and fields["names"]["default"] == []
    assert fields["note"]["default"] == "none"


def test_a_field_without_a_default_is_still_required():
    class Statement(Document):
        count: int
        tags: list[str]

    initialise()
    with pytest.raises(ValidationError, match="count"):
        Statement.Create(label="x", tags=[])
    with pytest.raises(ValidationError, match="tags"):
        Statement.Create(label="x", count=1)


# --- what a field is annotated with -------------------------------------------------------------------


def test_pydantic_constraints_and_validators_in_annotated_are_applied():
    class Statement(Document):
        # (pydantic checks the pattern on what was given, then changes the case)
        code: Annotated[str, StringConstraints(to_upper=True, pattern=r"^[a-z]+$")]
        even: Annotated[int, Predicate(lambda v: v % 2 == 0)]
        trimmed: Annotated[str, AfterValidator(str.strip)] | None = None
        matched: str = Field(pattern=r"^\d+$")

    initialise()
    made = Statement.Create(label="x", code="abc", even=2, trimmed="  a ", matched="12")
    assert made.code == "ABC" and made.trimmed == "a"
    for wrong in ({"code": "a1"}, {"even": 3}, {"matched": "x"}):
        with pytest.raises(ValidationError):
            Statement.Create(
                label="x", **{"code": "abc", "even": 2, "matched": "1", **wrong}
            )

    fields = {f["name"]: f for f in export_models()["models"]["Statement"]["fields"]}
    # (the interface sees the pattern; a function is named, not sent)
    assert {"name": "Constraints", "to_upper": True, "pattern": "^[a-z]+$"} in fields[
        "code"
    ]["validators"]
    assert fields["even"]["validators"] == [{"name": "Predicate"}]
    assert fields["trimmed"]["validators"] == [{"name": "AfterValidator"}]
    assert fields["matched"]["validators"] == [
        {"name": "Constraints", "pattern": "^\\d+$"}
    ]


def test_metadata_that_cannot_be_carried_is_an_error():
    class Marker:
        pass

    class Statement(Document):
        text: Annotated[str, Marker()]

    with pytest.raises(
        PanglossModelError, match="Statement.text is annotated with .*Marker"
    ):
        initialise()


def test_metadata_that_cannot_be_carried_on_a_relation_is_an_error_too():
    class Marker:
        pass

    class Person(Entity):
        pass

    class Statement(Document):
        about: Annotated[Person, Marker()]

    with pytest.raises(PanglossModelError, match="Statement.about is annotated with"):
        initialise()


# --- validators and methods ------------------------------------------------------------------------------


def test_field_validators_of_literal_fields_are_copied_to_the_models_that_are_written():
    class Named(Trait):
        name: str

        @field_validator("name")
        @classmethod
        def strip(cls, value: str) -> str:
            return value.strip()

    class Statement(Document, Named):
        tags: list[str]

        @field_validator("tags", mode="before")
        @classmethod
        def split(cls, value):
            return value.split(",") if isinstance(value, str) else value

        # (`label` is a field of the generated models, not of the class: pydantic must be told not to look)
        @field_validator("label", check_fields=False)
        @classmethod
        def no_empty_label(cls, value: str) -> str:
            if not value:
                raise ValueError("a label is needed")
            return value

    initialise()
    made = Statement.Create(label="x", name="  a ", tags="b,c")
    assert made.name == "a" and made.tags == ["b", "c"]
    assert Statement.CreateDB(label="x", name=" a", tags="b").name == "a"
    assert (
        Statement.Update(
            id="00000000-0000-0000-0000-000000000000", label="x", name=" a ", tags=[]
        ).name
        == "a"
    )
    with pytest.raises(ValidationError, match="a label is needed"):
        Statement.Create(label="", name="a", tags=[])
    # (not on what is read: the database holds what was written)
    assert (
        Statement.View(
            id="00000000-0000-0000-0000-000000000000", label="x", name=" a ", tags=[]
        ).name
        == " a "
    )


def test_model_validators_of_every_mode_are_copied():
    class Counted(Embedded):
        year: int
        double: int | None = None

        @model_validator(mode="before")
        @classmethod
        def from_text(cls, data):
            if isinstance(data, dict) and isinstance(data.get("year"), str):
                data = {**data, "year": int(data["year"].strip())}
            return data

        @model_validator(mode="after")
        def fill(self):
            self.double = self.year * 2
            return self

    class Note(Document):
        when: Counted

    initialise()
    made = Note.Create(label="x", when={"type": "Counted", "year": " 12 "})
    assert made.when.year == 12 and made.when.double == 24


def test_a_field_validator_of_a_relation_is_refused():
    class Person(Entity):
        pass

    class Statement(Document):
        about: Person

        @field_validator("about")
        @classmethod
        def check(cls, value):
            return value

    with pytest.raises(
        PanglossModelError, match="field_validator of 'about' cannot be carried"
    ):
        initialise()


def test_a_field_validator_of_a_field_that_does_not_exist_is_refused():
    class Statement(Document):
        text: str

        @field_validator("txet", check_fields=False)
        @classmethod
        def check(cls, value):
            return value

    with pytest.raises(PanglossModelError, match="'txet', which is not a field"):
        initialise()


def test_methods_properties_and_computed_fields_are_warned_about():
    class Person(Entity):
        first: str
        last: str

        def full_name(self) -> str:
            return f"{self.first} {self.last}"

        @property
        def initials(self) -> str:
            return self.first[0] + self.last[0]

        @computed_field
        @property
        def upper(self) -> str:
            return self.first.upper()

        @classmethod
        def kind(cls) -> str:  # (a classmethod is called on the class, which is there)
            return "person"

        @staticmethod
        def helper() -> int:
            return 1

    with pytest.warns(PanglossModelWarning) as caught:
        initialise()
    (message,) = [str(w.message) for w in caught if "Person declares" in str(w.message)]
    assert "the method 'full_name'" in message
    assert "the property 'initials'" in message
    assert "the computed field 'upper'" in message
    assert "kind" not in message and "helper" not in message
    assert not hasattr(Person.Create(label="x", first="a", last="b"), "full_name")


def test_a_model_config_of_the_class_is_warned_about():
    class Person(Entity):
        model_config = ConfigDict(frozen=True)
        name: str

    with pytest.warns(PanglossModelWarning, match="model_config of its own"):
        initialise()


def test_a_plain_class_warns_of_nothing():
    class Person(Entity):
        name: str
        born: datetime.date | None = None

        @model_validator(mode="after")
        def check(self):
            return self

    class Statement(Document):
        about: Person

    with warnings.catch_warnings():
        warnings.simplefilter("error", PanglossModelWarning)
        initialise()


# --- keys the models have no field for ------------------------------------------------------------------


def test_a_key_the_model_has_no_field_for_is_refused_on_create_and_update():
    class Person(Entity):
        pass

    class Statement(Document):
        text: str
        about: Person

    initialise()
    good = dict(
        label="x",
        text="t",
        about={"type": "Person", "id": "00000000-0000-0000-0000-000000000001"},
    )
    Statement.Create(**good)
    # (by the Python name and by the JSON name)
    Statement.Create(**{**good, "text": "t"})
    Statement.Create.model_validate({**good, "text": "t"})
    with pytest.raises(ValidationError, match="txet"):
        Statement.Create(**good, txet="typo")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Statement.Update.model_validate(
            {**good, "id": "00000000-0000-0000-0000-000000000000", "txet": "typo"}
        )
    # (a key of a nested model too)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Statement.Create(
            **{
                **good,
                "about": {"type": "Person", "id": good["about"]["id"], "lable": "x"},
            }
        )
    # (the models the database is written from and read into are not: they carry what the database has)
    Statement.CreateDB(**good, extra="kept")  # type: ignore[call-arg]
    Statement.View(
        id="00000000-0000-0000-0000-000000000000",
        label="x",
        text="t",
        about={"type": "Person", "id": good["about"]["id"], "label": "P"},
        extra="kept",
    )
