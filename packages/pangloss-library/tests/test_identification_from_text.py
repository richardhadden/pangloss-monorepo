"""Identifications that keep what the source wrote (`IdentificationFromText`, `IdentificationByToolchainFromText`), and
the checks at `initialise()` that a class of suggestion can become the class it names"""

import importlib
import warnings
from uuid import uuid7

import pytest
from pangloss_core import ClientSettings
from pangloss_core import settings as core_settings
from pangloss_models import (
    Document,
    Entity,
    ModelRegistry,
    PanglossModelError,
    PanglossModelWarning,
    initialise,
)


@pytest.fixture(autouse=True)
def clear_registry():
    # (models initialised with a database module that needs no database)
    saved = core_settings.__dict__.get("SETTINGS")
    ClientSettings(INSTALLED_APPS=[], STORAGE="pangloss_sdk.storage:api")
    ModelRegistry._reset()
    yield
    ModelRegistry._reset()
    if saved is None:
        core_settings.__dict__.pop("SETTINGS", None)
    else:
        core_settings.SETTINGS = saved


def library():
    # (the registry was reset, and a module is only run once)
    import pangloss_library.models

    return importlib.reload(pangloss_library.models)


def initialised() -> list[warnings.WarningMessage]:
    """`initialise()`, and the warnings of the models it gave"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", PanglossModelWarning)
        initialise()
    return [w for w in caught if issubclass(w.category, PanglossModelWarning)]


def test_the_two_classes_are_generated_and_keep_the_text():
    lib = library()

    class Person(Entity):
        pass

    class Statement(Document):
        by: lib.Identification[Person]  # ty: ignore[invalid-type-form]

    assert not initialised()
    john = {"type": "Person", "id": uuid7()}
    made = Statement.Create(
        label="S",
        by={"type": "IdentificationFromText", "text": "Jon", "target": [john]},
    )
    assert (made.by.type, made.by.text) == ("IdentificationFromText", "Jon")
    suggested = Statement.Create(
        label="S",
        by={
            "type": "IdentificationByToolchainFromText",
            "text": "Jon",
            "target": [john],
            "identified_by": "extractor",
        },
    )
    assert (suggested.by.type, suggested.by.text) == (
        "IdentificationByToolchainFromText",
        "Jon",
    )
    view = lib.IdentificationByToolchainFromText.View
    assert view.model_fields["text"].annotation is str
    assert lib.IdentificationFromText.View.model_fields["text"].annotation is str
    # (the text is needed)
    with pytest.raises(ValueError, match="text"):
        Statement.Create(
            label="S", by={"type": "IdentificationFromText", "target": [john]}
        )

    # confirmed, a suggestion with text becomes an identification with text
    assert (
        lib.confirmed_class_name(lib.IdentificationByToolchainFromText)
        == "IdentificationFromText"
    )
    # (each class of suggestion is read by its own label)
    from pangloss_models.indexes import indexed_classes

    assert {"IdentificationByToolchain", "IdentificationByToolchainFromText"} <= {
        model.__name__ for model in indexed_classes()
    }

    # the text of a suggestion is not changed in a form (the module shows it); a person's is a field of it
    from pangloss_interface.meta import export_definitions

    models = export_definitions()["models"]
    hidden = models["IdentificationByToolchainFromText"]["interfaceMeta"]["hideOnForms"]
    assert "text" in hidden
    assert (
        "text" not in models["IdentificationFromText"]["interfaceMeta"]["hideOnForms"]
    )


def test_a_confirmed_class_that_needs_a_field_the_suggestion_lacks_is_refused():
    lib = library()

    class Reading[T](lib.Identification[T]):
        folio: str

    class SuggestedReading[T](lib.IdentificationByToolchain[T]):
        confirmed_as = Reading

    with pytest.raises(
        PanglossModelError,
        match=r"SuggestedReading: a confirmed SuggestedReading becomes a Reading, whose field 'folio' has no "
        r"default and is not a field of SuggestedReading .*give SuggestedReading the field 'folio', or give "
        r"Reading.folio a default",
    ):
        initialise()


def test_a_field_the_two_type_differently_is_refused():
    lib = library()

    class Reading[T](lib.Identification[T]):
        note: str | None = None

    class SuggestedReading[T](lib.IdentificationByToolchain[T]):
        confirmed_as = Reading
        note: int | None = None

    with pytest.raises(
        PanglossModelError,
        match=r"SuggestedReading: the field 'note' is `int \| None` in SuggestedReading and `str \| None` in "
        r"Reading, .*declare 'note' with the same type in both",
    ):
        initialise()


def test_a_field_with_a_default_that_the_suggestion_lacks_is_accepted():
    lib = library()

    class Person(Entity):
        pass

    class Reading[T](lib.Identification[T]):
        folio: str | None = None
        checked: bool = False

    class SuggestedReading[T](lib.IdentificationByToolchain[T]):
        confirmed_as = Reading
        # (of the suggestion only: not kept, and not compared)
        model: int | None = None

    class Statement(Document):
        by: Reading[Person] | SuggestedReading[Person]  # ty: ignore[invalid-type-form]

    assert not initialised()
    assert lib.confirmed_class_name(SuggestedReading) == "Reading"


def test_a_field_that_takes_a_suggestion_and_not_what_it_becomes_is_warned_of_once():
    lib = library()

    class Person(Entity):
        pass

    class Statement(Document):
        only_suggested: lib.IdentificationByToolchain[Person]  # ty: ignore[invalid-type-form]
        both: Person | lib.Identification[Person]  # ty: ignore[invalid-type-form]
        # (the two that keep the text: what it becomes is taken)
        from_text: (
            lib.IdentificationFromText[Person]  # ty: ignore[invalid-type-form]
            | lib.IdentificationByToolchainFromText[Person]  # ty: ignore[invalid-type-form]
        )

    class Longer(Statement):
        pass

    caught = initialised()
    assert len(caught) == 1, [str(w.message) for w in caught]
    warning = caught[0].message
    assert isinstance(warning, PanglossModelWarning)
    assert str(warning) == (
        "Statement.only_suggested takes a suggestion that it does not take once it is confirmed "
        "(IdentificationByToolchain becomes Identification; IdentificationByToolchainFromText becomes "
        "IdentificationFromText): confirming one would be refused. Add Identification to what 'only_suggested' "
        "takes"
    )
    # (at the field, for the language server)
    assert (warning.model, warning.member) == (Statement, "only_suggested")


def test_a_suggestion_inside_a_wrapper_is_checked_where_it_is():
    lib = library()

    class Person(Entity):
        pass

    class Statement(Document):
        suspect: lib.WeightedAlternative[  # ty: ignore[invalid-type-form]
            lib.IdentificationByToolchainFromText[Person]  # ty: ignore[invalid-type-form]
        ]

    (caught,) = initialised()
    assert "Add IdentificationFromText to what 'suspect' takes" in str(caught.message)
