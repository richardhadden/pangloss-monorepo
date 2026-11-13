"""The parts of review that need no database: the status, the meta slot, the setting, the commands' shape"""

from types import SimpleNamespace

import pytest
from pangloss_models import Document, Entity, hooks
from pangloss_review import ReviewMeta, ReviewStatus, is_reviewable, meta
from pangloss_review.cli import cli
from pangloss_review.config import allow_self_review
from pangloss_review.meta import new_head_properties
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def fresh_registry():
    """(What a test declares is not left for the next, or for a test of another package that the same worker runs)"""
    from pangloss_core import ClientSettings
    from pangloss_core import settings as core_settings
    from pangloss_models import ModelRegistry

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


def test_only_a_checked_document_is_published():
    assert {s: s.published for s in ReviewStatus} == {
        ReviewStatus.UNCHECKED: False,
        ReviewStatus.ERRORS_FOUND: False,
        ReviewStatus.PUBLISHED: True,
    }
    assert [s.value for s in ReviewStatus] == ["unchecked", "errors_found", "published"]


def test_a_class_is_reviewed_only_when_it_says_so_and_a_subclass_inherits():
    class Plain(Document):
        title: str

    class Letter(Document):
        _review_meta = ReviewMeta(reviewable=True)
        title: str

    class Postcard(Letter):
        pass

    class Opted(Letter):
        _review_meta = ReviewMeta(reviewable=False)

    assert not is_reviewable(Plain)
    assert is_reviewable(Letter)
    assert is_reviewable(Postcard)
    assert not is_reviewable(Opted)


def test_entities_are_not_reviewed():
    class Person(Entity):
        name: str

    assert not is_reviewable(Person)
    assert new_head_properties(Person) == {}


def test_a_new_reviewed_document_is_written_unpublished_and_unchecked():
    class Letter(Document):
        _review_meta = ReviewMeta(reviewable=True)
        title: str

    class Plain(Document):
        title: str

    assert new_head_properties(Letter) == {
        "published": False,
        "review_status": "unchecked",
    }
    assert new_head_properties(Plain) == {}


def test_the_hook_is_installed_once_on_import():
    meta.install()
    meta.install()
    assert hooks.new_head_properties.count(new_head_properties) == 1


def test_self_review_is_allowed_unless_the_setting_says_not():
    assert allow_self_review(SimpleNamespace()) is True
    assert allow_self_review(SimpleNamespace(REVIEW_ALLOW_SELF_REVIEW=True)) is True
    assert allow_self_review(SimpleNamespace(REVIEW_ALLOW_SELF_REVIEW=False)) is False


@pytest.mark.parametrize("command", ["queue", "show", "set"])
def test_the_commands_are_there_and_have_help(command):
    result = CliRunner().invoke(cli, [command, "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_set_refuses_a_status_that_does_not_exist():
    result = CliRunner().invoke(
        cli, ["set", "7bd4b1c2-0c3e-4a56-9a39-6e0d6d1d9c11", "published", "-u", "x"]
    )
    assert result.exit_code != 0


def test_the_reviewed_classes_are_listed_by_name():
    from pangloss_review.service import reviewable_types

    class Unreviewed(Document):
        title: str

    class Dossier(Document):
        _review_meta = ReviewMeta(reviewable=True)
        title: str

    class SubDossier(Dossier):
        pass

    found = reviewable_types()
    assert {"Dossier", "SubDossier"} <= set(found)
    assert "Unreviewed" not in found
    assert found == sorted(found)


def test_the_interface_has_a_link_to_the_queue_for_someone_logged_in_and_no_list_of_unreconciled():
    from pangloss_interface import NavLink, NavModel
    from pangloss_review.interface_config import config

    assert config.nav == [
        NavLink("Review", href="/review", requires_login=True),
        NavModel("Unreconciled", hidden=True),
    ]


# --- unreconciled mentions ---------------------------------------------------------------------------------------


def unreconciled_model():
    # (the registry is reset before each test, and a module is only run once: declared again)
    import importlib

    import pangloss_review.models

    importlib.reload(pangloss_review.models)
    return pangloss_review.models.Unreconciled


def test_a_relation_to_a_class_that_allows_it_takes_an_unreconciled_mention():
    from typing import Annotated

    from pangloss_models import initialise
    from pangloss_models.field_definitions import RelationToDocument
    from pangloss_review import NoUnreconciled
    from pydantic import ValidationError

    Unreconciled = unreconciled_model()

    class Person(Entity):
        _review_meta = ReviewMeta(allow_unreconciled=True)

    class Monk(Person):  # (inherits that it may be)
        pass

    class Place(Entity):
        pass

    class Statement(Document):
        person: Person
        place: Place
        certain: Annotated[Person, NoUnreconciled()] | None = None

    initialise()

    def stands_in(field: str) -> list[str]:
        return sorted(
            name
            for option in Statement._meta.fields[field].type_options
            if isinstance(option, RelationToDocument)
            for name in option.stands_in_for
        )

    assert stands_in("person") == ["Monk", "Person"]
    assert stands_in("place") == [] and stands_in("certain") == []

    place = {"type": "Place", "id": "01a1c564-7def-70f0-bd21-410a35c82ab1"}
    made = Statement.Create(
        label="S",
        place=place,
        person={
            "type": "Unreconciled",
            "label": "Brother  ÉTIENNE.",
            "unreconciled_type": "Monk",
            "uris": ["http://example.org/e"],
        },
    )
    assert isinstance(made.person, Unreconciled.Create)
    # (the label folded, for comparing: only on what is written to the database)
    assert made._to_db_model().person.label_key == "brother etienne"
    with pytest.raises(ValidationError, match="stands for Monk or Person, not 'Place'"):
        Statement.Create(
            label="S",
            place=place,
            person={"type": "Unreconciled", "label": "X", "unreconciled_type": "Place"},
        )


def test_on_a_server_a_class_that_allows_it_needs_review_installed():
    from pangloss_core import BaseSettings
    from pangloss_core import settings as core_settings
    from pangloss_models import PanglossModelError, initialise

    # (a server's settings, in place of the client's of the fixture, which puts back what was there)
    core_settings.SETTINGS = BaseSettings.model_construct(
        INSTALLED_APPS=["app"], STORAGE="pangloss_sdk.storage:api", MODEL_SETTINGS={}
    )

    class Person(Entity):
        _review_meta = ReviewMeta(allow_unreconciled=True)

    with pytest.raises(
        PanglossModelError, match="add 'pangloss_review' to INSTALLED_APPS"
    ):
        initialise()


def test_a_client_of_the_api_gets_the_model_without_asking(monkeypatch):
    """(the SDK of a project: its models say `ReviewMeta`, and nothing there imports `pangloss_review.models`)"""
    import sys

    from pangloss_models import ModelRegistry, initialise

    # (as in a process that has not imported it)
    monkeypatch.delitem(sys.modules, "pangloss_review.models", raising=False)

    class Person(Entity):
        _review_meta = ReviewMeta(allow_unreconciled=True)

    class Hearing(Document):
        witness: Person

    initialise()
    assert "Unreconciled" in ModelRegistry._model_dict
    made = Hearing.Create(
        label="A hearing",
        witness={"type": "Unreconciled", "unreconciled_type": "Person", "label": "J."},
    )
    assert made.witness.type == "Unreconciled"


def test_labels_are_folded_for_comparing():
    from pangloss_review.models import label_key
    from pangloss_review.reconcile import likeness

    assert label_key("  JOHN   Smíth. ") == "john smith"
    assert label_key("Müller, ") == "muller"
    assert likeness("john smith", "john smith") == 1.0
    assert likeness("john smith", "jon smith") > 0.9
    assert likeness("john smith", "j. smith") >= 0.75
    assert likeness("john smith", "mary smith") < 0.75


def test_a_part_of_what_is_written_is_replaced_by_its_id():
    from pangloss_review.reconcile import replaced

    data = {
        "id": "h",
        "statements": [
            {"id": "a", "by": [{"id": "x", "label": "J"}, {"id": "y"}]},
            {"id": "b", "by": []},
        ],
    }
    changed, found = replaced(data, "x", lambda part: {"was": part["label"]})
    assert found
    assert changed["statements"][0]["by"] == [{"was": "J"}, {"id": "y"}]
    assert data["statements"][0]["by"][0] == {"id": "x", "label": "J"}
    assert replaced(data, "nowhere", lambda part: part) == (data, False)
