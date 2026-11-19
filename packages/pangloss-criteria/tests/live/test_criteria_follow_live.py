"""The worker follows the writes of other documents (implementation_docs/matches-criteria.md, "The worker", step 5):
a description in an Activity that was evaluated once keeps up with what is written elsewhere, without its Activity
being saved again. Its version stays 1 throughout."""

import asyncio
import importlib
from typing import no_type_check

import pangloss_criteria.models
import pytest
from criteria_court_support import (
    Court,
    candidates,
    description_of,
    ref,
    run_database,
    secretary_of,
)
from pangloss_core import storage_of
from pangloss_criteria import run_pending, settled
from pangloss_criteria.worker import (
    Worker,
    is_pending,
    out_of_date,
    pending_status,
    worker,
)
from pangloss_cypher import pending
from pangloss_models import Document, Entity, hooks, initialise
from pangloss_testing.live import run
from pangloss_users import see_unpublished

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models(review_meta=None):
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Person(Entity):
        title: str | None = None

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        if review_meta is not None:
            _review_meta = review_meta
        holder: list[Person | MatchesCriteria[Person]]
        office: Office
        employer: Person

    class Other(Document):
        _meta = Document.Meta(create_directly=False)
        about: list[Person]

    class Factoid(Document):
        """Holds an office as a statement of its own"""

        statements: list[HoldsOffice | Other]

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]
        witnessed_by: list[Person]

    class Note(Document):
        """Of a person, and touched by no criteria"""

        about: list[Person]

    initialise()
    return Person, Office, HoldsOffice, Factoid, Activity, Note


class Followed(Court):
    """Maximilian's court, and an activity of someone described as his secretary, evaluated once"""

    activity: object

    async def candidates(self) -> list[str]:
        read = await self.Activity.get(self.activity.id)
        # (it was not saved again)
        assert read.meta.version == 1
        return candidates(read)

    async def description(self):
        return description_of(await self.Activity.get(self.activity.id))

    async def update(self, document, **changes):
        """An update of a `HoldsOffice`, with what changes"""
        read = await self.HoldsOffice.get(document.id)
        payload = {
            "id": read.id,
            "label": read.label,
            "holder": [ref(p) for p in read.holder],
            "office": ref(read.office),
            "employer": ref(read.employer),
            **changes,
        }
        return await self.HoldsOffice.Update(**payload).save()


@no_type_check
async def a_court(*secretaries, criteria=None, review_meta=None) -> Followed:
    Person, Office, HoldsOffice, Factoid, Activity, Note = models(review_meta)
    court = Followed(Person, Office, HoldsOffice, Activity)
    court.Factoid, court.Note = Factoid, Note
    await court.office("Secretary")
    await court.person("Maximilian")
    for name in secretaries:
        await court.holds(name)
    court.activity = await court.described(criteria=criteria)
    await run_pending()
    return court


def stats():
    return dict(vars(worker.stats))


def grew(before, *keys) -> dict[str, int]:
    now = vars(worker.stats)
    return {key: now[key] - before[key] for key in keys}


@pytest.fixture(autouse=True)
def no_work_left(clear_database):
    yield
    worker.settings.batch = 200


# --- a document that holds an office ----------------------------------------------------------------------------------


@no_type_check
async def test_a_new_document_that_holds_the_office_is_followed(clear_database):
    court = await a_court("Waldauf")
    assert await court.candidates() == ["Waldauf"]
    before = stats()

    await court.holds("Serntein")
    assert await court.candidates() == ["Waldauf"]
    await run_pending()

    assert await court.candidates() == ["Serntein", "Waldauf"]
    assert (await court.description()).candidate_count == 2
    assert grew(before, "chosen", "unchanged") == {"chosen": 1, "unchanged": 0}


@no_type_check
async def test_settled_on_the_document_that_holds_the_office_waits_for_the_description(
    clear_database,
):
    court = await a_court("Waldauf")
    running = Worker()
    task = asyncio.create_task(running.run())
    hooks.after_write.append(running.listen)
    try:
        held = await court.holds("Serntein")
        await settled(held.id, timeout=10)
        assert await court.candidates() == ["Serntein", "Waldauf"]
    finally:
        hooks.after_write.remove(running.listen)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@no_type_check
async def test_an_update_to_another_holder_loses_one_and_gains_the_other(
    clear_database,
):
    court = await a_court("Waldauf")
    held = await court.holds("Serntein")
    await run_pending()

    await court.update(held, holder=[ref(await court.person("Lang"))])
    await run_pending()

    assert await court.candidates() == ["Lang", "Waldauf"]


@no_type_check
async def test_an_update_to_another_employer_loses_the_holder(clear_database):
    court = await a_court("Waldauf")
    held = await court.holds("Serntein")
    await run_pending()

    await court.update(held, employer=ref(await court.person("Sigismund")))
    await run_pending()

    assert await court.candidates() == ["Waldauf"]
    assert (await court.description()).candidate_count == 1


@no_type_check
async def test_a_delete_loses_the_holder_and_an_undelete_gains_them_again(
    clear_database,
):
    court = await a_court("Waldauf")
    held = await court.holds("Serntein")
    await run_pending()

    await court.HoldsOffice.delete(held.id)
    await run_pending()
    assert await court.candidates() == ["Waldauf"]

    await court.HoldsOffice.undelete(held.id)
    await run_pending()
    assert await court.candidates() == ["Serntein", "Waldauf"]


# --- nested in another document ---------------------------------------------------------------------------------------


@no_type_check
async def nested(court, holder="Kurz"):
    """A factoid that says, among other things, that someone is Maximilian's secretary"""
    return await court.Factoid.Create(
        label="A factoid",
        statements=[
            {
                "type": "HoldsOffice",
                "label": f"{holder} is secretary",
                "holder": [ref(await court.person(holder))],
                "office": ref(await court.office("Secretary")),
                "employer": ref(await court.person("Maximilian")),
            },
            {
                "type": "Other",
                "label": "Other",
                "about": [ref(await court.person("Eck"))],
            },
        ],
    ).save()


@no_type_check
async def without_the_office(court, factoid):
    """The factoid saved again with its statement of the office taken out: the new tree has no `HoldsOffice`"""
    return await court.Factoid.Update(
        id=factoid.id,
        label="A factoid",
        statements=[
            {
                "type": "Other",
                "label": "Other",
                "about": [ref(court.people["Eck"]), ref(court.people["Kurz"])],
            }
        ],
    ).save()


@no_type_check
async def test_an_office_held_in_a_statement_of_another_document_is_followed(
    clear_database,
):
    court = await a_court("Waldauf")
    factoid = await nested(court)
    await run_pending()
    assert await court.candidates() == ["Kurz", "Waldauf"]

    # (nothing of the factoid now is of a class the criteria touch: what it was before says it may matter)
    await without_the_office(court, factoid)
    await run_pending()

    assert await court.candidates() == ["Waldauf"]


@no_type_check
async def test_without_what_the_mark_kept_of_the_tree_before_the_statement_taken_out_is_missed(
    clear_database, monkeypatch
):
    court = await a_court("Waldauf")
    factoid = await nested(court)
    await run_pending()

    async def kept_nothing(tx, kind, head_ids):
        return {}

    monkeypatch.setattr(pending, "before_of", kept_nothing)
    await without_the_office(court, factoid)
    await run_pending()

    # (this is what `before_labels` is for)
    assert await court.candidates() == ["Kurz", "Waldauf"]
    assert await out_of_date() == [str((await court.description()).id)]


# --- published or not -------------------------------------------------------------------------------------------------


def seen(db_driver) -> list[dict]:
    return run(
        db_driver,
        "MATCH (:MatchesCriteria)-[e:target]->(p) RETURN p.label AS label, e.seen_by AS seen_by ORDER BY label",
    )


def counts(db_driver) -> dict:
    (row,) = run(
        db_driver,
        "MATCH (d:MatchesCriteria) RETURN d.candidate_count AS all, d.candidate_count_everyone AS everyone",
    )
    return row


@no_type_check
async def test_a_change_of_whether_the_document_is_published_is_followed(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    held = await court.holds("Serntein")
    await run_pending()
    assert counts(db_driver) == {"all": 2, "everyone": 2}

    await storage_of().operations.set_published_in_db(court.HoldsOffice, held.id, False)
    assert await is_pending(held.id)
    await run_pending()

    assert seen(db_driver) == [
        {"label": "Serntein", "seen_by": "logged_in"},
        {"label": "Waldauf", "seen_by": None},
    ]
    assert counts(db_driver) == {"all": 2, "everyone": 1}
    token = see_unpublished.set(False)
    try:
        assert candidates(await court.Activity.get(court.activity.id)) == ["Waldauf"]
    finally:
        see_unpublished.reset(token)

    await storage_of().operations.set_published_in_db(court.HoldsOffice, held.id, True)
    await run_pending()

    assert [row["seen_by"] for row in seen(db_driver)] == [None, None]
    assert counts(db_driver) == {"all": 2, "everyone": 2}
    assert await court.candidates() == ["Serntein", "Waldauf"]


@no_type_check
async def test_a_change_of_review_status_is_followed(clear_database, db_driver):
    review = pytest.importorskip("pangloss_review")
    from pangloss_review import service

    court = await a_court(review_meta=review.ReviewMeta(reviewable=True))
    db_driver.execute_query(
        "MERGE (:PGUser {username: 'reviewer'})", database_=run_database()
    )
    # (a document that is reviewed starts unpublished)
    held = await court.holds("Serntein")
    await run_pending()
    assert seen(db_driver) == [{"label": "Serntein", "seen_by": "logged_in"}]
    assert counts(db_driver) == {"all": 1, "everyone": 0}

    await service.set_status(held.id, review.ReviewStatus.PUBLISHED, "reviewer")
    await run_pending()
    assert seen(db_driver) == [{"label": "Serntein", "seen_by": None}]
    assert counts(db_driver) == {"all": 1, "everyone": 1}

    await service.set_status(held.id, review.ReviewStatus.ERRORS_FOUND, "reviewer")
    await run_pending()
    assert seen(db_driver) == [{"label": "Serntein", "seen_by": "logged_in"}]
    assert counts(db_driver) == {"all": 1, "everyone": 0}
    assert await court.candidates() == ["Serntein"]


# --- merges -----------------------------------------------------------------------------------------------------------


@no_type_check
async def test_the_entity_the_criteria_name_merged_into_another_with_secretaries_of_their_own(
    clear_database,
):
    court = await a_court("Waldauf")
    await court.holds("Fugger", employer="Maximilian I")
    await run_pending()
    assert await court.candidates() == ["Waldauf"]

    await court.Person.merge(
        absorb=court.people["Maximilian"].id, into=court.people["Maximilian I"].id
    )
    await run_pending()

    # (the criteria name the absorbed one still: its id leads to the survivor)
    assert await court.candidates() == ["Fugger", "Waldauf"]
    assert await out_of_date() == []


@no_type_check
async def test_another_with_secretaries_of_their_own_merged_into_the_entity_the_criteria_name(
    clear_database,
):
    court = await a_court("Waldauf")
    await court.holds("Fugger", employer="Maximilian I")
    await run_pending()

    result = await court.Person.merge(
        absorb=court.people["Maximilian I"].id, into=court.people["Maximilian"].id
    )
    await run_pending()
    assert await court.candidates() == ["Fugger", "Waldauf"]

    # (and undone)
    await court.Person.unmerge(result.merge.id)
    await run_pending()
    assert await court.candidates() == ["Waldauf"]
    assert await out_of_date() == []


@no_type_check
async def test_a_candidate_merged_into_another_person_and_the_merge_undone(
    clear_database,
):
    court = await a_court("Waldauf", "Serntein")
    hans = await court.person("Hans")
    await run_pending()

    result = await court.Person.merge(absorb=court.people["Waldauf"].id, into=hans.id)
    await run_pending()
    assert await court.candidates() == ["Hans", "Serntein"]

    await court.Person.unmerge(result.merge.id)
    await run_pending()
    assert await court.candidates() == ["Serntein", "Waldauf"]
    assert await out_of_date() == []


# --- the entity's own fields ------------------------------------------------------------------------------------------

DOCTORS = {"type": "Person", "where": {"title": {"eq": "Dr"}}}


@no_type_check
async def test_a_change_of_a_field_of_the_entity_the_criteria_are_on_is_followed(
    clear_database,
):
    court = await a_court(criteria=DOCTORS)
    eck = await court.Person.Create(label="Eck", title="Dr").save()
    abel = await court.person("Abel")
    await run_pending()
    assert await court.candidates() == ["Eck"]

    await court.Person.Update(id=abel.id, label="Abel", title="Dr").save()
    await run_pending()
    assert await court.candidates() == ["Abel", "Eck"]

    await court.Person.Update(id=eck.id, label="Eck", title=None).save()
    await run_pending()
    assert await court.candidates() == ["Abel"]


@no_type_check
async def test_a_candidate_deleted_is_no_longer_counted(clear_database):
    court = await a_court(criteria=DOCTORS)
    eck = await court.Person.Create(label="Eck", title="Dr").save()
    await court.Person.Create(label="Abel", title="Dr").save()
    await run_pending()
    assert (await court.description()).candidate_count == 2

    await court.Person.delete(eck.id)
    # (the edge went with the delete; the count follows when the worker has run)
    assert await court.candidates() == ["Abel"]
    await run_pending()

    described = await court.description()
    assert [p.label for p in described.target] == ["Abel"]
    assert described.candidate_count == 1
    assert await out_of_date() == []


# --- nothing written, nothing chosen ----------------------------------------------------------------------------------


@no_type_check
async def test_nothing_is_written_when_the_result_is_the_same(clear_database):
    court = await a_court("Waldauf")
    held = await court.holds("Serntein")
    await run_pending()
    first = await court.description()
    events = []
    hooks.after_write.append(events.append)
    before = stats()
    try:
        await court.update(held, label="Serntein, secretary")
        await run_pending()
    finally:
        hooks.after_write.remove(events.append)

    again = await court.description()
    assert again.evaluated_when == first.evaluated_when
    assert [p.label for p in again.target] == ["Serntein", "Waldauf"]
    assert [e.op for e in events if e.op == "computed"] == []
    assert grew(before, "chosen", "unchanged", "written") == {
        "chosen": 1,
        "unchanged": 1,
        "written": 0,
    }


@no_type_check
async def test_a_write_of_a_class_the_criteria_do_not_touch_chooses_nothing(
    clear_database,
):
    court = await a_court("Waldauf")
    before = stats()

    note = await court.Note.Create(
        label="A note", about=[ref(court.people["Waldauf"])]
    ).save()
    # (marked: the criteria of a person reach a note of one)
    assert await is_pending(note.id)
    await run_pending()

    assert grew(before, "chosen", "written") == {"chosen": 0, "written": 0}
    assert (await pending_status())["pending"] == 0


@no_type_check
async def test_a_description_whose_document_is_deleted_is_not_evaluated(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    await court.Activity.delete(court.activity.id)
    await run_pending()
    when = run(db_driver, "MATCH (d:MatchesCriteria) RETURN d.evaluated_when AS when")
    before = stats()

    await court.holds("Serntein")
    await run_pending()

    assert grew(before, "chosen", "evaluated", "written") == {
        "chosen": 0,
        "evaluated": 0,
        "written": 0,
    }
    assert (
        run(db_driver, "MATCH (d:MatchesCriteria) RETURN d.evaluated_when AS when")
        == when
    )
    # (brought back, it is evaluated as it then is)
    await court.Activity.undelete(court.activity.id)
    await run_pending()
    assert await court.candidates() == ["Serntein", "Waldauf"]


@no_type_check
async def test_criteria_that_became_broken_are_marked_broken_once_when_chosen(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    db_driver.execute_query(
        """
        MATCH (d:MatchesCriteria)
        SET d.criteria = '{"type": "Person", "where": {"shoe_size": {"gt": 40}}}'
        """,
        database_=run_database(),
    )
    before = stats()

    await court.holds("Serntein")
    await run_pending()

    described = await court.description()
    assert "Person has no field 'shoe_size'" in described.broken
    # (it keeps what it had)
    assert [p.label for p in described.target] == ["Waldauf"]
    assert grew(before, "chosen", "broken", "written") == {
        "chosen": 1,
        "broken": 1,
        "written": 1,
    }

    before = stats()
    await court.holds("Lang")
    await run_pending()

    again = await court.description()
    assert again.broken == described.broken
    assert again.evaluated_when == described.evaluated_when
    assert grew(before, "chosen", "unchanged", "written") == {
        "chosen": 1,
        "unchanged": 1,
        "written": 0,
    }


@no_type_check
async def test_a_chosen_description_whose_document_is_saved_meanwhile_is_refused_and_done_again(
    clear_database, monkeypatch
):
    court = await a_court("Waldauf")
    from pangloss_criteria import worker as worker_module

    real = worker_module.evaluate
    changed = []

    async def evaluate_then_change(pattern, without=(), limit=None):
        found = await real(pattern, without, limit)
        if not changed:
            # (a save of the activity, after the worker read it and before it writes)
            changed.append(True)
            read = await court.Activity.get(court.activity.id)
            payload = read.model_dump(mode="json", by_alias=True)
            payload.pop("meta")
            await court.Activity.Update(**{**payload, "label": "Changed"}).save()
        return found

    monkeypatch.setattr(worker_module, "evaluate", evaluate_then_change)
    await court.holds("Serntein")
    refused = worker.stats.refused

    await worker.take_lease()
    try:
        # (the office and the person it names, who is new)
        assert await worker.process_batch() == 2
        assert worker.stats.refused == refused + 1
        assert candidates(await court.Activity.get(court.activity.id)) == ["Waldauf"]
        # (the save marked it, after this batch was claimed)
        assert await is_pending(court.activity.id)
        await worker.drain()
    finally:
        await worker.give_up_lease()

    read = await court.Activity.get(court.activity.id)
    assert read.label == "Changed"
    assert candidates(read) == ["Serntein", "Waldauf"]


# --- out of date ------------------------------------------------------------------------------------------------------


@no_type_check
async def test_out_of_date_gives_the_descriptions_a_write_has_changed_until_the_worker_runs(
    clear_database,
):
    court = await a_court("Waldauf")
    other = await court.described(
        label="Another",
        criteria=secretary_of(
            await court.office("Secretary"), await court.person("Sigismund")
        ),
    )
    await run_pending()
    assert await out_of_date() == []

    await court.holds("Serntein")

    assert await out_of_date() == [str((await court.description()).id)]
    assert candidates(await court.Activity.get(other.id)) == []
    await run_pending()
    assert await out_of_date() == []
