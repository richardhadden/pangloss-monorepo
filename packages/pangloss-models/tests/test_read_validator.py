"""`@read_validator`: what a class says of a read of it, run on the data its `View` is made from (`write_checks`);
and `classes_stood_for`, what a generic's type variable stands for in the use a generated model was made for."""

from typing import Any

from pangloss_models import (
    Document,
    Entity,
    ReifiedRelation,
    SemanticSpace,
    classes_stood_for,
    initialise,
    read_validator,
)
from pangloss_users import see_unpublished

ID = "01a1c564-7def-70f0-bd21-410a35c82ab1"
OTHER = "01a1c564-7def-70f0-bd21-410a35c82ab2"


def models():
    calls: list[str] = []

    class Person(Entity):
        nickname: str | None = None

        @read_validator
        def shout(cls, data: dict[str, Any]) -> dict[str, Any]:
            calls.append("Person")
            return {**data, "label": str(data.get("label", "")).upper()}

    class Counted[T](ReifiedRelation[T]):
        shown: int = 0
        kept: int = 0

        @read_validator
        def the_readers_own(cls, data: dict[str, Any]) -> dict[str, Any]:
            calls.append("Counted")
            if not see_unpublished.get():
                return {**data, "shown": data.get("kept", 0)}
            return data

    class Statement(Document):
        text: str
        about: list[Counted[Person]]

        @read_validator
        def trim(cls, data: dict[str, Any]) -> dict[str, Any]:
            calls.append("Statement")
            return {**data, "text": str(data.get("text", "")).strip()}

    initialise()
    return Person, Counted, Statement, calls


def stored() -> dict[str, Any]:
    return {
        "id": ID,
        "type": "Statement",
        "label": "S",
        "text": "  a text  ",
        "about": [
            {"type": "Counted", "id": OTHER, "shown": 5, "kept": 2, "target": []}
        ],
    }


def test_it_runs_on_what_a_view_is_made_from():
    Person, Counted, Statement, calls = models()

    view = Statement.View(**stored())

    assert view.text == "a text"
    assert calls.count("Statement") == 1 and calls.count("Counted") == 1


def test_it_runs_for_the_head_view_too_and_for_a_use_of_a_generic():
    Person, Counted, Statement, calls = models()

    head = Statement.HeadView(
        **stored(),
        meta={
            "created_when": "2026-11-19T10:00:00Z",
            "updated_by": None,
            "updated_when": None,
        },
    )

    assert head.text == "a text" and head.about[0].shown == 5
    token = see_unpublished.set(False)
    try:
        assert Statement.View(**stored()).about[0].shown == 2
    finally:
        see_unpublished.reset(token)


def test_it_does_not_run_on_what_is_written():
    Person, Counted, Statement, calls = models()

    made = Statement.Create(
        label="S",
        text="  kept as given  ",
        about=[{"type": "Counted", "shown": 9, "kept": 1, "target": []}],
    )

    assert made.text == "  kept as given  " and made.about[0].shown == 9
    assert made._to_db_model().text == "  kept as given  "
    assert calls == []


def test_it_is_not_a_method_of_the_generated_models():
    Person, Counted, Statement, calls = models()

    assert not hasattr(Statement.Create, "trim")
    assert not hasattr(
        Statement.HeadView(
            **stored(),
            meta={
                "created_when": "2026-11-19T10:00:00Z",
                "updated_by": None,
                "updated_when": None,
            },
        ),
        "the_readers_own",
    )


def test_a_view_made_from_a_view_is_left_as_it_is():
    Person, Counted, Statement, calls = models()
    view = Statement.View(**stored())
    calls.clear()

    again = Statement.View.model_validate(view)

    assert again.text == "a text" and "Statement" not in calls


def test_it_is_inherited_and_replaced_by_one_of_the_same_name():
    class Base(Document):
        _meta = Document.Meta(abstract=True)
        text: str

        @read_validator
        def tidy(cls, data: dict[str, Any]) -> dict[str, Any]:
            return {**data, "text": data["text"].strip()}

    class Kept(Base):
        pass

    class Loud(Base):
        @read_validator
        def tidy(cls, data: dict[str, Any]) -> dict[str, Any]:
            return {**data, "text": data["text"].upper()}

    initialise()

    assert Kept.View(id=ID, type="Kept", label="K", text=" a ").text == "a"
    assert Loud.View(id=ID, type="Loud", label="L", text=" a ").text == " A "


# --- what a generic stands for ----------------------------------------------------------------------------------------


def test_the_models_of_a_use_of_a_generic_know_what_its_variable_stands_for():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Doubt[T](SemanticSpace[T]):
        pass

    class Proxy[T](ReifiedRelation[T]):
        pass

    class Statement(Document):
        about: list[Proxy[Person]]
        where: list[Proxy[Place | Doubt[Person]]]

    initialise()
    made = Statement.Create(
        label="S",
        about=[{"type": "Proxy", "target": [{"type": "Person", "id": ID}]}],
        where=[{"type": "Proxy", "target": [{"type": "Place", "id": OTHER}]}],
    )

    assert classes_stood_for(made.about[0]) == [Person]
    assert sorted(c.__name__ for c in classes_stood_for(made.where[0]) or []) == [
        "Person",
        "Place",
    ]
    written = made._to_db_model()
    assert classes_stood_for(written.about[0]) == [Person]
    read = Statement.View(
        id=ID,
        type="Statement",
        label="S",
        about=[{"type": "Proxy", "id": OTHER, "target": []}],
        where=[],
    )
    assert classes_stood_for(read.about[0]) == [Person]
    assert classes_stood_for(made) is None and classes_stood_for(Proxy.Create) is None
    assert classes_stood_for(made.about[0], "Other") is None
