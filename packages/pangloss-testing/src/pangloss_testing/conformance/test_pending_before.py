"""What the mark of an update keeps of the tree it replaced (`hooks.pending_keeps_before`, `pangloss_cypher.pending`):
the ids of the entities the old tree referred to (`before_refs`) and the labels of its nodes (`before_labels`), for
the kinds of work that ask, joined with what the mark already had (implementation_docs/matches-criteria.md, "1.
Marking": "What an update took away")."""

from typing import Annotated, no_type_check

import pytest
from pangloss_core import backend, storage_of
from pangloss_cypher import pending
from pangloss_models import (
    Computed,
    Document,
    Entity,
    ReifiedRelation,
    hooks,
    initialise,
)

from .helpers import DATABASE_NAME, run

pytestmark = pytest.mark.asyncio(loop_scope="session")

KEEPS, PLAIN = "keeps-before", "plain-work"


def models():
    class Place(Entity):
        pass

    class Person(Entity):
        born_in: Place | None = None

    class Office(Entity):
        pass

    class Guess[T](ReifiedRelation[T]):
        """Someone the source does not name: what the server finds is computed"""

        target: Annotated[list[T], Computed()] = []

    class InRole[T](ReifiedRelation[T]):
        role: Office | None = None

    class Statement(Document):
        _meta = Document.Meta(create_directly=False)
        about: Person

    class Remark(Document):
        _meta = Document.Meta(create_directly=False)
        text: str = ""

    class Record(Document):
        _meta = Document.Meta(abstract=True)
        by: list[Person | Guess[Person]]
        roles: list[InRole[Person]]
        at: Place | None = None
        parts: list[Statement | Remark]

    class Draft(Record):
        pass

    class Act(Record):
        pass

    initialise()
    return Person, Place, Office, Draft, Act


def ref(item):
    return {"type": type(item)._owner.__name__, "id": item.id}


@pytest.fixture
def keeping():
    """Two kinds of work asked of every write: one keeps what an update took away, the other does not"""
    kinds = lambda model: [KEEPS, PLAIN]  # noqa: E731
    kept = set(hooks.pending_keeps_before)
    hooks.pending_work.append(kinds)
    hooks.pending_keeps_before.clear()
    hooks.pending_keeps_before.add(KEEPS)
    yield
    hooks.pending_work.remove(kinds)
    hooks.pending_keeps_before.clear()
    hooks.pending_keeps_before.update(kept)


def mark_of(db_driver, kind, head_id) -> dict:
    """The mark's lists, as sets (None where the mark has no such property), and whether either has repeats"""
    rows = run(
        db_driver,
        "MATCH (p:PGPending {key: $key}) RETURN p.before_refs AS refs, p.before_labels AS labels",
        key=pending.key_of(kind, str(head_id)),
    )
    assert len(rows) == 1, f"no mark {kind} of {head_id}"
    (row,) = rows
    for key in ("refs", "labels"):
        if row[key] is not None:
            assert len(row[key]) == len(set(row[key])), f"{key} has repeats"
    return {
        key: None if row[key] is None else set(row[key]) for key in ("refs", "labels")
    }


def forget_marks(db_driver):
    db_driver.execute_query(
        "MATCH (p:PGPending) DETACH DELETE p", database=DATABASE_NAME
    )


def ids(*items) -> set[str]:
    return {str(item.id) for item in items}


def entities(db_driver, refs) -> set[str]:
    """Those of the ids kept that are entities. (The mark keeps every node the old tree had a relation to: the
    nodes of the tree itself too, of which a stand-in for an entity is one.)"""
    rows = run(
        db_driver,
        "UNWIND $ids AS id MATCH (e:Entity {id: id}) RETURN e.id AS id",
        ids=sorted(refs),
    )
    return {row["id"] for row in rows}


async def people(Person, *names):
    return [await Person.Create(label=name).save() for name in names]


@no_type_check
async def an_act(Act, Office, *, by, in_role, at, about):
    office = await Office.Create(label="Secretary").save()
    act = await Act.Create(
        label="An act",
        by=[ref(by), {"type": "Guess"}],
        roles=[{"type": "InRole", "target": [ref(in_role)], "role": ref(office)}],
        at=ref(at),
        parts=[
            {"type": "Statement", "label": "About", "about": ref(about)},
            {"type": "Remark", "label": "A remark", "text": "!"},
        ],
    ).save(detail=True)
    return act, office


@no_type_check
async def emptied(Act, act, *by):
    """The act updated to be by these people alone, and nothing else"""
    return await Act.Update(
        id=act.id, label="An act", by=[ref(p) for p in by], roles=[], parts=[]
    ).save()


def database():
    return backend.current().database()


# --- what an update keeps -----------------------------------------------------------------------------------------------


@no_type_check
async def test_an_update_keeps_what_the_old_tree_referred_to_and_its_labels(
    clear_database, db_driver, keeping
):
    Person, Place, Office, Draft, Act = models()
    john, ann, bob, carl = await people(Person, "John", "Ann", "Bob", "Carl")
    paris = await Place.Create(label="Paris").save()
    act, office = await an_act(Act, Office, by=john, in_role=ann, at=paris, about=bob)
    # (a create keeps nothing)
    assert mark_of(db_driver, KEEPS, act.id) == {"refs": None, "labels": None}

    await emptied(Act, act, carl)

    mark = mark_of(db_driver, KEEPS, act.id)
    # (from the head, from inside a wrapper with what the wrapper refers to, and from a nested document; not what
    # the new tree refers to)
    assert entities(db_driver, mark["refs"]) == ids(john, ann, office, paris, bob)
    # (the labels of every node of the old tree, among them the classes the update took away)
    assert {"Act", "Record", "Statement", "Remark", "InRole", "Guess"} <= mark["labels"]
    # (a kind that does not ask has neither)
    assert mark_of(db_driver, PLAIN, act.id) == {"refs": None, "labels": None}


@no_type_check
async def test_two_updates_before_a_claim_join_their_lists_without_repeats(
    clear_database, db_driver, keeping
):
    Person, Place, Office, Draft, Act = models()
    john, ann, bob, carl, dan = await people(
        Person, "John", "Ann", "Bob", "Carl", "Dan"
    )
    paris = await Place.Create(label="Paris").save()
    act, office = await an_act(Act, Office, by=john, in_role=ann, at=paris, about=bob)

    await emptied(Act, act, carl, john)
    await emptied(Act, act, dan, john)

    mark = mark_of(db_driver, KEEPS, act.id)
    assert entities(db_driver, mark["refs"]) == ids(john, ann, office, paris, bob, carl)
    assert {"Act", "Statement", "Remark", "InRole"} <= mark["labels"]


@no_type_check
async def test_after_the_mark_is_completed_a_new_one_starts_empty(
    clear_database, db_driver, keeping
):
    Person, Place, Office, Draft, Act = models()
    john, ann, bob, carl, dan = await people(
        Person, "John", "Ann", "Bob", "Carl", "Dan"
    )
    paris = await Place.Create(label="Paris").save()
    act, office = await an_act(Act, Office, by=john, in_role=ann, at=paris, about=bob)
    await emptied(Act, act, carl)
    db = database()

    @db.write_transaction
    async def claim_and_complete(tx):
        claimed = await pending.claim(tx, KEEPS, 100, 30)
        return await pending.complete(tx, KEEPS, claimed)

    assert await claim_and_complete() >= 1

    await emptied(Act, act, dan)
    mark = mark_of(db_driver, KEEPS, act.id)
    assert entities(db_driver, mark["refs"]) == ids(carl)
    assert "Statement" not in mark["labels"] and "Act" in mark["labels"]


@no_type_check
async def test_a_create_a_delete_and_an_undelete_keep_nothing(
    clear_database, db_driver, keeping
):
    Person, Place, Office, Draft, Act = models()
    john, ann, bob = await people(Person, "John", "Ann", "Bob")
    paris = await Place.Create(label="Paris").save()
    act, _ = await an_act(Act, Office, by=john, in_role=ann, at=paris, about=bob)
    assert mark_of(db_driver, KEEPS, act.id) == {"refs": None, "labels": None}

    forget_marks(db_driver)
    await Act.delete(act.id)
    assert mark_of(db_driver, KEEPS, act.id) == {"refs": None, "labels": None}

    forget_marks(db_driver)
    await Act.undelete(act.id)
    assert mark_of(db_driver, KEEPS, act.id) == {"refs": None, "labels": None}


@no_type_check
async def test_an_update_of_an_entity_keeps_what_it_referred_to(
    clear_database, db_driver, keeping
):
    Person, Place, Office, Draft, Act = models()
    paris = await Place.Create(label="Paris").save()
    john = await Person.Create(label="John", born_in=ref(paris)).save()

    await Person.Update(id=john.id, label="John", born_in=None).save()

    mark = mark_of(db_driver, KEEPS, john.id)
    assert entities(db_driver, mark["refs"]) == ids(paris)
    assert "Person" in mark["labels"]


@no_type_check
async def test_a_change_of_class_keeps_the_labels_of_the_class_it_was(
    clear_database, db_driver, keeping
):
    Person, Place, Office, Draft, Act = models()
    john, ann, bob = await people(Person, "John", "Ann", "Bob")
    draft = await Draft.Create(
        label="A draft",
        by=[ref(john)],
        roles=[],
        parts=[{"type": "Statement", "label": "About", "about": ref(bob)}],
    ).save()

    await Act.Update(
        id=draft.id, label="An act", by=[ref(ann)], roles=[], parts=[]
    ).save(changing_class_from=Draft)

    mark = mark_of(db_driver, KEEPS, draft.id)
    assert {"Draft", "Record", "Statement"} <= mark["labels"]
    assert "Act" not in mark["labels"]
    assert entities(db_driver, mark["refs"]) == ids(john, bob)


@no_type_check
async def test_what_is_computed_is_not_what_the_old_tree_referred_to(
    clear_database, db_driver, keeping
):
    Person, Place, Office, Draft, Act = models()
    john, ann, bob, eve = await people(Person, "John", "Ann", "Bob", "Eve")
    paris = await Place.Create(label="Paris").save()
    act, office = await an_act(Act, Office, by=john, in_role=ann, at=paris, about=bob)
    guess = next(item for item in act.by if item.type == "Guess")
    assert await storage_of().operations.set_computed(guess.id, {"target": [eve.id]})
    forget_marks(db_driver)

    await emptied(Act, act, john)

    assert str(eve.id) not in mark_of(db_driver, KEEPS, act.id)["refs"]


# --- only when a kind asks ----------------------------------------------------------------------------------------------


@no_type_check
async def test_a_kind_that_asks_is_given_what_was_before_and_one_that_does_not_is_not(
    clear_database, db_driver, keeping
):
    Person, Place, Office, Draft, Act = models()
    john, ann, bob = await people(Person, "John", "Ann", "Bob")
    paris = await Place.Create(label="Paris").save()
    act, _ = await an_act(Act, Office, by=john, in_role=ann, at=paris, about=bob)

    await emptied(Act, act, ann)

    assert mark_of(db_driver, KEEPS, act.id)["refs"] is not None
    assert mark_of(db_driver, PLAIN, act.id) == {"refs": None, "labels": None}


@no_type_check
async def test_with_no_kind_asking_an_update_reads_nothing_more(
    clear_database, db_driver, keeping, monkeypatch
):
    Person, Place, Office, Draft, Act = models()
    john, ann, bob = await people(Person, "John", "Ann", "Bob")
    paris = await Place.Create(label="Paris").save()
    act, _ = await an_act(Act, Office, by=john, in_role=ann, at=paris, about=bob)
    assert pending.keeps_before(Act) is True
    hooks.pending_keeps_before.discard(KEEPS)

    async def not_read(tx, head_id):
        raise AssertionError("the old tree was read")

    monkeypatch.setattr(pending, "tree_before", not_read)

    assert pending.keeps_before(Act) is False
    assert pending.keeps_before(Act, Draft) is False
    await emptied(Act, act, ann)
    assert mark_of(db_driver, KEEPS, act.id) == {"refs": None, "labels": None}
    assert mark_of(db_driver, PLAIN, act.id) == {"refs": None, "labels": None}


@pytest.fixture
def no_kinds():
    """The kinds of work, and those that keep what was before, as the test sets them; given back after"""
    work, kept = list(hooks.pending_work), set(hooks.pending_keeps_before)
    hooks.pending_work.clear()
    hooks.pending_keeps_before.clear()
    yield
    hooks.pending_work[:] = work
    hooks.pending_keeps_before.clear()
    hooks.pending_keeps_before.update(kept)


async def test_whether_a_write_keeps_what_was_before_is_asked_of_each_class(no_kinds):
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    initialise()
    # (no work asked at all: nothing kept, whatever the kinds that would keep it)
    hooks.pending_keeps_before.add(KEEPS)
    assert pending.keeps_before(Person) is False

    hooks.pending_work.append(lambda model: [KEEPS] if model is Person else [PLAIN])
    assert pending.keeps_before(Person) is True
    assert pending.keeps_before(Place) is False
    # (an update that changes the class asks of the class it was too)
    assert pending.keeps_before(Place, Person) is True
    assert pending.keeps_before(Place, None) is False
    hooks.pending_keeps_before.clear()
    assert pending.keeps_before(Person) is False


# --- the worker reads it ------------------------------------------------------------------------------------------------


@no_type_check
async def test_before_of_gives_what_the_marks_keep_and_leaves_out_those_that_keep_nothing(
    clear_database, db_driver, keeping
):
    Person, Place, Office, Draft, Act = models()
    john, ann, bob = await people(Person, "John", "Ann", "Bob")
    paris = await Place.Create(label="Paris").save()
    updated, office = await an_act(
        Act, Office, by=john, in_role=ann, at=paris, about=bob
    )
    created = await Act.Create(label="New", by=[], roles=[], parts=[]).save()
    await emptied(Act, updated, ann)
    db = database()

    @db.read_transaction
    async def read(tx):
        return (
            await pending.before_of(tx, KEEPS, [updated.id, created.id]),
            await pending.before_of(tx, PLAIN, [updated.id, created.id]),
            await pending.before_of(tx, KEEPS, []),
        )

    keeps, plain, nothing = await read()

    assert list(keeps) == [str(updated.id)]
    before = keeps[str(updated.id)]
    assert entities(db_driver, before.refs) == ids(john, ann, office, paris, bob)
    assert {"Act", "Statement", "Remark", "InRole"} <= before.labels
    assert plain == {} and nothing == {}
