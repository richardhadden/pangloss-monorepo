"""Where a node is (implementation_docs/spaces-and-comparison-plan.md, step 1.2): a version holds each nested node's
`context_path`. It is what the graph works out when it is written, not a change anyone made: it is not shown in the
read form, nor counted as a difference, and a version holding it is put back all the same."""

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


def version(with_path: bool = True) -> dict:
    """The write form of one statement, as a version keeps it: with the `context_path` of each node, or without"""
    part = {"id": PART, "type": "Part", "label": "P", "text": "a"}
    space = {"id": NEGATIVE, "type": "Negative", "contents": [part]}
    if with_path:
        part["context_path"] = PATH
        space["context_path"] = PATH[:1]
    return {
        "id": HEAD,
        "type": "Statement",
        "label": "S",
        "semantic_spaces": [],
        **({"context_path": []} if with_path else {}),
        "parts": [space],
    }


def test_the_record_of_a_node_s_place_is_not_in_the_read_form():
    view = to_view(version(), {}, set(), version())
    assert set(view) == {"id", "type", "label", "parts"}
    [space] = view["parts"]
    assert space == {
        "id": NEGATIVE,
        "type": "Negative",
        "contents": [{"id": PART, "type": "Part", "label": "P", "text": "a"}],
    }


def test_a_version_with_the_path_and_one_without_have_no_difference():
    assert diff(version(False), version()) == []
    assert diff(version(), version(False)) == []
    assert field_changes(version(False), version()) == []


def test_a_change_beside_it_is_still_a_change():
    after = version()
    after["parts"][0]["contents"][0]["text"] = "b"
    changes = diff(version(False), after)
    assert [(c.path, c.kind) for c in changes] == [
        (f"parts[{NEGATIVE}].contents[{PART}].text", "changed")
    ]
    assert field_changes(version(False), after) == [
        {"key": "parts", "kind": "changed", "count": 1}
    ]


def with_degree(degree: str) -> dict:
    """The version with a degree entered on the space (`Degree()`): the field on the space, and the degree in the
    space's entry of the path of what it holds, as the write form has them"""
    data = version()
    space = data["parts"][0]
    space["how_likely"] = degree
    space["contents"][0]["context_path"] = [PATH[0], {**PATH[1], "degree": degree}]
    return data


def test_a_changed_degree_is_a_change_of_the_space_s_field_and_not_of_the_path():
    changes = diff(with_degree("likely"), with_degree("unlikely"))
    assert [(c.path, c.kind, c.old, c.new) for c in changes] == [
        (f"parts[{NEGATIVE}].how_likely", "changed", "likely", "unlikely")
    ]
    assert field_changes(with_degree("likely"), with_degree("unlikely")) == [
        {"key": "parts", "kind": "changed", "count": 1}
    ]
    # (nor is the path, with its degree, in the read form)
    view = to_view(with_degree("likely"), {}, set(), with_degree("likely"))
    [space] = view["parts"]
    assert "context_path" not in space["contents"][0]


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


def stored():
    """A version of a statement as the history keeps it, with real ids"""
    data = version()
    ids = {HEAD: str(uuid7()), NEGATIVE: str(uuid7()), PART: str(uuid7())}
    text = json.dumps(data)
    for old, new in ids.items():
        text = text.replace(f'"{old}"', f'"{new}"')
    return record(content=json.loads(text))


def test_a_version_holding_the_path_is_not_refused(statement_models, monkeypatch):
    monkeypatch.setattr(draft_module, "installed_apps", lambda: ["letters"])
    monkeypatch.setattr(
        draft_module, "schema_position", lambda apps: {"letters": "0001_initial"}
    )
    draft = draft_module.make_draft(stored(), statement_models)
    assert draft.problems == []
    assert not draft.upgraded
    update = statement_models.Update.model_validate(draft.data)
    assert update.parts[0].contents[0].text == "a"
