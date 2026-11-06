"""History installed on a project that has data already (`pangloss-history`): nothing is recorded of that data until it
is written again, so `pangloss history baseline` records what it is now; and a version in the read form, as the
interface shows it."""

from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_core import settings as core_settings
from pangloss_history import SqliteStore, listener
from pangloss_history.baseline import make_baseline
from pangloss_history.restore import restore
from pangloss_history.view import view_of
from pangloss_models import Document, Entity, hooks, initialise

pytestmark = pytest.mark.asyncio(loop_scope="session")

# (the schema position of a project with no migrations, as the listener records it)
POSITION: dict[str, str] = {}


@pytest.fixture
def history(tmp_path, monkeypatch):
    path = tmp_path / "h.sqlite3"

    def install():
        # (after the models are initialised, which need the test's own settings)
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

    yield SimpleNamespace(store=SqliteStore(path), install=install)
    listener.reset_recorder()
    hooks.after_write[:] = [h for h in hooks.after_write if h is not listener.on_write]


def models():
    class Person(Entity):
        pass

    class Part(Document):
        text: str

    class Statement(Document):
        text: str
        about: Person
        parts: list[Part]

    initialise()
    return Person, Part, Statement


def about(person):
    return {"type": "Person", "id": person.id}


@no_type_check
async def test_data_from_before_history_gets_a_baseline_once(
    db_driver, clear_database, history
):
    Person, Part, Statement = models()
    # (written before history is installed: nothing is recorded)
    john = await Person.Create(label="John").save()
    s = await Statement.Create(
        label="S",
        text="one",
        about=about(john),
        parts=[{"type": "Part", "label": "P", "text": "a"}],
    ).save()
    await Statement.Update(
        id=s.id, label="S", text="two", about=about(john), parts=[]
    ).save()
    history.install()
    assert history.store.versions(s.id) == []

    result = await make_baseline(history.store, POSITION, [Person, Part, Statement])

    # (the person and the statement: a part inside a statement is not a head node of its own)
    assert (result.recorded, result.up_to_date, result.failed) == (2, 0, [])
    [record] = history.store.versions(s.id)
    assert (record.version, record.op, record.model) == (2, "baseline", "Statement")
    content = history.store.get(s.id, 2).data()
    assert content["text"] == "two" and content["about"]["id"] == str(john.id)
    assert history.store.get(john.id, 1).op == "baseline"

    again = await make_baseline(history.store, POSITION, [Person, Part, Statement])
    assert (again.recorded, again.up_to_date) == (0, 2)


@no_type_check
async def test_a_document_inside_another_gets_no_baseline_of_its_own(
    db_driver, clear_database, history
):
    """A part of a statement is listed with the parts, but is written with its statement and has no versions of
    its own: a dry run said that each "would be recorded" (19,191 statements of 8,795 factoids), and a run would
    have written a record for each"""
    Person, Part, Statement = models()
    john = await Person.Create(label="John").save()
    s = await Statement.Create(
        label="S",
        text="one",
        about=about(john),
        parts=[
            {"type": "Part", "label": "P1", "text": "a"},
            {"type": "Part", "label": "P2", "text": "b"},
        ],
    ).save()
    history.install()
    parts = (await Statement.get(s.id)).parts
    assert len(parts) == 2

    dry = await make_baseline(history.store, POSITION, dry_run=True)
    assert (dry.looked_at, dry.recorded, dry.up_to_date, dry.failed) == (2, 2, 0, [])
    made = await make_baseline(history.store, POSITION)
    assert (made.looked_at, made.recorded) == (2, 2)
    assert history.store.latest_version(john.id) == 1
    assert history.store.latest_version(s.id) == 1
    for part in parts:
        assert history.store.latest_version(part.id) is None
    # (the statement's record has its parts in it)
    assert "P2" in str(history.store.get(s.id, 1).data())
    again = await make_baseline(history.store, POSITION, dry_run=True)
    assert (again.looked_at, again.recorded, again.up_to_date) == (2, 0, 2)


@no_type_check
async def test_a_baseline_is_restored_and_edits_after_it_are_recorded(
    db_driver, clear_database, history
):
    Person, Part, Statement = models()
    john = await Person.Create(label="John").save()
    s = await Statement.Create(
        label="S", text="one", about=about(john), parts=[]
    ).save()
    history.install()
    await make_baseline(history.store, POSITION, [Statement])
    await Statement.Update(
        id=s.id, label="S", text="two", about=about(john), parts=[]
    ).save()
    listener.get_recorder().drain()
    assert [(r.version, r.op) for r in history.store.versions(s.id)] == [
        (1, "baseline"),
        (2, "update"),
    ]

    assert await restore(history.store, Statement, s.id, 1) == 3
    assert (await Statement.get(s.id)).text == "one"


@no_type_check
async def test_a_head_node_ahead_of_its_history_gets_a_baseline(
    db_driver, clear_database, history
):
    Person, Part, Statement = models()
    john = await Person.Create(label="John").save()
    history.install()
    s = await Statement.Create(
        label="S", text="one", about=about(john), parts=[]
    ).save()
    listener.get_recorder().drain()
    listener.reset_recorder()
    hooks.after_write[:] = [h for h in hooks.after_write if h is not listener.on_write]
    # (a write that was not recorded: history was off, or the queue was full)
    await Statement.Update(
        id=s.id, label="S", text="two", about=about(john), parts=[]
    ).save()

    result = await make_baseline(history.store, POSITION, [Statement])

    assert result.recorded == 1
    assert [(r.version, r.op) for r in history.store.versions(s.id)] == [
        (1, "create"),
        (2, "baseline"),
    ]


@no_type_check
async def test_a_version_in_the_read_form_has_the_labels_of_its_entities_now(
    db_driver, clear_database, history
):
    Person, Part, Statement = models()
    history.install()
    john = await Person.Create(label="John").save()
    gone = await Person.Create(label="Gone").save()
    s = await Statement.Create(
        label="S",
        text="one",
        about=about(john),
        parts=[{"type": "Part", "label": "P", "text": "a"}],
    ).save()
    await Person.Update(id=john.id, label="John Smith").save()
    listener.get_recorder().drain()

    view = await view_of(history.store.get(s.id, 1).data())

    assert view["about"] == {
        "id": str(john.id),
        "type": "Person",
        "label": "John Smith",
    }
    assert view["parts"][0]["text"] == "a" and "contextLabels" not in view["parts"][0]
    assert "semanticSpaces" not in view

    await Person.delete(gone.id)
    other = await view_of(
        {
            "type": "Statement",
            "id": str(s.id),
            "about": about(gone) | {"id": str(gone.id)},
        }
    )
    assert other["about"]["missing"] is True and other["about"]["label"] is None
