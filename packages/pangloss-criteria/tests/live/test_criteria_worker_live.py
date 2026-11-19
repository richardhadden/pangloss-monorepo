"""`MatchesCriteria` with its worker: a save marks the document, the worker links the description to everyone its
criteria find, under the rules of "What is searched" (implementation_docs/matches-criteria.md)."""

import asyncio
import datetime
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
from pangloss_criteria.worker import Worker, is_pending, pending_status, worker
from pangloss_models import (
    Document,
    Entity,
    Match,
    PanglossWriteRefused,
    hooks,
    initialise,
)
from pangloss_testing.live import run
from pangloss_users import see_unpublished

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Person(Entity):
        pass

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        holder: list[Person | MatchesCriteria[Person]]
        office: Office
        employer: Person

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]
        witnessed_by: list[Person]

    class Note(Document):
        """Cannot hold a description"""

        about: list[Person]

    initialise()
    return Person, Office, HoldsOffice, Activity, Note


@no_type_check
async def a_court(*secretaries) -> Court:
    Person, Office, HoldsOffice, Activity, Note = models()
    court = Court(Person, Office, HoldsOffice, Activity)
    for name in secretaries:
        await court.holds(name)
    if not secretaries:
        court.offices["Secretary"] = await Office.Create(label="Secretary").save()
        await court.person("Maximilian")
    # (the documents of the court can hold a description too: what they left is done)
    await run_pending()
    return court


@pytest.fixture(autouse=True)
def no_work_left(clear_database):
    """(each test starts with nothing pending, and the worker of the process with its settings as they are)"""
    yield
    worker.settings.batch = 200


# --- a save marks, the worker evaluates -------------------------------------------------------------------------------


@no_type_check
async def test_a_save_marks_the_document_and_the_worker_links_the_candidates(
    clear_database,
):
    court = await a_court("Waldauf", "Serntein")
    await court.holds("Fugger", office="Banker")
    await court.holds("Lang", employer="Sigismund")
    # (the criteria of a description reach these: marked, and done, though no description is there yet)
    assert await run_pending() > 0
    assert (await pending_status())["pending"] == 0
    activity = await court.described()

    # (a save does not evaluate: it marks)
    assert await is_pending(activity.id)
    described = description_of(activity)
    assert described.target == [] and described.candidate_count == 0
    assert described.evaluated_when is None

    before = datetime.datetime.now(datetime.UTC)
    assert await run_pending() == 1

    assert not await is_pending(activity.id)
    read = await court.Activity.get(activity.id)
    described = description_of(read)
    assert candidates(read) == ["Serntein", "Waldauf"]
    assert described.candidate_count == 2 and described.broken is None
    assert described.evaluated_when >= before
    assert described.wording == "N. N."
    # (computed, not asserted: the document has no new version)
    assert read.meta.version == 1 and read.meta.updated_when is None


@no_type_check
async def test_a_description_with_no_match_has_no_candidates_and_is_evaluated(
    clear_database,
):
    court = await a_court()
    activity = await court.described()

    await run_pending()

    read = description_of(await court.Activity.get(activity.id))
    assert read.target == [] and read.candidate_count == 0
    assert read.evaluated_when is not None and read.broken is None


@no_type_check
async def test_what_the_server_works_out_of_the_criteria_is_stored_with_them(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    activity = await court.described()

    (row,) = run(
        db_driver,
        "MATCH (d:MatchesCriteria) RETURN d.criteria_hash AS hash, d.depends_on AS depends_on, d.names AS names",
    )

    assert len(row["hash"]) == 40
    assert row["depends_on"] == ["Person", "HoldsOffice"]
    # (the same however the pattern was written)
    assert sorted(row["names"]) == sorted(
        [str(court.offices["Secretary"].id), str(court.people["Maximilian"].id)]
    )
    # (not shown: a read has the description, not the worker's notes of it)
    dumped = description_of(await court.Activity.get(activity.id)).model_dump()
    assert {"criteria_hash", "depends_on", "names", "candidate_count_everyone"} & set(
        dumped
    ) == set()


# --- the rules of what is searched ------------------------------------------------------------------------------------


@no_type_check
async def test_what_the_same_document_names_is_never_a_candidate(clear_database):
    court = await a_court("Waldauf", "Serntein", "Lang")
    plain = await court.described(label="Nobody named")
    beside = await court.described(label="With Waldauf", named=["Waldauf"])
    witnessed = await court.described(
        label="Witnessed by Lang",
        witnessed_by=[ref(court.people["Lang"])],
    )

    await run_pending()

    assert candidates(await court.Activity.get(plain.id)) == [
        "Lang",
        "Serntein",
        "Waldauf",
    ]
    # ("N. N. and Waldauf, both his secretaries" does not offer Waldauf for N. N.)
    read = await court.Activity.get(beside.id)
    assert candidates(read) == ["Lang", "Serntein"]
    assert description_of(read).candidate_count == 2
    # (named anywhere in the document, by any relation)
    assert candidates(await court.Activity.get(witnessed.id)) == ["Serntein", "Waldauf"]


@no_type_check
async def test_criteria_never_pass_through_another_description(clear_database):
    court = await a_court("Waldauf")
    # (a description in the place of a holder: "someone, a secretary of Maximilian, is his chancellor")
    chancellor = await court.Office.Create(label="Chancellor").save()
    court.offices["Chancellor"] = chancellor
    held = await court.HoldsOffice.Create(
        label="A secretary is chancellor",
        holder=[
            {
                "type": "MatchesCriteria",
                "criteria": secretary_of(
                    court.offices["Secretary"], court.people["Maximilian"]
                ),
            }
        ],
        office=ref(chancellor),
        employer=ref(court.people["Maximilian"]),
    ).save(detail=True)
    await run_pending()
    assert [p.label for p in held.holder[0].target] == []
    assert [
        p.label for p in (await court.HoldsOffice.get(held.id)).holder[0].target
    ] == ["Waldauf"]

    # ("the chancellor of Maximilian" does not find Waldauf, who is only a candidate for it)
    activity = await court.Activity.Create(
        label="Sealed by the chancellor",
        carried_out_by=[
            {
                "type": "MatchesCriteria",
                "criteria": secretary_of(chancellor, court.people["Maximilian"]),
            }
        ],
        witnessed_by=[],
    ).save(detail=True)
    await run_pending()

    assert candidates(await court.Activity.get(activity.id)) == []
    # (though an ordinary search sees through to him)
    found = await court.Person.search(
        Match(**secretary_of(chancellor, court.people["Maximilian"]))
    )
    assert [p.label for p in found.results] == ["Waldauf"]


@no_type_check
async def test_at_most_so_many_are_linked_the_first_by_label_and_the_count_is_of_all(
    clear_database, monkeypatch
):
    court = await a_court("Eck", "Dorn", "Cles", "Baum", "Abel")
    monkeypatch.setattr("pangloss_criteria.evaluate.max_candidates", lambda: 3)
    activity = await court.described(named=["Baum"])

    await run_pending()

    read = await court.Activity.get(activity.id)
    assert candidates(read) == ["Abel", "Cles", "Dorn"]
    # (four fit, not counting the one the document names)
    assert description_of(read).candidate_count == 4


@no_type_check
async def test_the_ids_of_merged_entities_are_resolved_when_the_criteria_are_evaluated(
    clear_database,
):
    court = await a_court("Waldauf")
    duplicate = await court.Person.Create(label="Maximilian I").save()
    activity = await court.Activity.Create(
        label="A letter",
        carried_out_by=[
            {
                "type": "MatchesCriteria",
                "criteria": secretary_of(court.offices["Secretary"], duplicate),
            }
        ],
        witnessed_by=[],
    ).save(detail=True)
    await run_pending()
    assert candidates(await court.Activity.get(activity.id)) == []

    await court.Person.merge(duplicate.id, into=court.people["Maximilian"].id)
    # (the description names the absorbed entity still; a save of its document has it evaluated again)
    read = await court.Activity.get(activity.id)
    payload = read.model_dump(mode="json", by_alias=True)
    payload.pop("meta")
    await court.Activity.Update(**payload).save()
    await run_pending()

    read = await court.Activity.get(activity.id)
    assert candidates(read) == ["Waldauf"]
    assert str(duplicate.id) in description_of(read).criteria.text()


# --- two results, by what may be seen ----------------------------------------------------------------------------------


@no_type_check
async def test_a_candidate_that_rests_on_what_is_not_published_is_seen_by_those_logged_in(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    hidden = await court.holds("Serntein")
    await storage_of().operations.set_published_in_db(
        court.HoldsOffice, hidden.id, False
    )
    await run_pending()
    activity = await court.described()

    await run_pending()

    read = await court.Activity.get(activity.id)
    assert candidates(read) == ["Serntein", "Waldauf"]
    assert description_of(read).candidate_count == 2
    seen = run(
        db_driver,
        "MATCH (:MatchesCriteria)-[e:target]->(p) RETURN p.label AS label, e.seen_by AS seen_by ORDER BY label",
    )
    assert seen == [
        {"label": "Serntein", "seen_by": "logged_in"},
        {"label": "Waldauf", "seen_by": None},
    ]
    assert run(
        db_driver,
        "MATCH (d:MatchesCriteria) RETURN d.candidate_count AS all, d.candidate_count_everyone AS everyone",
    ) == [{"all": 2, "everyone": 1}]

    token = see_unpublished.set(False)
    try:
        public = await court.Activity.get(activity.id)
    finally:
        see_unpublished.reset(token)
    # (a reader who is not logged in sees the candidates everyone may see, and their count)
    assert candidates(public) == ["Waldauf"]
    assert description_of(public).candidate_count == 1


@no_type_check
async def test_a_candidate_only_those_logged_in_see_is_not_shown_to_others_anywhere(
    clear_database,
):
    court = await a_court("Waldauf")
    hidden = await court.holds("Serntein")
    await storage_of().operations.set_published_in_db(
        court.HoldsOffice, hidden.id, False
    )
    await run_pending()
    activity = await court.described()
    await run_pending()
    serntein, waldauf = court.people["Serntein"], court.people["Waldauf"]

    def incoming(view) -> list[str]:
        return [
            item["label"]
            for value in view.model_dump().values()
            if isinstance(value, list)
            for item in value
            if isinstance(item, dict) and item.get("type") == "Activity"
        ]

    async def by(person):
        found = await court.Activity.search(
            Match(where={"carried_out_by": {"is": str(person.id)}})
        )
        return [a.label for a in found.results]

    assert incoming(await court.Person.get(serntein.id)) == ["A letter carried"]
    assert await by(serntein) == ["A letter carried"]
    token = see_unpublished.set(False)
    try:
        # (not on the candidate's page, nor found by a search through the description)
        assert incoming(await court.Person.get(serntein.id)) == []
        assert incoming(await court.Person.get(waldauf.id)) == ["A letter carried"]
        assert await by(serntein) == []
        assert await by(waldauf) == ["A letter carried"]
        mentions = await court.Activity.search(
            Match(where={"$mentions": {"is": str(serntein.id)}})
        )
        assert mentions.results == []
        referred = await court.Person.search(
            Match(where={"$incoming": [{"type": "Activity"}]})
        )
        assert [p.label for p in referred.results] == ["Waldauf"]
    finally:
        see_unpublished.reset(token)
    assert activity.meta.version == 1


@no_type_check
async def test_publishing_what_a_candidate_rests_on_is_followed_when_the_description_is_evaluated_again(
    clear_database, db_driver
):
    court = await a_court()
    hidden = await court.holds("Serntein")
    await storage_of().operations.set_published_in_db(
        court.HoldsOffice, hidden.id, False
    )
    await run_pending()
    activity = await court.described()
    await run_pending()
    assert run(
        db_driver, "MATCH (:MatchesCriteria)-[e:target]->() RETURN e.seen_by AS seen_by"
    ) == [{"seen_by": "logged_in"}]

    await storage_of().operations.set_published_in_db(
        court.HoldsOffice, hidden.id, True
    )
    payload = (await court.Activity.get(activity.id)).model_dump(mode="json")
    payload.pop("meta")
    await court.Activity.Update(**payload).save()
    await run_pending()

    assert run(
        db_driver, "MATCH (:MatchesCriteria)-[e:target]->() RETURN e.seen_by AS seen_by"
    ) == [{"seen_by": None}]


# --- saved again ------------------------------------------------------------------------------------------------------


@no_type_check
async def test_a_description_saved_again_unchanged_keeps_its_candidates_meanwhile(
    clear_database,
):
    court = await a_court("Waldauf")
    activity = await court.described()
    await run_pending()
    first = description_of(await court.Activity.get(activity.id))

    payload = (await court.Activity.get(activity.id)).model_dump(mode="json")
    payload.pop("meta")
    payload["label"] = "A letter carried to Innsbruck"
    await court.Activity.Update(**payload).save()

    # (pending again, and showing what it showed)
    assert await is_pending(activity.id)
    meanwhile = await court.Activity.get(activity.id)
    assert candidates(meanwhile) == ["Waldauf"]
    assert description_of(meanwhile).evaluated_when == first.evaluated_when
    await court.holds("Serntein")
    await run_pending()

    after = await court.Activity.get(activity.id)
    assert candidates(after) == ["Serntein", "Waldauf"]
    assert description_of(after).evaluated_when > first.evaluated_when
    assert after.meta.version == 2


@no_type_check
async def test_criteria_that_are_changed_start_empty_and_are_evaluated_anew(
    clear_database,
):
    court = await a_court("Waldauf")
    await court.holds("Fugger", office="Banker")
    activity = await court.described()
    await run_pending()
    described = description_of(await court.Activity.get(activity.id))

    await court.Activity.Update(
        id=activity.id,
        label="A letter carried",
        carried_out_by=[
            {
                "type": "MatchesCriteria",
                "id": described.id,
                "wording": "N. N., his banker",
                "criteria": secretary_of(
                    court.offices["Banker"], court.people["Maximilian"]
                ),
            }
        ],
        witnessed_by=[],
    ).save()

    changed = await court.Activity.get(activity.id)
    assert candidates(changed) == []
    assert description_of(changed).evaluated_when is None
    await run_pending()
    assert candidates(await court.Activity.get(activity.id)) == ["Fugger"]


@no_type_check
async def test_a_deleted_document_is_not_evaluated_until_it_is_brought_back(
    clear_database,
):
    court = await a_court("Waldauf")
    activity = await court.described()
    await court.Activity.delete(activity.id)

    assert await run_pending() == 1
    assert not await is_pending(activity.id)
    await court.Activity.undelete(activity.id)
    assert candidates(await court.Activity.get(activity.id)) == []
    assert await is_pending(activity.id)

    await run_pending()
    assert candidates(await court.Activity.get(activity.id)) == ["Waldauf"]


# --- criteria that no longer fit ---------------------------------------------------------------------------------------


@no_type_check
async def test_criteria_that_no_longer_fit_the_models_are_marked_broken_and_keep_their_candidates(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    activity = await court.described()
    await run_pending()
    # (as a change of the models that no migration followed would leave it)
    db_driver.execute_query(
        """
        MATCH (d:MatchesCriteria)
        SET d.criteria = '{"type": "Person", "where": {"shoe_size": {"gt": 40}}}'
        """,
        database_=run_database(),
    )
    payload = (await court.Activity.get(activity.id)).model_dump(mode="json")
    payload.pop("meta")
    # (marked, as a write of it would mark it, without checking the criteria again)
    db_driver.execute_query(
        "MERGE (p:PGPending {key: $key}) SET p.kind = 'criteria', p.head_id = $id, p.token = 't', p.at = 0",
        parameters_={"key": f"criteria:{activity.id}", "id": str(activity.id)},
        database_=run_database(),
    )

    await run_pending()

    read = description_of(await court.Activity.get(activity.id))
    assert "Person has no field 'shoe_size'" in read.broken
    assert [p.label for p in read.target] == ["Waldauf"] and read.candidate_count == 1
    assert not await is_pending(activity.id)


@no_type_check
async def test_a_description_is_refused_when_its_criteria_do_not_fit(clear_database):
    court = await a_court("Waldauf")

    def create(criteria):
        return court.Activity.Create(
            label="X",
            carried_out_by=[{"type": "MatchesCriteria", "criteria": criteria}],
            witnessed_by=[],
        ).save()

    with pytest.raises(
        PanglossWriteRefused,
        match="criteria: type: 'Office' is not what is described here",
    ):
        await create({"type": "Office"})
    with pytest.raises(
        PanglossWriteRefused,
        match="criteria: shoe_size: Person has no field 'shoe_size'",
    ):
        await create({"type": "Person", "where": {"shoe_size": {"gt": 40}}})
    with pytest.raises(
        PanglossWriteRefused,
        match="'MatchesCriteria' is a wrapper the search leaves out",
    ):
        await create(
            {
                "type": "Person",
                "where": {
                    "$incoming": [
                        {"type": "HoldsOffice", "through": ["MatchesCriteria"]}
                    ]
                },
            }
        )
    with pytest.raises(PanglossWriteRefused, match="a description needs the criteria"):
        await court.Activity.Create(
            label="X",
            carried_out_by=[{"type": "MatchesCriteria", "wording": "N. N."}],
            witnessed_by=[],
        ).save()
    assert (await court.Activity.list()).count == 0


# --- the queue ---------------------------------------------------------------------------------------------------------


@no_type_check
async def test_a_write_of_a_class_that_holds_no_description_and_that_no_criteria_reach_leaves_no_work(
    clear_database, db_driver
):
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Person(Entity):
        pass

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]

    class Ship(Entity):
        """Joined to nothing a description is of"""

    class Logbook(Document):
        ships: list[Ship]

    initialise()
    ship = await Ship.Create(label="The Mary Rose").save()
    log = await Logbook.Create(label="A log", ships=[ref(ship)]).save()
    ann = await Person.Create(label="Ann").save()

    assert not await is_pending(log.id) and not await is_pending(ship.id)
    # (a person can be what criteria find)
    assert await is_pending(ann.id)
    activity = await Activity.Create(
        label="An activity", carried_out_by=[ref(ann)]
    ).save()
    assert await is_pending(activity.id)
    assert (await pending_status())["pending"] == 2
    assert await run_pending() == 2
    assert (await pending_status())["pending"] == 0
    await Logbook.Update(id=log.id, label="The log", ships=[]).save()
    await Ship.delete(ship.id)
    assert (await pending_status())["pending"] == 0


@no_type_check
async def test_writing_the_candidates_leaves_the_other_work_of_the_head_and_none_of_its_own(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    told = []
    work = lambda model: ["test-work"]  # noqa: E731
    hooks.pending_work.append(work)
    hooks.work_marked.append(told.append)
    try:
        activity = await court.described()
        db_driver.execute_query(
            "MATCH (p:PGPending {kind: 'test-work'}) DELETE p", database_=run_database()
        )
        await run_pending()
    finally:
        hooks.pending_work.remove(work)
        hooks.work_marked.remove(told.append)

    marks = run(
        db_driver, "MATCH (p:PGPending) RETURN p.kind AS kind, p.head_id AS head"
    )
    # (what reads the candidates has work to do; the candidates change no other description)
    assert marks == [{"kind": "test-work", "head": str(activity.id)}]
    assert told == [court.Activity]
    db_driver.execute_query("MATCH (p:PGPending) DELETE p", database_=run_database())


@no_type_check
async def test_a_result_for_a_document_that_changed_meanwhile_is_not_written(
    clear_database, monkeypatch
):
    court = await a_court("Waldauf")
    activity = await court.described()
    described = description_of(activity)
    from pangloss_criteria import worker as worker_module

    real = worker_module.evaluate
    changed = []

    async def evaluate_then_change(pattern, without=(), limit=None):
        found = await real(pattern, without, limit)
        if not changed:
            # (a save of the document, after the worker read it and before it writes)
            changed.append(True)
            await court.Activity.Update(
                id=activity.id,
                label="Changed meanwhile",
                carried_out_by=[
                    {
                        "type": "MatchesCriteria",
                        "id": described.id,
                        "wording": "Someone else",
                        "criteria": {
                            "type": "Person",
                            "where": {"label": {"eq": "Nobody"}},
                        },
                    }
                ],
                witnessed_by=[],
            ).save()
        return found

    monkeypatch.setattr(worker_module, "evaluate", evaluate_then_change)
    refused_before = worker.stats.refused

    await worker.take_lease()
    try:
        assert await worker.process_batch() == 1
        # (the result of the old criteria was refused, and the save left the document pending again)
        assert worker.stats.refused == refused_before + 1
        read = await court.Activity.get(activity.id)
        assert candidates(read) == [] and description_of(read).evaluated_when is None
        assert await is_pending(activity.id)
        await worker.drain()
    finally:
        await worker.give_up_lease()

    read = await court.Activity.get(activity.id)
    assert candidates(read) == [] and description_of(read).evaluated_when is not None
    assert description_of(read).wording == "Someone else"


@no_type_check
async def test_a_batch_that_fails_gives_its_claims_back(clear_database, monkeypatch):
    court = await a_court("Waldauf")
    activity = await court.described()
    from pangloss_criteria import worker as worker_module

    async def failing(pattern, without=(), limit=None):
        raise RuntimeError("the database went away")

    monkeypatch.setattr(worker_module, "evaluate", failing)
    with pytest.raises(RuntimeError):
        await run_pending()
    status = await pending_status()
    assert status["pending"] == 1 and status["claimed"] == 0

    monkeypatch.undo()
    assert await run_pending() == 1
    assert candidates(await court.Activity.get(activity.id)) == ["Waldauf"]


@no_type_check
async def test_many_documents_are_done_in_batches(clear_database):
    court = await a_court("Waldauf")
    made = [await court.described(label=f"Letter {n}") for n in range(7)]
    worker.settings.batch = 3
    batches = worker.stats.batches

    assert await run_pending() == 7

    assert worker.stats.batches - batches == 3
    for activity in made:
        assert candidates(await court.Activity.get(activity.id)) == ["Waldauf"]


@no_type_check
async def test_only_one_worker_works_at_a_time(clear_database):
    await a_court()
    other = Worker()

    assert await worker.take_lease() is True
    try:
        assert await other.take_lease() is False
        assert await worker.take_lease() is True  # (renewed)
    finally:
        await worker.give_up_lease()
    assert await other.take_lease() is True
    await other.give_up_lease()


# --- the worker running, and waiting for it ----------------------------------------------------------------------------


@no_type_check
async def test_settled_waits_for_the_running_worker_to_have_evaluated_a_save(
    clear_database,
):
    court = await a_court("Waldauf")
    running = Worker()
    task = asyncio.create_task(running.run())
    hooks.after_write.append(running.listen)
    try:
        activity = await court.described()
        await settled(activity.id, timeout=10)
        assert candidates(await court.Activity.get(activity.id)) == ["Waldauf"]

        # (woken by the write, not found at its next look: well inside the time it idles)
        began = asyncio.get_running_loop().time()
        second = await court.described(label="Another letter")
        await settled(second.id, timeout=5)
        assert asyncio.get_running_loop().time() - began < running.settings.idle / 2
        assert candidates(await court.Activity.get(second.id)) == ["Waldauf"]
    finally:
        hooks.after_write.remove(running.listen)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    # (it gave its lease up as it stopped)
    assert await worker.take_lease() is True
    await worker.give_up_lease()


@no_type_check
async def test_settled_says_so_when_nothing_evaluates(clear_database):
    court = await a_court("Waldauf")
    activity = await court.described()

    with pytest.raises(TimeoutError, match="is the criteria worker running"):
        await settled(activity.id, timeout=0.2)
    await run_pending()
    await settled(activity.id, timeout=0.2)
