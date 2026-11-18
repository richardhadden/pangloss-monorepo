"""What the core does for a package that decides, itself, whether a document is published and what counts as a use
(`pangloss-derived`, for its derived documents): a change of whether a document is published leaves the work a write
of it leaves; a document of a class that is not reviewed can be unpublished; the references of some classes do not
count."""

from typing import no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_models import Document, Entity, Match, hooks, initialise
from pangloss_review import ReviewMeta, ReviewStatus, service
from pangloss_users import see_unpublished

from .helpers import DATABASE_NAME, run

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Person(Entity):
        pass

    class Letter(Document):
        _review_meta = ReviewMeta(reviewable=True)
        sender: Person

    class Summary(Document):
        """Not reviewed: something else says whether one is published"""

        about: list[Person]

    initialise()
    return Person, Letter, Summary


def make_user(db_driver, username):
    db_driver.execute_query(
        "MERGE (:PGUser {username: $username})",
        parameters_={"username": username},
        database=DATABASE_NAME,
    )


def pending(db_driver):
    return sorted(
        r["head"]
        for r in run(
            db_driver,
            "MATCH (p:PGPending {kind: 'test-work'}) RETURN p.head_id AS head",
        )
    )


def forget_pending(db_driver):
    db_driver.execute_query(
        "MATCH (p:PGPending) DETACH DELETE p", database=DATABASE_NAME
    )


@pytest.fixture
def listening():
    """Work asked of every write, and what is told of work marked by something that is not a write"""
    told = []
    work = lambda model: ["test-work"]  # noqa: E731
    hooks.pending_work.append(work)
    hooks.work_marked.append(told.append)
    yield told
    hooks.pending_work.remove(work)
    hooks.work_marked.remove(told.append)


@no_type_check
async def test_a_change_of_review_status_leaves_the_work_a_write_leaves(
    clear_database, db_driver, listening
):
    Person, Letter, Summary = models()
    make_user(db_driver, "reviewer")
    john = await Person.Create(label="John").save()
    letter = await Letter.Create(
        label="L", sender={"type": "Person", "id": john.id}
    ).save()
    assert str(letter.id) in pending(db_driver)
    forget_pending(db_driver)
    assert listening == []

    await service.set_status(letter.id, ReviewStatus.PUBLISHED, "reviewer")
    # (in the transaction of the change: the head is pending, and those who listen were told after it)
    assert pending(db_driver) == [str(letter.id)]
    assert listening == [Letter]
    forget_pending(db_driver)
    await service.set_status(letter.id, ReviewStatus.ERRORS_FOUND, "reviewer")
    assert pending(db_driver) == [str(letter.id)]
    assert listening == [Letter, Letter]
    # (a comment, or an assignment, changes nothing a reader sees: no work)
    forget_pending(db_driver)
    await service.add_comment(letter.id, "reviewer", "See the date")
    assert pending(db_driver) == []


@no_type_check
async def test_a_listener_to_marked_work_that_fails_does_not_fail_the_change(
    clear_database, db_driver, listening
):
    Person, Letter, Summary = models()
    make_user(db_driver, "reviewer")
    john = await Person.Create(label="John").save()
    letter = await Letter.Create(
        label="L", sender={"type": "Person", "id": john.id}
    ).save()

    def failing(model):
        raise RuntimeError("no")

    hooks.work_marked.insert(0, failing)
    try:
        state = await service.set_status(letter.id, ReviewStatus.PUBLISHED, "reviewer")
    finally:
        hooks.work_marked.remove(failing)
    assert state.published and listening == [Letter]


@no_type_check
async def test_a_document_of_a_class_that_is_not_reviewed_can_be_unpublished(
    clear_database, db_driver, listening
):
    Person, Letter, Summary = models()
    make_user(db_driver, "reviewer")
    john = await Person.Create(label="John").save()
    jane = await Person.Create(label="Jane").save()
    await Summary.Create(
        label="Shown", about=[{"type": "Person", "id": john.id}]
    ).save()
    hidden = await Summary.Create(
        label="Hidden", about=[{"type": "Person", "id": jane.id}]
    ).save()
    forget_pending(db_driver)
    operations = storage_of().operations

    assert await operations.set_published_in_db(Summary, hidden.id, False) is True
    assert pending(db_driver) == [str(hidden.id)]
    assert listening == [Summary]
    # (as it is already: nothing changed, nothing marked, nobody told)
    forget_pending(db_driver)
    assert await operations.set_published_in_db(Summary, hidden.id, False) is False
    assert pending(db_driver) == [] and listening == [Summary]
    # (not a document of the class named, or not there: nothing)
    assert await operations.set_published_in_db(Letter, hidden.id, True) is False
    assert await operations.set_published_in_db(Summary, john.id, False) is False

    token = see_unpublished.set(False)
    try:
        # (hidden from a reader who is not logged in, wherever it would be met)
        assert [s.label for s in (await Summary.list()).results] == ["Shown"]
        assert await Summary.get(hidden.id) is None
        assert [s.label for s in (await Summary.search(Match(where={}))).results] == [
            "Shown"
        ]
        incoming = await Person.search(
            Match(where={"$incoming": [{"type": "Summary", "where": {}}]})
        )
        assert [p.label for p in incoming.results] == ["John"]
        see_unpublished.set(True)
        assert len((await Summary.list()).results) == 2
        # (found by the filter of a list)
        assert [s.label for s in (await Summary.list(published=False)).results] == [
            "Hidden"
        ]
        assert [s.label for s in (await Summary.list(published=True)).results] == [
            "Shown"
        ]
    finally:
        see_unpublished.reset(token)

    # (it has no review status: it is not among what is to be reviewed, in any state, and review does not take it)
    for status in ReviewStatus:
        queued = await service.queue(statuses=[status])
        assert [item.id for item in queued.results] == []
    rows = run(
        db_driver,
        "MATCH (h:HeadNode {id: $id}) RETURN h.review_status AS status, h.published AS published",
        id=str(hidden.id),
    )
    assert rows == [{"status": None, "published": False}]

    # (an update keeps it unpublished)
    await Summary.Update(id=hidden.id, label="Hidden still", about=[]).save()
    token = see_unpublished.set(False)
    try:
        assert await Summary.get(hidden.id) is None
    finally:
        see_unpublished.reset(token)
    assert await operations.set_published_in_db(Summary, hidden.id, True) is True
    token = see_unpublished.set(False)
    try:
        assert (await Summary.get(hidden.id)).label == "Hidden still"
    finally:
        see_unpublished.reset(token)


@no_type_check
async def test_the_references_of_some_classes_do_not_count(clear_database, db_driver):
    Person, Letter, Summary = models()
    john = await Person.Create(label="John").save()
    jane = await Person.Create(label="Jane").save()
    ref = lambda p: {"type": "Person", "id": p.id}  # noqa: E731
    await Letter.Create(label="L", sender=ref(john)).save(published=True)
    summary = await Summary.Create(label="S", about=[ref(john), ref(jane)]).save()
    operations = storage_of().operations

    async def uses():
        listed = await Person.list(use_counts=True)
        return {p.label: listed.use_counts[str(p.id)] for p in listed.results}, sorted(
            p.label for p in (await Person.list(used_only=True)).results
        )

    assert await uses() == ({"John": 2, "Jane": 1}, ["Jane", "John"])
    check = await operations.check_deletable(Person, jane.id)
    assert not check.deletable and check.reference_count == 1

    uncounted = lambda: ["Summary"]  # noqa: E731
    hooks.references_not_counted.append(uncounted)
    try:
        assert hooks.uncounted_classes() == ["Summary"]
        # (what only a summary names is not used; what a letter names as well is used once)
        assert await uses() == ({"John": 1, "Jane": 0}, ["John"])
        searched = await Person.search(Match(where={}), used_only=True)
        assert [p.label for p in searched.results] == ["John"]
        check = await operations.check_deletable(Person, jane.id)
        assert check.deletable
        check = await operations.check_deletable(Person, john.id)
        assert not check.deletable and check.reference_count == 1
        assert [r["type"] for r in check.referenced_by] == ["Letter"]
        # (and it is deleted, though the summary still names it)
        await Person.delete(jane.id)
        assert await Person.get(jane.id) is None
        assert (await Summary.get(summary.id)) is not None
    finally:
        hooks.references_not_counted.remove(uncounted)
    assert hooks.uncounted_classes() == []
    assert (await uses())[0] == {"John": 2}
