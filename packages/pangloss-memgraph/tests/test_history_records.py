"""History (`pangloss-history`) recording real writes to Memgraph, through the hook."""

from types import SimpleNamespace
from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_core import settings as core_settings
from pangloss_history import listener
from pangloss_history.store import SqliteStore
from pangloss_models import hooks, initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def history(tmp_path, monkeypatch):
    path = tmp_path / "h.sqlite3"
    # (after `initialise`, which reads the real settings, the ones history reads are swapped)
    yield (
        path,
        lambda: monkeypatch.setattr(
            core_settings,
            "SETTINGS",
            SimpleNamespace(
                INSTALLED_APPS=[], HISTORY_DB_PATH=str(path), HISTORY_BATCH_MS=1
            ),
            raising=False,
        ),
    )
    listener.reset_recorder()
    hooks.after_write[:] = [h for h in hooks.after_write if h is not listener.on_write]


@no_type_check
async def test_the_whole_life_of_a_document_and_the_entity_it_made_is_recorded(
    db_driver, clear_database, history
):
    path, use_settings = history

    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Statement(Document):
        text: str
        about: Person

    initialise()
    use_settings()
    listener.reset_recorder()
    listener.install()

    person_id = uuid7()
    about = {"type": "Person", "id": person_id, "label": "P", "create_new": True}
    statement = await Statement.Create(label="S", text="one", about=about).save()
    await Statement.Update(
        id=statement.id,
        label="S",
        text="two",
        about={"type": "Person", "id": person_id},
    ).save()
    await Statement.delete(statement.id)
    await Statement.undelete(statement.id)

    listener.get_recorder().drain()
    store = SqliteStore(path)

    assert [(r.version, r.op, r.model) for r in store.versions(statement.id)] == [
        (1, "create", "Statement"),
        (2, "update", "Statement"),
        (2, "delete", "Statement"),
        (2, "undelete", "Statement"),
    ]
    assert store.get(statement.id, 1).data()["text"] == "one"
    assert store.get(statement.id, 2).data()["text"] == "two"

    # (the entity was made by the first write, and has its own history)
    (made,) = store.versions(person_id)
    assert (made.version, made.op, made.model) == (1, "create", "Person")
    assert store.get(person_id, 1).data()["label"] == "P"

    # The write form has the ids (what a restore will need)
    assert store.get(statement.id, 1).data()["id"] == str(statement.id)
