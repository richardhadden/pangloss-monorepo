import datetime
from types import SimpleNamespace
from uuid import uuid7

import pytest
from pangloss_core import settings as core_settings
from pangloss_history import listener
from pangloss_history.store import SqliteStore
from pangloss_models import hooks
from pangloss_models.hooks import WriteEvent, emit_write_event
from pydantic import BaseModel

AT = datetime.datetime(2026, 10, 23, tzinfo=datetime.UTC)


class Statement(BaseModel):
    id: object
    type: str = "Statement"
    text: str


class Person(Statement):
    type: str = "Person"


@pytest.fixture
def history(tmp_path, monkeypatch):
    settings = SimpleNamespace(
        INSTALLED_APPS=[], HISTORY_DB_PATH=str(tmp_path / "h.sqlite3"), HISTORY_BATCH_MS=1
    )
    monkeypatch.setattr(core_settings, "SETTINGS", settings, raising=False)
    monkeypatch.setattr(hooks, "after_write", [])
    listener.reset_recorder()
    listener.install()
    yield settings
    listener.reset_recorder()


def event(op="create", version=1, payload=None, created=(), model=Statement, id=None):
    return WriteEvent(
        op=op,
        model=model,
        id=id or uuid7(),
        version=version,
        user="john",
        at=AT,
        payload=payload,
        created_entities=tuple(created),
    )


def recorded(history, id):
    listener.get_recorder().drain()
    return SqliteStore(history.HISTORY_DB_PATH)


def test_a_write_makes_a_record_with_its_content(history):
    id = uuid7()
    emit_write_event(event(payload=Statement(id=id, text="one"), id=id))
    emit_write_event(event("update", 2, Statement(id=id, text="two"), id=id))
    emit_write_event(event("delete", 2, id=id))

    store = recorded(history, id)
    assert [(r.version, r.op, r.who) for r in store.versions(id)] == [
        (1, "create", "john"),
        (2, "update", "john"),
        (2, "delete", "john"),
    ]
    assert store.get(id, 2).data()["text"] == "two"
    assert store.get(id, 1).schema_position == {}


def test_an_entity_made_by_the_write_has_a_first_version_of_its_own(history):
    doc, person = uuid7(), uuid7()
    emit_write_event(
        event(
            payload=Statement(id=doc, text="s"),
            id=doc,
            created=[Person(id=person, text="p")],
        )
    )
    store = recorded(history, doc)
    (made,) = store.versions(person)
    assert (made.model, made.version, made.op) == ("Person", 1, "create")
    assert store.get(person, 1).data()["text"] == "p"
    assert len(store.versions(doc)) == 1


def test_a_model_that_is_excluded_has_no_history(history):
    history.HISTORY_EXCLUDE = ["Statement"]
    id = uuid7()
    emit_write_event(event(payload=Statement(id=id, text="x"), id=id))
    assert recorded(history, id).versions(id) == []


def test_what_is_kept_is_what_was_written_even_if_the_object_changes_later(history):
    id = uuid7()
    payload = Statement(id=id, text="before")
    emit_write_event(event(payload=payload, id=id))
    payload.text = "after"
    assert recorded(history, id).get(id, 1).data()["text"] == "before"


def test_a_store_that_cannot_be_made_does_not_fail_the_write(history, tmp_path, caplog):
    history.HISTORY_DB_PATH = str(tmp_path / "a-file" / "h.sqlite3")
    (tmp_path / "a-file").write_text("not a directory")
    emit_write_event(event(payload=Statement(id=uuid7(), text="x")))  # (does not raise)
    assert "listener to writes failed" in caplog.text
