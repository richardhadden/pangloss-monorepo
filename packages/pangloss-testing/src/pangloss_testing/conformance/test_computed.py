"""What the server computes (`Computed()`): a field that is read with its model and written by `set_computed` alone.

It is no version of the document (no `PGUpdate`, no history), and a computed relation is no reference (it keeps
nothing from being deleted, counts for no usage, and a merge does not move it). An update keeps what was computed for
a node that says the same as before (implementation_docs/matches-criteria.md, "`Computed()`")."""

import asyncio
import datetime
from typing import Annotated, no_type_check

import pytest
from pangloss_core import settings as core_settings
from pangloss_core import storage_of
from pangloss_history import SqliteStore, listener
from pangloss_history.diff import diff
from pangloss_history.restore import restore
from pangloss_models import (
    Computed,
    ComputedTarget,
    ComputedWrite,
    Document,
    Entity,
    Match,
    PanglossEntityInUseError,
    PanglossNotFoundError,
    PanglossWriteError,
    ReifiedRelation,
    hooks,
    initialise,
)
from pangloss_users import see_unpublished
from types import SimpleNamespace
from pydantic import ValidationError

from .helpers import DATABASE_NAME, run

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Guess[T](ReifiedRelation[T]):
        """Someone the source does not name"""

        wording: str | None = None
        target: Annotated[list[T], Computed()] = []
        count: Annotated[int, Computed()] = 0
        worked_out: Annotated[datetime.datetime | None, Computed()] = None
        tags: Annotated[list[str], Computed()] = []

    class Act(Document):
        by: list[Person | Guess[Person]]
        at: Place | None = None
        score: Annotated[int, Computed()] = 0
        near: Annotated[list[Place], Computed()] = []

    initialise()
    return Person, Place, Guess, Act


def set_computed():
    return storage_of().operations.set_computed


def ref(item):
    return {"type": type(item)._owner.__name__, "id": item.id}


async def an_act(Act, *people, wording="N. N.", label="An act", at=None):
    """An act by the people, and by someone not named"""
    return await Act.Create(
        label=label,
        by=[*(ref(p) for p in people), {"type": "Guess", "wording": wording}],
        at=ref(at) if at is not None else None,
    ).save(detail=True)


def guess_of(act):
    return next(item for item in act.by if item.type == "Guess")


def versions(db_driver, head_id) -> int:
    return run(
        db_driver,
        "MATCH (h:HeadNode {id: $id}) RETURN size([(h)<-[:is_update_of]-(u:PGUpdate) | u]) + 1 AS version",
        id=str(head_id),
    )[0]["version"]


def pending(db_driver, kind="test-work"):
    return sorted(
        r["head"]
        for r in run(
            db_driver,
            "MATCH (p:PGPending {kind: $kind}) RETURN p.head_id AS head",
            kind=kind,
        )
    )


def forget_pending(db_driver):
    db_driver.execute_query(
        "MATCH (p:PGPending) DETACH DELETE p", database=DATABASE_NAME
    )


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


@pytest.fixture
def listening():
    """Two kinds of work asked of every write, the write events, and what is told of work marked"""

    class Heard:
        events: list = []
        marked: list = []

    heard = Heard()
    heard.events, heard.marked = [], []
    work = lambda model: ["test-work", "own-work"]  # noqa: E731
    hooks.pending_work.append(work)
    hooks.work_marked.append(heard.marked.append)
    hooks.after_write.append(heard.events.append)
    yield heard
    hooks.pending_work.remove(work)
    hooks.work_marked.remove(heard.marked.append)
    hooks.after_write.remove(heard.events.append)


# --- written by set_computed, read with the document ----------------------------------------------------------------


@no_type_check
async def test_a_computed_field_is_read_with_its_document_and_starts_empty(
    clear_database,
):
    Person, Place, Guess, Act = models()
    john = await Person.Create(label="John").save()
    act = await an_act(Act, john)

    assert act.score == 0 and act.near == []
    guess = guess_of(act)
    assert guess.wording == "N. N."
    assert guess.target == [] and guess.count == 0
    assert guess.worked_out is None and guess.tags == []


@no_type_check
async def test_set_computed_gives_a_nested_node_its_relation_and_values(
    clear_database,
):
    Person, Place, Guess, Act = models()
    john = await Person.Create(label="John").save()
    ann = await Person.Create(label="Ann").save()
    bob = await Person.Create(label="Bob").save()
    act = await an_act(Act, john)
    when = datetime.datetime(2026, 11, 19, 10, 12, tzinfo=datetime.UTC)

    written = await set_computed()(
        guess_of(act).id,
        {
            "target": [bob.id, ann.id],
            "count": 2,
            "worked_out": when,
            "tags": ["a", "b"],
        },
        based_on_version=1,
    )

    assert written is True
    guess = guess_of(await Act.get(act.id))
    # (in the order given)
    assert [(p.type, p.label) for p in guess.target] == [
        ("Person", "Bob"),
        ("Person", "Ann"),
    ]
    assert guess.count == 2 and guess.worked_out == when and guess.tags == ["a", "b"]
    # (the edges are not those of an edge model: nothing of them is shown)
    assert not hasattr(guess.target[0], "edge_properties")
    assert "edgeProperties" not in guess.target[0].model_dump(by_alias=True)


@no_type_check
async def test_set_computed_gives_a_head_its_own_computed_fields(clear_database):
    Person, Place, Guess, Act = models()
    vienna = await Place.Create(label="Vienna").save()
    act = await an_act(Act)

    assert await set_computed()(act.id, {"score": 7, "near": [vienna.id]}) is True

    read = await Act.get(act.id)
    assert read.score == 7 and [p.label for p in read.near] == ["Vienna"]


@no_type_check
async def test_set_computed_replaces_what_was_computed_and_none_takes_a_value_away(
    clear_database,
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    bob = await Person.Create(label="Bob").save()
    act = await an_act(Act)
    guess = guess_of(act).id
    when = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    await set_computed()(
        guess, {"target": [ann.id, bob.id], "count": 2, "worked_out": when}
    )

    # (a field that is not named keeps what it has)
    await set_computed()(guess, {"target": [bob.id]})
    read = guess_of(await Act.get(act.id))
    assert [p.label for p in read.target] == ["Bob"]
    assert read.count == 2 and read.worked_out == when

    await set_computed()(guess, {"target": [], "worked_out": None})
    read = guess_of(await Act.get(act.id))
    assert read.target == [] and read.worked_out is None and read.count == 2


@no_type_check
async def test_a_computed_relation_is_a_pair_of_marked_edges_each_entity_once(
    clear_database, db_driver
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act)
    guess = guess_of(act).id

    await set_computed()(guess, {"target": [ann.id, ann.id, str(ann.id)]})
    await set_computed()(guess, {"target": [ann.id]})

    edges = run(
        db_driver,
        """
        MATCH (a {id: $ann})-[e]-(g {id: $guess})
        RETURN type(e) AS type, startNode(e).id AS start, properties(e) AS properties ORDER BY type
        """,
        ann=str(ann.id),
        guess=str(guess),
    )
    assert edges == [
        {
            "type": "target",
            "start": str(guess),
            "properties": {"computed": True, "pg_position": 0},
        },
        {
            "type": "target_reverse",
            "start": str(ann.id),
            "properties": {"computed": True, "reverse": True},
        },
    ]


@no_type_check
async def test_who_may_see_a_computed_edge_is_kept_on_it(clear_database, db_driver):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    bob = await Person.Create(label="Bob").save()
    act = await an_act(Act)
    guess = guess_of(act).id

    await set_computed()(
        guess,
        {
            "target": [
                ComputedTarget(ann.id, seen_by="logged_in"),
                {"id": bob.id, "seen_by": "everyone"},
            ]
        },
    )

    seen = run(
        db_driver,
        "MATCH ({id: $guess})-[e:target]->(p) RETURN p.label AS label, e.seen_by AS seen_by ORDER BY label",
        guess=str(guess),
    )
    # (everyone is what an edge that says nothing means)
    assert seen == [
        {"label": "Ann", "seen_by": "logged_in"},
        {"label": "Bob", "seen_by": None},
    ]
    with pytest.raises(PanglossWriteError, match="seen_by"):
        await set_computed()(guess, {"target": [ComputedTarget(ann.id, seen_by="me")]})


# --- no version ------------------------------------------------------------------------------------------------------


@no_type_check
async def test_set_computed_makes_no_version_and_no_record_of_an_update(
    clear_database, db_driver
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act)

    await set_computed()(guess_of(act).id, {"target": [ann.id], "count": 1})
    await set_computed()(act.id, {"score": 3})

    read = await Act.get(act.id)
    assert read.meta.version == 1 and versions(db_driver, act.id) == 1
    assert read.meta.updated_by is None and read.meta.updated_when is None
    assert run(db_driver, "MATCH (u:PGUpdate) RETURN count(u) AS n") == [{"n": 0}]
    # (and an update based on the version read before is still taken)
    await Act.Update(id=act.id, label="Changed", by=[]).save(expected_version=1)


@no_type_check
async def test_set_computed_is_refused_when_the_head_has_moved_on(clear_database):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act)
    guess = guess_of(act)
    await Act.Update(
        id=act.id,
        label="An act, corrected",
        by=[{"type": "Guess", "id": guess.id, "wording": "N. N."}],
    ).save()

    # (worked out from version 1, and the document is at 2: nothing is written, and it says so)
    assert (
        await set_computed()(
            guess.id, {"target": [ann.id], "count": 1}, based_on_version=1
        )
        is False
    )
    read = guess_of(await Act.get(act.id))
    assert read.target == [] and read.count == 0

    assert await set_computed()(guess.id, {"count": 1}, based_on_version=2) is True
    # (with no version named, whatever it is)
    assert await set_computed()(guess.id, {"count": 5}) is True
    assert guess_of(await Act.get(act.id)).count == 5


@no_type_check
async def test_set_computed_writes_nothing_to_a_deleted_document(clear_database):
    Person, Place, Guess, Act = models()
    act = await an_act(Act)
    await Act.delete(act.id)

    assert await set_computed()(act.id, {"score": 1}) is False
    assert await set_computed()(guess_of(act).id, {"count": 1}) is False

    await Act.undelete(act.id)
    read = await Act.get(act.id)
    assert read.score == 0 and guess_of(read).count == 0


@no_type_check
async def test_set_computed_gives_a_computed_event_for_the_head(
    clear_database, listening
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act)
    listening.events.clear()

    await set_computed()(guess_of(act).id, {"target": [ann.id]})

    assert [(e.op, e.model, e.id, e.version) for e in listening.events] == [
        ("computed", Act, act.id, 1)
    ]
    assert listening.events[0].payload is None
    # (refused: no event)
    listening.events.clear()
    await set_computed()(guess_of(act).id, {"count": 9}, based_on_version=4)
    assert listening.events == []


@no_type_check
async def test_history_keeps_no_record_of_what_is_computed_and_no_diff_names_it(
    clear_database, history
):
    Person, Place, Guess, Act = models()
    # (asked for before the settings are those of the history's test)
    write = set_computed()
    store = history()
    john = await Person.Create(label="John").save()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act, john)
    guess = guess_of(act)
    await write(guess.id, {"target": [ann.id], "count": 1})
    await write(act.id, {"score": 3})
    await Act.Update(
        id=act.id,
        label="Renamed",
        by=[ref(john), {"type": "Guess", "id": guess.id, "wording": "N. N."}],
    ).save()
    await write(guess.id, {"count": 2})
    listener.get_recorder().drain()

    records = store.versions(act.id)
    assert [(r.version, r.op) for r in records] == [(1, "create"), (2, "update")]
    for record in records:
        content = store.get(act.id, record.version).data()
        assert "score" not in content and "near" not in content
        described = next(item for item in content["by"] if item["type"] == "Guess")
        assert set(described) & {"target", "count", "worked_out", "tags"} == set()
    changes = diff(store.get(act.id, 1).data(), store.get(act.id, 2).data())
    assert [change.path for change in changes] == ["label"]


@no_type_check
async def test_a_restored_version_keeps_what_was_computed_for_what_it_leaves_unchanged(
    clear_database, history
):
    Person, Place, Guess, Act = models()
    # (asked for before the settings are those of the history's test)
    write = set_computed()
    store = history()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act)
    guess = guess_of(act)
    await Act.Update(
        id=act.id,
        label="Renamed",
        by=[{"type": "Guess", "id": guess.id, "wording": "N. N."}],
    ).save()
    await write(guess.id, {"target": [ann.id], "count": 1})
    listener.get_recorder().drain()

    assert await restore(store, Act, act.id, 1) == 3

    read = await Act.get(act.id)
    assert read.label == "An act" and read.meta.version == 3
    assert [p.label for p in guess_of(read).target] == ["Ann"]
    assert guess_of(read).count == 1


# --- pending work ----------------------------------------------------------------------------------------------------


@no_type_check
async def test_set_computed_marks_the_head_less_the_kinds_named_and_tells_of_it(
    clear_database, db_driver, listening
):
    Person, Place, Guess, Act = models()
    act = await an_act(Act)
    forget_pending(db_driver)
    assert listening.marked == []

    await set_computed()(guess_of(act).id, {"count": 1}, less=["own-work"])

    # (the head, not the node; and not the kind of whoever computed it)
    assert pending(db_driver) == [str(act.id)]
    assert pending(db_driver, "own-work") == []
    assert listening.marked == [Act]

    forget_pending(db_driver)
    await set_computed()(act.id, {"score": 1})
    assert pending(db_driver) == [str(act.id)]
    assert pending(db_driver, "own-work") == [str(act.id)]

    # (refused: nothing marked, nobody told)
    forget_pending(db_driver)
    listening.marked.clear()
    await set_computed()(act.id, {"score": 2}, based_on_version=9)
    assert pending(db_driver) == [] and listening.marked == []


@no_type_check
async def test_several_are_written_in_one_transaction_with_what_follows_them(
    clear_database, db_driver, listening
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    first = await an_act(Act, label="First")
    second = await an_act(Act, label="Second")
    listening.events.clear()
    ran = []

    async def then(tx):
        ran.append(True)
        await (await tx.run("CREATE (:PGTestDone {at: 1})")).consume()

    written = await storage_of().operations.set_computed_batch(
        [
            ComputedWrite(guess_of(first).id, {"target": [ann.id]}, 1),
            ComputedWrite(first.id, {"score": 4}, 1),
            ComputedWrite(guess_of(second).id, {"count": 3}, 7),
        ],
        less=["own-work"],
        then=then,
    )

    assert written == [True, True, False] and ran
    assert run(db_driver, "MATCH (d:PGTestDone) RETURN count(d) AS n") == [{"n": 1}]
    assert (await Act.get(first.id)).score == 4
    assert guess_of(await Act.get(second.id)).count == 0
    # (one event for a head, however many of its nodes were written)
    assert [(e.op, e.id) for e in listening.events] == [("computed", first.id)]
    db_driver.execute_query("MATCH (d:PGTestDone) DELETE d", database=DATABASE_NAME)

    async def failing(tx):
        raise RuntimeError("no")

    with pytest.raises(RuntimeError):
        await storage_of().operations.set_computed_batch(
            [ComputedWrite(first.id, {"score": 9})], then=failing
        )
    # (all of it or none)
    assert (await Act.get(first.id)).score == 4


# --- what it refuses -------------------------------------------------------------------------------------------------


@no_type_check
async def test_set_computed_writes_only_computed_fields_of_a_node_that_is_there(
    clear_database,
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act)
    guess = guess_of(act).id

    with pytest.raises(PanglossWriteError, match="no computed field wording"):
        await set_computed()(guess, {"wording": "Someone else"})
    with pytest.raises(PanglossWriteError, match="no computed field by"):
        await set_computed()(act.id, {"by": [ann.id]})
    with pytest.raises(PanglossWriteError, match="Guess.count"):
        await set_computed()(guess, {"count": "many"})
    with pytest.raises(PanglossNotFoundError):
        await set_computed()("00000000-0000-7000-8000-000000000000", {"count": 1})
    # (to an entity that is not there, or to something that is no entity: nothing of the call is written)
    with pytest.raises(PanglossWriteError, match="entities that are there"):
        await set_computed()(
            guess,
            {"count": 4, "target": [ann.id, "00000000-0000-7000-8000-000000000001"]},
        )
    with pytest.raises(PanglossWriteError, match="entities that are there"):
        await set_computed()(guess, {"target": [act.id]})
    read = guess_of(await Act.get(act.id))
    assert read.target == [] and read.count == 0 and read.wording == "N. N."


@no_type_check
async def test_a_deleted_or_merged_entity_is_left_out_of_what_is_computed(
    clear_database,
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    gone = await Person.Create(label="Gone").save()
    kept = await Person.Create(label="Kept").save()
    absorbed = await Person.Create(label="Absorbed").save()
    act = await an_act(Act)
    await Person.delete(gone.id)
    await Person.merge(absorbed.id, into=kept.id)

    assert await set_computed()(
        guess_of(act).id, {"target": [gone.id, ann.id, absorbed.id]}
    )

    assert [p.label for p in guess_of(await Act.get(act.id)).target] == ["Ann"]


# --- not written by anyone else --------------------------------------------------------------------------------------


@no_type_check
async def test_create_and_update_do_not_take_a_computed_field_but_take_it_back_from_a_read(
    clear_database,
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act)
    await set_computed()(guess_of(act).id, {"target": [ann.id], "count": 1})
    await set_computed()(act.id, {"score": 5})

    assert "score" not in Act.Create.model_fields
    assert "near" not in Act.Update.model_fields
    # (what a read gave, sent back as it is: taken out before the check, and not written)
    read = await Act.get(act.id)
    payload = read.model_dump(mode="json", by_alias=True)
    payload.pop("meta")
    payload["score"] = 99
    payload["by"][0]["count"] = 77
    payload["by"][0]["target"] = []
    await Act.Update(**payload).save()
    again = await Act.get(act.id)
    assert again.meta.version == 2
    # (and what was computed is as it was: the document says the same)
    assert again.score == 5
    assert guess_of(again).count == 1
    assert [p.label for p in guess_of(again).target] == ["Ann"]

    with pytest.raises(ValidationError):
        Act.Create(label="X", by=[], scor=1)


# --- an update keeps what was computed for what has not changed ------------------------------------------------------


@no_type_check
async def test_an_update_carries_over_what_was_computed_for_an_unchanged_node(
    clear_database, db_driver
):
    Person, Place, Guess, Act = models()
    john = await Person.Create(label="John").save()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act, john)
    guess = guess_of(act)
    when = datetime.datetime(2026, 11, 19, tzinfo=datetime.UTC)
    await set_computed()(
        guess.id,
        {
            "target": [ComputedTarget(ann.id, seen_by="logged_in")],
            "count": 1,
            "worked_out": when,
            "tags": ["x"],
        },
    )
    await set_computed()(act.id, {"score": 5})

    # (the head says something else; the description, with its id, says the same)
    await Act.Update(
        id=act.id,
        label="An act, renamed",
        by=[ref(john), {"type": "Guess", "id": guess.id, "wording": "N. N."}],
    ).save()

    read = await Act.get(act.id)
    assert read.meta.version == 2 and read.label == "An act, renamed"
    kept = guess_of(read)
    assert kept.id == guess.id
    assert [p.label for p in kept.target] == ["Ann"]
    assert kept.count == 1 and kept.worked_out == when and kept.tags == ["x"]
    # (the head changed, so what was computed for the head starts again)
    assert read.score == 0
    # (the edges are as they were: marked, with who may see them, a pair)
    edges = run(
        db_driver,
        "MATCH ({id: $guess})-[e]-(p:Person) RETURN type(e) AS type, properties(e) AS properties ORDER BY type",
        guess=str(guess.id),
    )
    assert edges == [
        {
            "type": "target",
            "properties": {"computed": True, "pg_position": 0, "seen_by": "logged_in"},
        },
        {
            "type": "target_reverse",
            "properties": {"computed": True, "reverse": True, "seen_by": "logged_in"},
        },
    ]


@no_type_check
async def test_an_unchanged_head_keeps_its_own_computed_fields(clear_database):
    Person, Place, Guess, Act = models()
    vienna = await Place.Create(label="Vienna").save()
    john = await Person.Create(label="John").save()
    act = await an_act(Act, john, at=vienna)
    await set_computed()(act.id, {"score": 5, "near": [vienna.id]})

    read = await Act.get(act.id)
    payload = read.model_dump(mode="json", by_alias=True)
    payload.pop("meta")
    await Act.Update(**payload).save()

    again = await Act.get(act.id)
    assert again.meta.version == 2
    assert again.score == 5 and [p.label for p in again.near] == ["Vienna"]


@no_type_check
async def test_a_node_that_changed_starts_with_nothing_computed(clear_database):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act)
    guess = guess_of(act)
    await set_computed()(guess.id, {"target": [ann.id], "count": 1})

    await Act.Update(
        id=act.id,
        label="An act",
        by=[{"type": "Guess", "id": guess.id, "wording": "N. N., a secretary"}],
    ).save()

    changed = guess_of(await Act.get(act.id))
    assert changed.id == guess.id and changed.wording == "N. N., a secretary"
    assert changed.target == [] and changed.count == 0


@no_type_check
async def test_a_node_written_anew_or_removed_carries_nothing(
    clear_database, db_driver
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act)
    guess = guess_of(act)
    await set_computed()(guess.id, {"target": [ann.id], "count": 1})

    # (the same words, with no id: another node)
    await Act.Update(
        id=act.id, label="An act", by=[{"type": "Guess", "wording": "N. N."}]
    ).save()
    new = guess_of(await Act.get(act.id))
    assert new.id != guess.id and new.target == [] and new.count == 0

    await set_computed()(new.id, {"target": [ann.id]})
    await Act.Update(id=act.id, label="An act", by=[]).save()
    # (gone with its node: no edge is left on the entity)
    assert run(
        db_driver, "MATCH ({id: $id})-[e]-() RETURN count(e) AS n", id=str(ann.id)
    ) == [{"n": 1}]  # (the record of its creation)
    assert (await Person.get(ann.id)).model_dump().get("by", []) == []


@no_type_check
async def test_what_was_computed_is_carried_over_several_updates_and_a_restore_of_nothing(
    clear_database,
):
    Person, Place, Guess, Act = models()
    john = await Person.Create(label="John").save()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act, john)
    guess = guess_of(act)
    await set_computed()(guess.id, {"target": [ann.id], "count": 1})

    for label in ("One", "Two", "Three"):
        await Act.Update(
            id=act.id,
            label=label,
            by=[ref(john), {"type": "Guess", "id": guess.id, "wording": "N. N."}],
        ).save()

    read = await Act.get(act.id)
    assert read.meta.version == 4
    assert [p.label for p in guess_of(read).target] == ["Ann"]
    assert guess_of(read).count == 1


# --- no reference ----------------------------------------------------------------------------------------------------


@no_type_check
async def test_an_entity_that_is_only_computed_to_be_related_can_be_deleted(
    clear_database, db_driver, listening
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    bob = await Person.Create(label="Bob").save()
    act = await an_act(Act)
    await set_computed()(guess_of(act).id, {"target": [ann.id, bob.id]})
    forget_pending(db_driver)
    listening.marked.clear()

    check = await storage_of().operations.check_deletable(Person, ann.id)
    assert check.deletable is True and check.referenced_by == []
    await Person.delete(ann.id)

    assert await Person.get(ann.id) is None
    # (the edge went with it, and the document it was in is left for whoever computes it; no new version)
    read = await Act.get(act.id)
    assert [p.label for p in guess_of(read).target] == ["Bob"]
    assert read.meta.version == 1
    assert str(act.id) in pending(db_driver)
    assert Act in listening.marked


@no_type_check
async def test_an_entity_that_is_also_referred_to_is_still_kept(clear_database):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    first = await an_act(Act, ann, label="Names her")
    second = await an_act(Act, label="Guesses her")
    await set_computed()(guess_of(second).id, {"target": [ann.id]})

    check = await storage_of().operations.check_deletable(Person, ann.id)
    assert check.deletable is False
    # (only what refers to her is named, not where she was computed to be)
    assert [r["id"] for r in check.referenced_by] == [str(first.id)]
    assert check.reference_count == 1
    with pytest.raises(PanglossEntityInUseError) as refused:
        await Person.delete(ann.id)
    assert [r["id"] for r in refused.value.referenced_by] == [str(first.id)]
    # (and what was computed stays: she was not deleted)
    assert [p.label for p in guess_of(await Act.get(second.id)).target] == ["Ann"]


@no_type_check
async def test_a_computed_relation_counts_for_no_usage(clear_database):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    bob = await Person.Create(label="Bob").save()
    await an_act(Act, bob, label="Names Bob")
    act = await an_act(Act, label="Guesses Ann")
    await set_computed()(guess_of(act).id, {"target": [ann.id, bob.id]})

    listed = await Person.list(use_counts=True)
    assert listed.use_counts == {str(ann.id): 0, str(bob.id): 1}
    assert [p.label for p in (await Person.list(used_only=True)).results] == ["Bob"]
    found = await Person.search(Match(where={}), used_only=True)
    assert [p.label for p in found.results] == ["Bob"]


@no_type_check
async def test_what_is_offered_first_is_ordered_by_references_not_by_what_is_computed(
    clear_database,
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    bob = await Person.Create(label="Bob").save()
    await an_act(Act, bob, label="Names Bob")
    for index in range(3):
        act = await an_act(Act, label=f"Guesses Ann {index}")
        await set_computed()(guess_of(act).id, {"target": [ann.id]})

    offered = await Person.autocomplete("")

    assert [p.label for p in offered.results][:2] == ["Bob", "Ann"]


# --- read as any relation --------------------------------------------------------------------------------------------


@no_type_check
async def test_an_entity_lists_the_documents_it_is_computed_to_be_in(clear_database):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act, label="Guesses Ann")
    await set_computed()(guess_of(act).id, {"target": [ann.id]})

    read = await Person.get(ann.id)

    incoming = read.model_dump(by_alias=True)
    names = [
        key for key, value in incoming.items() if isinstance(value, list) and value
    ]
    assert len(names) == 1
    (held,) = incoming[names[0]]
    assert held["label"] == "Guesses Ann" and held["id"] == act.id


@no_type_check
async def test_a_search_passes_through_to_what_is_computed(clear_database):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    bob = await Person.Create(label="Bob").save()
    act = await an_act(Act, bob, label="Names Bob, guesses Ann")
    await an_act(Act, bob, label="Names Bob")
    await set_computed()(guess_of(act).id, {"target": [ann.id], "count": 1})

    by_ann = await Act.search(Match(where={"by": {"is": str(ann.id)}}))
    assert [a.label for a in by_ann.results] == ["Names Bob, guesses Ann"]
    # (and it can be asked that it does)
    through = await Act.search(
        Match(where={"by": {"is": str(ann.id), "through": ["Guess"]}})
    )
    assert [a.label for a in through.results] == ["Names Bob, guesses Ann"]
    named = await Act.search(
        Match(where={"by": {"is": str(bob.id), "through": ["Guess"]}})
    )
    assert named.results == []
    # (a computed value is searched as any value of the wrapper)
    counted = await Act.search(
        Match(
            where={
                "by": {
                    "exists": True,
                    "through": [{"type": "Guess", "where": {"count": {"gte": 1}}}],
                }
            }
        )
    )
    assert [a.label for a in counted.results] == ["Names Bob, guesses Ann"]


# --- merges ----------------------------------------------------------------------------------------------------------


@no_type_check
async def test_a_merge_neither_moves_nor_records_a_computed_edge(
    clear_database, db_driver, listening
):
    Person, Place, Guess, Act = models()
    kept = await Person.Create(label="Kept").save()
    absorbed = await Person.Create(label="Absorbed").save()
    other = await Person.Create(label="Other").save()
    named = await an_act(Act, absorbed, label="Names the absorbed")
    guessed = await an_act(Act, label="Guesses the absorbed")
    await set_computed()(guess_of(guessed).id, {"target": [absorbed.id, other.id]})
    forget_pending(db_driver)

    preview = await Person.merge_preview(absorbed.id, into=kept.id)
    assert preview.heads == 1 and preview.refer_to_absorbed == {"Act": 1}
    result = await Person.merge(absorbed.id, into=kept.id)

    # (one head was written by the merge: the one that names the entity)
    assert result.merge.heads == 1 and result.merge.moved == 1
    assert run(db_driver, "MATCH (m:PGMergeMove) RETURN m.pg_head AS head") == [
        {"head": str(named.id)}
    ]
    read = await Act.get(guessed.id)
    assert read.meta.version == 1
    # (not moved to the survivor: gone, and the document is left for whoever computes it)
    assert [p.label for p in guess_of(read).target] == ["Other"]
    assert str(guessed.id) in pending(db_driver)
    assert (await Act.get(named.id)).meta.version == 2


@no_type_check
async def test_computed_edges_do_not_count_against_the_limit_of_a_merge(
    clear_database, monkeypatch
):
    Person, Place, Guess, Act = models()
    kept = await Person.Create(label="Kept").save()
    absorbed = await Person.Create(label="Absorbed").save()
    await an_act(Act, absorbed, label="Names the absorbed")
    for index in range(3):
        act = await an_act(Act, label=f"Guess {index}")
        await set_computed()(guess_of(act).id, {"target": [absorbed.id]})

    monkeypatch.setattr(core_settings.SETTINGS, "MERGE_LIMIT", 1)
    result = await Person.merge(absorbed.id, into=kept.id)

    assert result.merge.heads == 1


@no_type_check
async def test_undoing_a_merge_leaves_what_was_computed_for_the_survivor_to_be_done_again(
    clear_database, db_driver, listening
):
    Person, Place, Guess, Act = models()
    kept = await Person.Create(label="Kept").save()
    absorbed = await Person.Create(label="Absorbed").save()
    guessed = await an_act(Act, label="Guesses the survivor")
    result = await Person.merge(absorbed.id, into=kept.id)
    await set_computed()(guess_of(guessed).id, {"target": [kept.id]})
    forget_pending(db_driver)

    await Person.unmerge(result.merge.id)

    assert str(guessed.id) in pending(db_driver)
    # (nothing is taken away: it may still hold)
    assert [p.label for p in guess_of(await Act.get(guessed.id)).target] == ["Kept"]
    assert (await Act.get(guessed.id)).meta.version == 1


@no_type_check
async def test_a_merged_entity_leaves_no_stray_reference_where_it_was_computed(
    clear_database, db_driver
):
    Person, Place, Guess, Act = models()
    kept = await Person.Create(label="Kept").save()
    absorbed = await Person.Create(label="Absorbed").save()
    guessed = await an_act(Act, label="Guess")
    await Person.merge(absorbed.id, into=kept.id)
    # (as a write that raced the merge would leave it)
    guess = guess_of(guessed).id
    db_driver.execute_query(
        """
        MATCH (g {id: $guess}), (b {id: $absorbed})
        CREATE (g)-[:target {computed: true, pg_position: 0}]->(b)
        CREATE (b)-[:target_reverse {computed: true, reverse: true}]->(g)
        """,
        parameters_={"guess": str(guess), "absorbed": str(absorbed.id)},
        database=DATABASE_NAME,
    )

    assert await storage_of().operations.stray_references() == []


# --- with other things -----------------------------------------------------------------------------------------------


@no_type_check
async def test_what_is_computed_is_read_as_the_reader_may_see_the_document(
    clear_database,
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    act = await an_act(Act)
    await set_computed()(guess_of(act).id, {"target": [ann.id], "count": 1})

    token = see_unpublished.set(False)
    try:
        read = await Act.get(act.id)
    finally:
        see_unpublished.reset(token)
    assert [p.label for p in guess_of(read).target] == ["Ann"]


@no_type_check
async def test_a_class_with_nothing_computed_is_written_as_it_was(
    clear_database, db_driver
):
    class Person(Entity):
        pass

    class Plain(Document):
        about: list[Person]

    initialise()
    ann = await Person.Create(label="Ann").save()
    plain = await Plain.Create(label="Plain", about=[ref(ann)]).save()
    await Plain.Update(id=plain.id, label="Plain still", about=[ref(ann)]).save()

    assert run(
        db_driver,
        "MATCH (n) WHERE n.pg_computed_basis IS NOT NULL RETURN count(n) AS n",
    ) == [{"n": 0}]
    with pytest.raises(PanglossWriteError, match="no computed field"):
        await set_computed()(plain.id, {"label": "No"})


@no_type_check
async def test_a_document_that_changes_class_keeps_what_was_computed_for_its_unchanged_parts(
    clear_database,
):
    class Person(Entity):
        pass

    class Guess[T](ReifiedRelation[T]):
        wording: str | None = None
        target: Annotated[list[T], Computed()] = []

    class Draft(Document):
        by: list[Person | Guess[Person]]
        score: Annotated[int, Computed()] = 0

    class Final(Document):
        by: list[Person | Guess[Person]]
        score: Annotated[int, Computed()] = 0

    initialise()
    ann = await Person.Create(label="Ann").save()
    draft = await Draft.Create(
        label="D", by=[{"type": "Guess", "wording": "N. N."}]
    ).save(detail=True)
    guess = draft.by[0]
    await set_computed()(guess.id, {"target": [ann.id]})
    await set_computed()(draft.id, {"score": 4})

    await Final.Update(
        id=draft.id,
        label="D",
        by=[{"type": "Guess", "id": guess.id, "wording": "N. N."}],
    ).save(changing_class_from=Draft)

    final = await Final.get(draft.id)
    assert [p.label for p in final.by[0].target] == ["Ann"]
    # (the head is another class now: what was computed for it as the other starts again)
    assert final.score == 0


@no_type_check
async def test_an_update_and_set_computed_at_once_never_leave_a_stale_result(
    clear_database,
):
    Person, Place, Guess, Act = models()
    ann = await Person.Create(label="Ann").save()
    for round in range(6):
        act = await an_act(Act, label=f"Round {round}")
        guess = guess_of(act)

        async def update(act=act, guess=guess):
            await Act.Update(
                id=act.id,
                label="Changed",
                by=[{"type": "Guess", "id": guess.id, "wording": "Someone else"}],
            ).save()

        async def compute(guess=guess):
            return await set_computed()(
                guess.id, {"target": [ann.id], "count": 1}, based_on_version=1
            )

        _, written = await asyncio.gather(update(), compute())

        read = await Act.get(act.id)
        assert read.meta.version == 2
        # (whichever went first: what was worked out for the old wording is not on the new one)
        assert guess_of(read).wording == "Someone else"
        assert guess_of(read).target == [] and guess_of(read).count == 0
        assert written in (True, False)
