"""`hooks.resolved` raised by `pangloss-review`: once for each mention reconciled, after its document is written (the
one asked about `direct`, the others reconciled with it not); never for a mention reconciled in a form; nothing for a
reconciliation that fails; a listener that fails does not fail it, and a listener may write to the database"""

import contextlib
import datetime
import logging
from typing import no_type_check
from uuid import UUID, uuid4

import pytest
from pangloss_core import backend
from pangloss_models import hooks
from pangloss_review import PanglossReconcileError, reconcile
from pangloss_users import current_request_username

from .helpers import DATABASE_NAME, run
from .test_reconcile_live import factoid, mention, models

pytestmark = pytest.mark.asyncio(loop_scope="session")


@contextlib.contextmanager
def listening(listener):
    hooks.resolved.append(listener)
    try:
        yield
    finally:
        hooks.resolved.remove(listener)


@contextlib.contextmanager
def as_user(db_driver, username: str):
    db_driver.execute_query(
        "MERGE (:PGUser {username: $username})",
        parameters_={"username": username},
        database_=DATABASE_NAME,
    )
    token = current_request_username.set(username)
    try:
        yield
    finally:
        current_request_username.reset(token)


@no_type_check
async def test_a_reconciliation_tells_who_put_what_in_the_place_of_which_mention(
    clear_database, db_driver
):
    m = models()
    john = await m.Person.Create(label="John Smith (1570-1630)").save()
    made = await m.Factoid.Create(
        label="F",
        statements=[
            {
                "type": "Activity",
                "label": "a",
                "by": [mention("John Smith", uris=["http://example.org/new"])],
            }
        ],
    ).save(detail=True)
    first = made.statements[0].by[0].id
    told = []

    async def listen(resolution):
        # (after the document's write, before the URIs are given)
        document = await m.Factoid.get(resolution.head_id)
        person = await m.Person.get(john.id)
        told.append((resolution, document.meta.version, list(person.urls)))

    before = datetime.datetime.now(datetime.UTC)
    with listening(listen), as_user(db_driver, "ann"):
        await reconcile.reconcile(first, "Person", john.id)
    after = datetime.datetime.now(datetime.UTC)

    ((resolution, version, urls),) = told
    assert resolution == hooks.Resolution(
        stand_in_id=first,
        stand_in_type="Unreconciled",
        head_id=made.id,
        head_type="Factoid",
        entity_id=john.id,
        entity_type="Person",
        user="ann",
        at=resolution.at,
        direct=True,
        label="John Smith",
        stood_for="Person",
    )
    assert isinstance(resolution.stand_in_id, UUID)
    assert isinstance(resolution.head_id, UUID)
    assert before <= resolution.at <= after
    assert (version, urls) == (2, [])
    assert [str(u) for u in (await m.Person.get(john.id)).urls] == [
        "http://example.org/new"
    ]


@no_type_check
async def test_each_other_mention_reconciled_with_it_is_told_not_direct(
    clear_database, db_driver
):
    m = models(rule=None)
    john = await m.Person.Create(label="John Smith (1570-1630)").save()
    one = await factoid(m, "One", "John Smith", "John Smith")
    two = await factoid(m, "Two", "john smith")
    first, same_document = (part.id for part in one.statements[0].by)
    other = two.statements[0].by[0].id
    told = []

    async def listen(resolution):
        told.append(resolution)

    with listening(listen), as_user(db_driver, "ann"):
        await reconcile.reconcile(
            first, "Person", john.id, also=[same_document, other, uuid4()]
        )
        await reconcile.background_done()

    assert [(r.stand_in_id, r.head_id, r.direct) for r in told] == [
        (first, one.id, True),
        (same_document, one.id, False),
        (other, two.id, False),
    ]
    # (in the background as the user of the request)
    assert {(r.user, r.entity_id, r.label) for r in told} == {
        ("ann", john.id, "John Smith"),
        ("ann", john.id, "john smith"),
    }


@no_type_check
async def test_a_mention_reconciled_in_a_form_is_not_told_but_one_elsewhere_is(
    clear_database, db_driver
):
    m = models(rule=None)
    john = await m.Person.Create(label="John Smith (1570-1630)").save()
    one = await factoid(m, "One", "John Smith", "John Smith")
    two = await factoid(m, "Two", "john smith")
    first, same_document = (part.id for part in one.statements[0].by)
    other = two.statements[0].by[0].id
    told = []

    async def listen(resolution):
        told.append(resolution)

    with listening(listen):
        await reconcile.reconcile(
            first, "Person", john.id, also=[same_document, other], in_form=True
        )
        await reconcile.background_done()

    # (the form's own document is not written here: of it nothing is said)
    assert [(r.stand_in_id, r.head_id, r.direct) for r in told] == [
        (other, two.id, False)
    ]


@no_type_check
async def test_mentions_reconciled_with_what_something_else_says_are_not_direct(
    clear_database, db_driver
):
    m = models(rule=None)
    john = await m.Person.Create(label="John Smith (1570-1630)").save()
    one = await factoid(m, "One", "John Smith")
    two = await factoid(m, "Two", "J. Smith")
    mentions = [one.statements[0].by[0].id, two.statements[0].by[0].id]
    told = []

    async def listen(resolution):
        told.append(resolution)

    with listening(listen):
        assert await reconcile.reconcile_with(mentions, "Person", john.id) == 2
        await reconcile.background_done()
    assert sorted((r.label, r.direct, r.entity_type) for r in told) == [
        ("J. Smith", False, "Person"),
        ("John Smith", False, "Person"),
    ]


@no_type_check
async def test_a_reconciliation_that_fails_tells_nothing(clear_database, db_driver):
    m = models()
    group = await m.Group.Create(label="A guild").save()
    one = await factoid(m, "One", "John Smith")
    first = one.statements[0].by[0].id
    told = []

    async def listen(resolution):
        told.append(resolution)

    with listening(listen):
        with pytest.raises(PanglossReconcileError, match="There is no Person"):
            await reconcile.reconcile(first, "Person", uuid4())
        with pytest.raises(PanglossReconcileError, match="cannot take the place"):
            await reconcile.reconcile(first, "Group", group.id)
        await reconcile.background_done()
    assert told == []
    assert (await m.Factoid.get(one.id)).meta.version == 1


@no_type_check
async def test_a_listener_that_fails_does_not_fail_the_reconciliation(
    clear_database, db_driver, caplog
):
    m = models()
    john = await m.Person.Create(label="John Smith (1570-1630)").save()
    one = await factoid(m, "One", "John Smith")
    first = one.statements[0].by[0].id

    async def failing(resolution):
        raise RuntimeError("no")

    with (
        listening(failing),
        caplog.at_level(logging.ERROR, logger="pangloss.models.hooks"),
    ):
        done = await reconcile.reconcile(first, "Person", john.id)
    assert done.entity.id == john.id
    read = await m.Factoid.get(one.id)
    assert (read.meta.version, read.statements[0].by[0].id) == (2, john.id)
    (record,) = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert str(first) in record.getMessage()


@no_type_check
async def test_a_listener_may_write_to_the_database(clear_database, db_driver):
    m = models()
    john = await m.Person.Create(label="John Smith (1570-1630)").save()
    one = await factoid(m, "One", "John Smith")
    first = one.statements[0].by[0].id

    async def keep(resolution):
        database = backend.current().database()

        @database.write_transaction
        async def write(tx):
            await (
                await tx.run(
                    "CREATE (:PGResolvedForTest {stand_in: $stand_in, entity: $entity})",
                    stand_in=str(resolution.stand_in_id),
                    entity=str(resolution.entity_id),
                )
            ).consume()

        await write()

    with listening(keep):
        await reconcile.reconcile(first, "Person", john.id)
    rows = run(db_driver, "MATCH (n:PGResolvedForTest) RETURN n")
    assert [(row["n"]["stand_in"], row["n"]["entity"]) for row in rows] == [
        (str(first), str(john.id))
    ]
