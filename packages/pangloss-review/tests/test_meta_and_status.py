"""The parts of review that need no database: the status, the meta slot, the setting, the commands' shape"""

from types import SimpleNamespace

import pytest
from pangloss_models import hooks
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_review import meta
from pangloss_review.cli import cli
from pangloss_review.config import allow_self_review
from pangloss_review.meta import ReviewMeta, is_reviewable, new_head_properties
from pangloss_review.status import ReviewStatus
from typer.testing import CliRunner


def test_only_a_checked_document_is_published():
    assert {s: s.published for s in ReviewStatus} == {
        ReviewStatus.UNCHECKED: False,
        ReviewStatus.ERRORS_FOUND: False,
        ReviewStatus.CHECKED: True,
    }
    assert [s.value for s in ReviewStatus] == ["unchecked", "errors_found", "checked"]


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
