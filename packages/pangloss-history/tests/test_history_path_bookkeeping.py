"""Where a node is (implementation_docs/spaces-and-comparison-plan.md, step 1.2): a version written before the path
holds each nested node's `context_labels`, one written since its `context_path`. Both are what the graph works out
when it is written, not a change anyone made: neither is shown in the read form, nor counted as a difference, and an
old version is put back all the same."""

import json
import typing
from typing import no_type_check
from uuid import uuid7

import pytest
from history_support import record
from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_history import draft as draft_module
from pangloss_history.diff import diff
from pangloss_history.summary import field_changes
from pangloss_history.view import to_view
from pangloss_models import Document, ModelRegistry, SemanticSpace, initialise
from pydantic import AnyHttpUrl

HEAD, NEGATIVE, PART = "h1", "n1", "a1"

PATH = [
    {"kind": "document", "type": "Statement", "id": HEAD, "field": "parts"},
    {"kind": "space", "type": "Negative", "id": NEGATIVE, "field": "contents"},
]


def version(where: str) -> dict:
    """The write form of one statement, as a version written before the path (`labels`) or since (`path`) keeps it"""
    part = {"id": PART, "type": "Part", "label": "P", "text": "a"}
    space = {"id": NEGATIVE, "type": "Negative", "contents": [part]}
    if where == "labels":
        part["context_labels"] = [{"type": "Negative"}]
        space["context_labels"] = []
    else:
        part["context_path"] = PATH
        space["context_path"] = PATH[:1]
    return {
        "id": HEAD,
        "type": "Statement",
        "label": "S",
        "semantic_spaces": [],
        **({"context_labels": None} if where == "labels" else {"context_path": []}),
        "parts": [space],
    }


def test_neither_record_of_a_node_s_place_is_in_the_read_form():
    for where in ("labels", "path"):
        view = to_view(version(where), {}, set(), version(where))
        assert set(view) == {"id", "type", "label", "parts"}
        [space] = view["parts"]
        assert space == {
            "id": NEGATIVE,
            "type": "Negative",
            "contents": [{"id": PART, "type": "Part", "label": "P", "text": "a"}],
        }


def test_a_version_with_the_old_record_and_one_with_the_new_have_no_difference():
    assert diff(version("labels"), version("path")) == []
    assert diff(version("path"), version("labels")) == []
    assert field_changes(version("labels"), version("path")) == []


def test_a_change_beside_them_is_still_a_change():
    after = version("path")
    after["parts"][0]["contents"][0]["text"] = "b"
    changes = diff(version("labels"), after)
    assert [(c.path, c.kind) for c in changes] == [
        (f"parts[{NEGATIVE}].contents[{PART}].text", "changed")
    ]
    assert field_changes(version("labels"), after) == [
        {"key": "parts", "kind": "changed", "count": 1}
    ]


# --- putting an old version back: the draft ------------------------------------------------------------------------


@pytest.fixture
def statement_models():
    class Settings(BaseSettings):
        PROJECT_NAME: str = "Test"
        BACKEND_CORS_ORIGINS: list[typing.Any] = []
        INSTALLED_APPS: list[str] = []
        STORAGE: str | None = "pangloss_sdk.storage:api"
        DATABASE: DatabaseSettings = DatabaseSettings()
        INTERFACE_LANGUAGES: list[str] = []
        DEFAULT_INTERFACE_LANGUAGE: str = "en"
        AUTHJWT_SECRET_KEY: str = "asdf"
        ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("http://test.com/")

    Settings()
    ModelRegistry._reset()

    @no_type_check
    def declare():
        class Part(Document):
            text: str

        class Negative[T](SemanticSpace[T]):
            pass

        class Statement(Document):
            parts: list[Part | Negative[Part]]

        initialise()
        return Statement

    yield declare()
    ModelRegistry._reset()


def stored(where: str):
    """A version of a statement as the history keeps it, with real ids"""
    data = version(where)
    ids = {HEAD: str(uuid7()), NEGATIVE: str(uuid7()), PART: str(uuid7())}
    text = json.dumps(data)
    for old, new in ids.items():
        text = text.replace(f'"{old}"', f'"{new}"')
    return record(content=json.loads(text))


@pytest.mark.parametrize("where", ["labels", "path"])
def test_an_old_version_is_not_refused_for_either_record_of_a_node_s_place(
    statement_models, monkeypatch, where
):
    monkeypatch.setattr(draft_module, "installed_apps", lambda: ["letters"])
    monkeypatch.setattr(
        draft_module, "schema_position", lambda apps: {"letters": "0001_initial"}
    )
    draft = draft_module.make_draft(stored(where), statement_models)
    assert draft.problems == []
    assert not draft.upgraded
    # (what is put back is what a person wrote: the older record is taken out at every depth)
    assert "context_labels" not in json.dumps(draft.data)
    update = statement_models.Update.model_validate(draft.data)
    assert update.parts[0].contents[0].text == "a"
