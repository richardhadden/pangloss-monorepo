"""`_vectors_meta` (implementation_docs/similarity-build-plan.md, step 2.2): inherited as the other slots are; a group
is a class that says `searchable=True` itself; refused on anything but a document or entity class. Which classes have
vectors (step 7a.3): `VECTORS_EXCLUDE`, the stand-ins and `VECTORS_INCLUDE`, in their order, checked at
`initialise()`, and the signature a part is stored with. No database."""

import typing
from typing import no_type_check

import pytest
from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_core.settings import configure
from pangloss_models import Document, Embedded, Entity, PanglossMetaError, initialise
from pangloss_models import ReifiedRelation, hooks
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_vectors import VectorsMeta
from pangloss_vectors.class_part import PART
from pangloss_vectors.meta import excluded, groups, groups_of, included, vectors_meta
from pangloss_vectors.store import part_signature


@no_type_check
def test_a_class_with_none_has_the_default_and_a_subclass_has_its_parent_s_unless_it_says():
    class Thing(Entity):
        pass

    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Saint(Person):
        pass

    class Ghost(Person):
        _vectors_meta = VectorsMeta(include=False)

    initialise()
    assert vectors_meta(Thing) == VectorsMeta(searchable=False, include=True)
    assert vectors_meta(Saint) == VectorsMeta(searchable=True)
    assert vectors_meta(Ghost) == VectorsMeta(searchable=False, include=False)


@no_type_check
def test_a_class_left_out_and_those_below_it_have_no_vectors():
    class Note(Document):
        _vectors_meta = VectorsMeta(include=False)

    class Margin(Note):
        pass

    class Letter(Document):
        pass

    initialise()
    assert not included("Note") and not included("Margin")
    assert included("Letter")
    # (a class that is no model's is the part's business)
    assert included("NoSuchClass")


@no_type_check
def test_a_group_is_a_class_that_says_searchable_itself_and_holds_the_classes_below_it():
    class Agent(Entity):
        pass

    class Person(Agent):
        _vectors_meta = VectorsMeta(searchable=True)

    class Saint(Person):
        pass

    class Martyr(Saint):
        _vectors_meta = VectorsMeta(searchable=True)

    class Hermit(Person):
        # (its own setting is not searchable: it is still in its parent's group)
        _vectors_meta = VectorsMeta(searchable=False)

    initialise()
    assert groups() == ["Martyr", "Person"]
    assert groups_of("Agent") == []
    assert groups_of("Person") == ["Person"]
    assert groups_of("Saint") == ["Person"]
    assert groups_of("Martyr") == ["Martyr", "Person"]
    assert groups_of("Hermit") == ["Person"]
    assert groups_of("NoSuchClass") == []


@no_type_check
def test_searchable_on_an_embedded_class_is_refused_at_initialise_by_name():
    class Dimensions(Embedded):
        _vectors_meta = VectorsMeta(searchable=True)
        width: int

    class Painting(Document):
        size: Dimensions

    with pytest.raises(PanglossMetaError, match="Dimensions: VectorsMeta"):
        initialise()


@no_type_check
def test_searchable_on_a_reified_relation_is_refused_at_initialise_by_name():
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        _vectors_meta = VectorsMeta(searchable=True)

    class Statement(Document):
        person: Identification[Person]

    with pytest.raises(PanglossMetaError, match="Identification: VectorsMeta"):
        initialise()


@no_type_check
def test_left_out_on_an_embedded_class_is_not_refused():
    class Dimensions(Embedded):
        _vectors_meta = VectorsMeta(include=False)
        width: int

    class Painting(Document):
        size: Dimensions

    initialise()


# ---------------------------------------------------------------------------
# Which classes have vectors: `VECTORS_EXCLUDE`, the stand-ins, `VECTORS_INCLUDE` (step 7a.3)
# ---------------------------------------------------------------------------


@pytest.fixture
def project(settings):
    """Makes settings of the project with `VECTORS_EXCLUDE` and `VECTORS_INCLUDE` (as importing a project's settings
    module does), and gives the tests' settings back after"""

    def make(exclude=None, include=None, installed=("pangloss_vectors",)):
        class Settings(BaseSettings):
            PROJECT_NAME: str = "Test"
            BACKEND_CORS_ORIGINS: list[typing.Any] = []
            INSTALLED_APPS: list[str] = list(installed)
            STORAGE: str | None = "pangloss_sdk.storage:api"
            DATABASE: DatabaseSettings = DatabaseSettings()
            AUTHJWT_SECRET_KEY: str = "asdf"
            ENTITY_BASE_URL: typing.Any = "http://test.com/"
            VECTORS_EXCLUDE: typing.Any = exclude
            VECTORS_INCLUDE: typing.Any = include

        return Settings()

    yield make
    configure(settings)


@pytest.fixture
def mention():
    """A stand-in of the test's own (`hooks.stand_ins`): the document `Mention`, which stands in for nothing here (a
    stand-in's document is all the rule looks at)"""
    stand_in = hooks.StandIn(document="Mention", stands_for=lambda model: False)
    hooks.stand_ins.append(stand_in)
    yield stand_in
    hooks.stand_ins.remove(stand_in)


@no_type_check
def mentions_and_notes():
    """`Note` above `Margin`; `Mention` (a stand-in, with `mention`) above `QuotedMention`; `Letter`; `Person`"""

    class Person(Entity):
        pass

    class Note(Document):
        pass

    class Margin(Note):
        pass

    class Mention(Document):
        pass

    class QuotedMention(Mention):
        pass

    class Letter(Document):
        pass

    class Dimensions(Embedded):
        width: int

    initialise()


def test_a_class_named_in_vectors_exclude_and_those_below_it_have_no_vectors(project):
    project(exclude=["Note"])
    mentions_and_notes()
    assert not included("Note") and not included("Margin")
    assert included("Letter") and included("Person")
    assert excluded() == ["Margin", "Note"]


def test_a_stand_in_s_document_and_those_below_it_have_no_vectors(project, mention):
    project()
    mentions_and_notes()
    assert not included("Mention") and not included("QuotedMention")
    assert included("Note") and included("Letter")
    assert excluded() == ["Mention", "QuotedMention"]


def test_vectors_include_gives_a_stand_in_its_vectors_back_and_a_subclass_named_only_its_own(
    project, mention
):
    project(include=["Mention"])
    mentions_and_notes()
    assert included("Mention") and included("QuotedMention")
    assert excluded() == []
    project(include=["QuotedMention"])
    assert not included("Mention") and included("QuotedMention")


def test_without_the_stand_in_registered_the_class_has_vectors(project):
    project()
    mentions_and_notes()
    assert included("Mention")
    assert excluded() == []


@no_type_check
def test_a_class_s_own_include_true_wins_over_the_stand_in_rule(project, mention):
    project()

    class Mention(Document):
        _vectors_meta = VectorsMeta(include=True)

    class QuotedMention(Mention):
        pass

    initialise()
    assert included("Mention") and included("QuotedMention")


@no_type_check
def test_a_class_s_own_include_false_wins_over_vectors_include(project, mention):
    project(include=["Mention"])

    class Mention(Document):
        _vectors_meta = VectorsMeta(include=False)

    initialise()
    assert not included("Mention")


@no_type_check
def test_vectors_exclude_wins_over_a_class_s_own_include_true(project):
    project(exclude=["Note"])

    class Note(Document):
        _vectors_meta = VectorsMeta(include=True)

    class Margin(Note):
        _vectors_meta = VectorsMeta(include=True)

    initialise()
    assert not included("Note") and not included("Margin")


def test_vectors_exclude_wins_over_vectors_include_of_a_subclass(project, mention):
    project(exclude=["Mention"], include=["QuotedMention"])
    mentions_and_notes()
    assert not included("Mention") and not included("QuotedMention")


def test_a_name_that_is_no_model_s_has_vectors_whatever_the_settings(project, mention):
    project(exclude=["Note"])
    mentions_and_notes()
    assert included("NoSuchClass")


@pytest.mark.parametrize("setting", ["VECTORS_EXCLUDE", "VECTORS_INCLUDE"])
def test_a_name_that_is_no_model_s_is_refused_at_initialise_by_name(project, setting):
    project(**{setting.removeprefix("VECTORS_").lower(): ["Nope"]})
    with pytest.raises(PanglossInitialisationError, match=f"{setting} names 'Nope'"):
        mentions_and_notes()


@pytest.mark.parametrize("setting", ["VECTORS_EXCLUDE", "VECTORS_INCLUDE"])
def test_a_class_that_is_not_one_of_documents_or_entities_is_refused_at_initialise(
    project, setting
):
    project(**{setting.removeprefix("VECTORS_").lower(): ["Dimensions"]})
    with pytest.raises(
        PanglossInitialisationError,
        match=f"{setting} names 'Dimensions', which is not a class of documents or entities",
    ):
        mentions_and_notes()


def test_a_class_named_in_both_settings_is_refused_at_initialise(project, mention):
    project(exclude=["Note", "Mention"], include=["Mention"])
    with pytest.raises(
        PanglossInitialisationError,
        match="'Mention' is named in both VECTORS_EXCLUDE and VECTORS_INCLUDE",
    ):
        mentions_and_notes()


@pytest.mark.parametrize("value", ["Note", {"Note"}, ["Note", 3], {"Note": True}])
@pytest.mark.parametrize("setting", ["VECTORS_EXCLUDE", "VECTORS_INCLUDE"])
def test_a_setting_that_is_not_a_list_of_names_is_refused(project, setting, value):
    project(**{setting.removeprefix("VECTORS_").lower(): value})
    with pytest.raises(PanglossInitialisationError, match=f"{setting} is a list"):
        mentions_and_notes()


def test_the_settings_are_not_checked_when_the_app_is_not_installed(project):
    project(exclude=["Nope"], installed=())
    mentions_and_notes()


def test_the_class_part_s_signature_is_its_own_while_nothing_is_excluded(project):
    project()
    mentions_and_notes()
    assert part_signature(PART) == PART.signature()
    # (a stand-in let in is not excluded either)
    project(include=["Mention"])
    assert part_signature(PART) == PART.signature()


def test_the_class_part_s_signature_changes_when_either_setting_changes_what_is_excluded(
    project, mention
):
    project(include=["Mention"])
    mentions_and_notes()
    nothing = part_signature(PART)
    assert nothing == PART.signature()
    project()
    stand_in = part_signature(PART)
    project(exclude=["Note"])
    notes_and_stand_in = part_signature(PART)
    project(exclude=["Note"], include=["Mention"])
    notes = part_signature(PART)
    assert len({nothing, stand_in, notes_and_stand_in, notes}) == 4
    # (the same classes excluded, said another way, is the same signature)
    project(exclude=["Note", "Margin"], include=["Mention"])
    assert part_signature(PART) == notes
