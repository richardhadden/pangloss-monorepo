"""The instructions of one write (`hooks.declare_write_instruction`, `hooks.instructed_work`): what a create or an update
says (`save(instructions={...})`) decides, for a kind of pending work, whether the head is marked or a standing mark is
taken off, in the write's transaction. Only a create and an update of a head ask; nothing that copies a context from
inside one carries what it said. An app of the test declares the instruction and the work"""

import asyncio
import contextvars
from types import SimpleNamespace
from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_core import backend, storage_of
from pangloss_cypher import pending
from pangloss_history.restore import restore
from pangloss_history import listener
from pangloss_models import (
    Companion,
    Document,
    Entity,
    PanglossInstructionError,
    PanglossVersionConflictError,
    create_heads,
    hooks,
    initialise,
)
from pangloss_review import ReviewMeta, ReviewStatus, service

from .helpers import DATABASE_NAME, run
from .test_history_restore import history  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="session")

KIND = "test-instructed"
NAME = "test_suggest"


@pytest.fixture
def instructed():
    """An app that declares `test_suggest` and a kind of work it decides: marked when the write says `true`, taken off
    when it says `false`, and, when it says nothing, as `setting.on` says. `asked` records each question"""
    asked: list[tuple[str, dict[str, str]]] = []
    setting = SimpleNamespace(on=False, classes={"Letter", "Person", "Naming"})

    def work(model, instructions):
        asked.append((model.__name__, dict(instructions)))
        if model.__name__ not in setting.classes:
            return {}
        said = instructions.get(NAME)
        return {KIND: setting.on if said is None else said == "true"}

    hooks.declare_write_instruction(
        hooks.WriteInstruction(
            NAME, ("true", "false"), "Whether the test's work follows"
        )
    )
    hooks.instructed_work.append(work)
    try:
        yield SimpleNamespace(asked=asked, setting=setting)
    finally:
        hooks.instructed_work.remove(work)
        hooks.write_instructions.pop(NAME, None)


@no_type_check
def declare():
    class Person(Entity):
        _meta = Entity.Meta(
            create_inline=True,
            create_with_id=True,
            companions=[
                Companion(name="naming", document="Naming", entity_field="named")
            ],
        )

    class Naming(Document):
        named: Person

    class Letter(Document):
        _review_meta = ReviewMeta(reviewable=True)
        about: list[Person]

    initialise()
    return SimpleNamespace(Person=Person, Naming=Naming, Letter=Letter)


def distinct(asked: list) -> list:
    """Each question once, in the order first asked: a transaction that the driver runs again (a transient error,
    under load) asks again, and must be answered the same"""
    seen: list = []
    for question in asked:
        if question not in seen:
            seen.append(question)
    return seen


def ref(item) -> dict:
    return {"type": type(item)._owner.__name__, "id": item.id}


def marked(db_driver) -> set[str]:
    return {
        row["head"]
        for row in run(
            db_driver,
            "MATCH (p:PGPending {kind: $kind}) RETURN p.head_id AS head",
            kind=KIND,
        )
    }


def counts(db_driver) -> tuple[int, int]:
    """The nodes of the models, and the marks"""
    (row,) = run(
        db_driver,
        "MATCH (n) RETURN count(CASE WHEN n:PGIndexableNode THEN 1 END) AS nodes, "
        "count(CASE WHEN n:PGPending THEN 1 END) AS marks",
    )
    return row["nodes"], row["marks"]


def forget_marks(db_driver):
    db_driver.execute_query(
        "MATCH (p:PGPending) DETACH DELETE p", database_=DATABASE_NAME
    )


@no_type_check
async def test_a_create_and_an_update_are_marked_as_their_instruction_says(
    db_driver, clear_database, instructed
):
    m = declare()
    ann = await m.Person.Create(label="Ann").save(instructions={NAME: False})
    said = await m.Letter.Create(label="Said", about=[ref(ann)]).save(
        instructions={NAME: True}
    )
    told_not = await m.Letter.Create(label="Not", about=[ref(ann)]).save(
        instructions={NAME: "false"}
    )
    silent = await m.Letter.Create(label="Silent", about=[ref(ann)]).save()
    assert marked(db_driver) == {str(said.id)}
    # (asked with what each said, as text; with nothing said, with an empty mapping)
    assert distinct(instructed.asked) == [
        ("Person", {NAME: "false"}),
        ("Letter", {NAME: "true"}),
        ("Letter", {NAME: "false"}),
        ("Letter", {}),
    ]

    # an update, the same: and with nothing said, the setting decides
    await m.Letter.Update(id=told_not.id, label="Not now", about=[ref(ann)]).save(
        instructions={NAME: True}
    )
    instructed.setting.on = True
    await m.Letter.Update(id=silent.id, label="Silent", about=[ref(ann)]).save()
    assert marked(db_driver) == {str(said.id), str(told_not.id), str(silent.id)}
    # (the setting is the app's: a write that says nothing is asked all the same)
    assert instructed.asked[-1] == ("Letter", {})
    made = await m.Letter.Create(label="By the setting", about=[ref(ann)]).save()
    assert str(made.id) in marked(db_driver)


@no_type_check
async def test_false_takes_off_a_mark_an_earlier_write_left_and_a_refused_write_leaves_it(
    db_driver, clear_database, instructed
):
    m = declare()
    ann = await m.Person.Create(label="Ann").save()
    letter = await m.Letter.Create(label="L", about=[ref(ann)]).save(
        instructions={NAME: True}
    )
    assert marked(db_driver) == {str(letter.id)}

    # (a stale version: refused, and nothing of it is done, the mark's going neither)
    with pytest.raises(PanglossVersionConflictError):
        await m.Letter.Update(id=letter.id, label="L", about=[]).save(
            expected_version=7, instructions={NAME: False}
        )
    assert marked(db_driver) == {str(letter.id)}

    # claimed or not, it goes; whoever holds the claim then completes nothing
    database = backend.current().database()

    @database.write_transaction
    async def claim(tx):
        return await pending.claim(tx, KIND, 10, 60)

    claimed = await claim()
    assert [head for head, _ in claimed] == [str(letter.id)]
    await m.Letter.Update(id=letter.id, label="L", about=[ref(ann)]).save(
        expected_version=1, instructions={NAME: False}
    )
    assert marked(db_driver) == set()

    @database.write_transaction
    async def complete(tx):
        return await pending.complete(tx, KIND, claimed)

    assert await complete() == 0
    # (and a write that says nothing, with the setting off, leaves none)
    await m.Letter.Update(id=letter.id, label="L", about=[ref(ann)]).save()
    assert marked(db_driver) == set()


@no_type_check
async def test_an_entity_a_create_makes_is_asked_for_by_its_class(
    db_driver, clear_database, instructed
):
    m = declare()
    new = uuid7()
    letter = await m.Letter.Create(
        label="L",
        about=[{"type": "Person", "id": new, "label": "New", "create_new": True}],
    ).save(instructions={NAME: True})
    assert distinct(instructed.asked) == [
        ("Letter", {NAME: "true"}),
        ("Person", {NAME: "true"}),
    ]
    assert marked(db_driver) == {str(letter.id), str(new)}


@no_type_check
async def test_create_heads_and_save_with_companions_carry_them_to_each_head(
    db_driver, clear_database, instructed
):
    m = declare()
    ann = m.Person.Create(label="Ann")
    ann_db = ann._to_db_model()
    letter = m.Letter.Create(label="L", about=[{"type": "Person", "id": ann_db.id}])
    made = await create_heads(ann_db, letter, instructions={NAME: True})
    assert distinct(instructed.asked) == [
        ("Person", {NAME: "true"}),
        ("Letter", {NAME: "true"}),
    ]
    assert marked(db_driver) == {str(item.id) for item in made}

    forget_marks(db_driver)
    instructed.asked.clear()
    person, (naming,) = await m.Person.Create(label="Bo").save_with_companions(
        {"naming": {"label": "Bo named"}}, instructions={NAME: True}
    )
    assert distinct(instructed.asked) == [
        ("Person", {NAME: "true"}),
        ("Naming", {NAME: "true"}),
    ]
    assert marked(db_driver) == {str(person.id), str(naming.id)}


@no_type_check
async def test_what_no_app_declares_is_refused_before_anything_is_written(
    db_driver, clear_database, instructed
):
    m = declare()
    ann = await m.Person.Create(label="Ann").save()
    letter = await m.Letter.Create(label="L", about=[ref(ann)]).save(
        instructions={NAME: True}
    )
    before = counts(db_driver)
    instructed.asked.clear()

    with pytest.raises(PanglossInstructionError, match="'nonsense' is no instruction"):
        await m.Letter.Create(label="M", about=[ref(ann)]).save(
            instructions={"nonsense": True}
        )
    with pytest.raises(
        PanglossInstructionError, match="one of true, false, not 'maybe'"
    ):
        await m.Letter.Create(label="M", about=[ref(ann)]).save(
            instructions={NAME: "maybe"}
        )
    with pytest.raises(PanglossInstructionError, match="not 'maybe'"):
        await m.Letter.Update(id=letter.id, label="M", about=[]).save(
            instructions={NAME: "maybe"}
        )
    with pytest.raises(PanglossInstructionError):
        await create_heads(
            m.Person.Create(label="Bo"), instructions={"nonsense": "true"}
        )
    with pytest.raises(PanglossInstructionError):
        await m.Person.Create(label="Bo").save_with_companions(
            {"naming": {}}, instructions={NAME: 1}
        )
    with pytest.raises(PanglossInstructionError):
        await storage_of().operations.checked_create(
            m.Person.Create(label="Bo"), instructions={NAME: "maybe"}
        )
    assert counts(db_driver) == before
    assert marked(db_driver) == {str(letter.id)}
    assert instructed.asked == []
    assert (await m.Letter.get(letter.id)).label == "L"


@no_type_check
async def test_no_other_write_asks(db_driver, clear_database, instructed):
    m = declare()
    instructed.setting.on = True
    db_driver.execute_query(
        "MERGE (:PGUser {username: 'reviewer'})", database_=DATABASE_NAME
    )
    ann = await m.Person.Create(label="Ann").save()
    bo = await m.Person.Create(label="Bo").save()
    letter = await m.Letter.Create(label="L", about=[ref(ann), ref(bo)]).save()
    forget_marks(db_driver)
    instructed.asked.clear()

    await m.Letter.delete(letter.id)
    await m.Letter.undelete(letter.id)
    merged = await m.Person.merge(absorb=bo.id, into=ann.id)
    await m.Person.unmerge(merged.merge.id)
    await service.set_status(letter.id, ReviewStatus.PUBLISHED, "reviewer")
    await storage_of().operations.set_published_in_db(m.Letter, letter.id, False)
    assert instructed.asked == []
    # (what those writes mark is `pending_work`'s: the test's kind is the app's, and none of them touched it)
    assert marked(db_driver) == set()


@no_type_check
async def test_a_restore_is_an_update_that_says_nothing(
    db_driver,
    clear_database,
    instructed,
    history,  # noqa: F811
):
    m = declare()
    store = history()
    ann = await m.Person.Create(label="Ann").save()
    letter = await m.Letter.Create(label="L", about=[ref(ann)]).save()
    await m.Letter.Update(id=letter.id, label="L2", about=[ref(ann)]).save(
        instructions={NAME: True}
    )
    listener.get_recorder().drain()
    instructed.asked.clear()
    await restore(store, m.Letter, letter.id, 1)
    assert distinct(instructed.asked) == [("Letter", {})]


@no_type_check
async def test_nothing_that_copies_the_context_of_a_create_carries_its_instructions(
    db_driver, clear_database, instructed
):
    m = declare()
    ann = await m.Person.Create(label="Ann").save()
    bo = await m.Person.Create(label="Bo").save()
    copied: list[contextvars.Context] = []

    def listen(event):
        if event.op == "create" and event.model is m.Letter:
            copied.append(contextvars.copy_context())

    hooks.after_write.append(listen)
    try:
        await m.Letter.Create(label="L", about=[ref(ann), ref(bo)]).save(
            instructions={NAME: True}
        )
    finally:
        hooks.after_write.remove(listen)
    (context,) = copied
    forget_marks(db_driver)
    instructed.asked.clear()
    instructed.setting.on = False

    loop = asyncio.get_running_loop()
    merged = await loop.create_task(
        m.Person.merge(absorb=bo.id, into=ann.id), context=context
    )
    await loop.create_task(m.Person.unmerge(merged.merge.id), context=context.copy())
    lone = await m.Person.Create(label="Cy").save()
    instructed.asked.clear()
    await loop.create_task(m.Person.delete(lone.id), context=context.copy())
    assert instructed.asked == []
    assert marked(db_driver) == set()
    # (and a create in that context that says nothing is asked with nothing)
    await loop.create_task(
        m.Letter.Create(label="M", about=[ref(ann)]).save(), context=context.copy()
    )
    assert distinct(instructed.asked) == [("Letter", {})]
    assert marked(db_driver) == set()
