"""Restoring a version from history (`pangloss-history`): the old content as a new version."""

from dataclasses import replace
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_core import settings as core_settings
from pangloss_history import listener
from pangloss_history.restore import PanglossRestoreError, restore
from pangloss_history.store import SqliteStore
from pangloss_models import hooks, initialise
from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossNotFoundError,
    PanglossVersionConflictError,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pydantic import AnyHttpUrl

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def history(tmp_path, monkeypatch):
    path = tmp_path / "h.sqlite3"

    def start():
        monkeypatch.setattr(
            core_settings,
            "SETTINGS",
            SimpleNamespace(
                INSTALLED_APPS=[], HISTORY_DB_PATH=str(path), HISTORY_BATCH_MS=1
            ),
            raising=False,
        )
        listener.reset_recorder()
        listener.install()
        return SqliteStore(path)

    yield start
    listener.reset_recorder()
    hooks.after_write[:] = [h for h in hooks.after_write if h is not listener.on_write]


def models():
    class Person(Entity):
        pass

    class Statement(Document):
        text: str
        about: Person

    initialise()
    return Person, Statement


def about(person):
    return {"type": "Person", "id": person.id}


@no_type_check
async def test_a_restore_writes_the_old_content_as_a_new_version(
    db_driver, clear_database, history
):
    Person, Statement = models()
    store = history()

    person = await Person.Create(label="John").save()
    s = await Statement.Create(label="S", text="one", about=about(person)).save()
    await Statement.Update(id=s.id, label="S", text="two", about=about(person)).save()
    listener.get_recorder().drain()

    new_version = await restore(store, Statement, s.id, 1)

    assert new_version == 3
    now = await Statement.get(s.id)
    assert (now.text, now.meta.version) == ("one", 3)
    listener.get_recorder().drain()
    records = store.versions(s.id)
    assert [(r.version, r.op, r.restored_from) for r in records] == [
        (1, "create", None),
        (2, "update", None),
        (3, "restore", 1),
    ]
    assert store.get(s.id, 3).data()["text"] == "one"  # (history is not rewritten)
    assert store.get(s.id, 2).data()["text"] == "two"


@no_type_check
async def test_a_restore_of_a_stale_version_is_refused_and_writes_nothing(
    db_driver, clear_database, history
):
    Person, Statement = models()
    store = history()
    person = await Person.Create(label="John").save()
    s = await Statement.Create(label="S", text="one", about=about(person)).save()
    await Statement.Update(id=s.id, label="S", text="two", about=about(person)).save()
    listener.get_recorder().drain()

    with pytest.raises(PanglossVersionConflictError):
        await restore(store, Statement, s.id, 1, expected_version=1)
    assert (await Statement.get(s.id)).text == "two"
    assert (await Statement.get(s.id)).meta.version == 2


@no_type_check
async def test_a_deleted_document_is_undeleted_by_restoring_a_version(
    db_driver, clear_database, history
):
    Person, Statement = models()
    store = history()
    person = await Person.Create(label="John").save()
    s = await Statement.Create(label="S", text="one", about=about(person)).save()
    await Statement.delete(s.id)
    assert await Statement.get(s.id) is None
    listener.get_recorder().drain()

    assert await restore(store, Statement, s.id, 1) == 2
    assert (await Statement.get(s.id)).text == "one"


@no_type_check
async def test_an_entity_deleted_since_is_undeleted_and_one_that_is_gone_is_a_problem(
    db_driver, clear_database, history
):
    Person, Statement = models()
    store = history()
    john = await Person.Create(label="John").save()
    jane = await Person.Create(label="Jane").save()
    s = await Statement.Create(label="S", text="one", about=about(john)).save()
    await Statement.Update(id=s.id, label="S", text="two", about=about(jane)).save()
    listener.get_recorder().drain()
    await Person.delete(john.id)  # (nothing refers to John now)
    assert await Person.get(john.id) is None

    await restore(store, Statement, s.id, 1)
    assert (await Person.get(john.id)).label == "John"
    assert (await Statement.get(s.id)).text == "one"

    # Now one that is gone altogether
    await Statement.Update(id=s.id, label="S", text="three", about=about(jane)).save()
    listener.get_recorder().drain()
    run(db_driver, "MATCH (n {id: $id}) DETACH DELETE n", id=str(john.id))
    with pytest.raises(PanglossRestoreError) as error:
        await restore(store, Statement, s.id, 1)
    assert error.value.problems[0]["kind"] == "reference-missing"
    assert (await Statement.get(s.id)).text == "three"


@no_type_check
async def test_a_url_that_another_entity_has_taken_is_a_conflict(
    db_driver, clear_database, history
):
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()
    store = history()
    url = AnyHttpUrl("http://example.com/john")
    john = await Person.Create(id=url, create_new=True, label="John").save()
    await Person.Update(id=john.id, label="John", urls=[]).save()
    await Person.Create(id=url, create_new=True, label="Other").save()
    listener.get_recorder().drain()

    with pytest.raises(PanglossConflictError):
        await restore(store, Person, john.id, 1)
    assert (await Person.get(john.id)).meta.version == 2


@no_type_check
async def test_an_entity_is_restored_with_its_own_values(
    db_driver, clear_database, history
):
    Person, Statement = models()
    store = history()
    john = await Person.Create(label="John").save()
    await Person.Update(id=john.id, label="Johnny").save()
    listener.get_recorder().drain()

    assert await restore(store, Person, john.id, 1) == 3
    assert (await Person.get(john.id)).label == "John"


@no_type_check
async def test_what_cannot_be_restored_is_refused(db_driver, clear_database, history):
    Person, Statement = models()
    store = history()
    person = await Person.Create(label="John").save()
    s = await Statement.Create(label="S", text="one", about=about(person)).save()
    listener.get_recorder().drain()

    with pytest.raises(PanglossNotFoundError):
        await restore(store, Statement, s.id, 7)  # (never recorded)
    with pytest.raises(PanglossNotFoundError):
        await restore(store, Person, s.id, 1)  # (it is a Statement)

    # Written when the migrations were somewhere that is not a migration now: it cannot be upgraded
    old = replace(store.get(s.id, 1), schema_position={"letters": "0009_gone"})
    store.append([old])
    with pytest.raises(PanglossRestoreError) as error:
        await restore(store, Statement, s.id, 1)
    assert error.value.problems[0]["kind"] == "unknown-position"
