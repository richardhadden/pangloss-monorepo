"""What the commands of `pangloss criteria` do (`pangloss_criteria.maintenance`): `rebuild`, `description_status`,
`explain` and `check`, against the database (implementation_docs/matches-criteria.md, "7. Commands")"""

import importlib
from typing import no_type_check

import pangloss_criteria.models
import pytest
from criteria_court_support import (
    Court,
    candidates,
    description_of,
    run_database,
    secretary_of,
)
from pangloss_criteria import CriteriaWorkerBusy, rebuild, run_pending
from pangloss_criteria.maintenance import check, description_status, explain
from pangloss_criteria.worker import Worker, out_of_date, worker
from pangloss_models import Document, Entity, initialise

pytestmark = pytest.mark.asyncio(loop_scope="session")

evaluating = importlib.import_module("pangloss_criteria.evaluate")


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Person(Entity):
        title: str | None = None

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        holder: list[Person | MatchesCriteria[Person]]
        office: Office
        employer: Person

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]
        witnessed_by: list[Person]

    initialise()
    return Person, Office, HoldsOffice, Activity


DOCTORS = {"type": "Person", "where": {"title": {"eq": "Dr"}}}


def doctors_employer(court) -> dict:
    """Far: a field of another entity (the employer), anchored at the office"""
    return {
        "type": "Person",
        "where": {
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "holder",
                    "where": {
                        "office": {"is": str(court.offices["Secretary"].id)},
                        "employer": {
                            "type": "Person",
                            "where": {"title": {"eq": "Dr"}},
                        },
                    },
                }
            ]
        },
    }


@no_type_check
async def a_court(*secretaries) -> Court:
    court = Court(*models())
    await court.office("Secretary")
    await court.person("Maximilian")
    for name in secretaries:
        await court.holds(name)
    await run_pending()
    return court


def forget_marks(db_driver):
    """As a bulk load leaves the data: written, and nothing pending"""
    db_driver.execute_query("MATCH (p:PGPending) DELETE p", database_=run_database())


def break_criteria(db_driver, description_id):
    db_driver.execute_query(
        """
        MATCH (d:MatchesCriteria {id: $id})
        SET d.criteria = '{"type": "Person", "where": {"shoe_size": {"gt": 40}}}'
        """,
        id=str(description_id),
        database_=run_database(),
    )


# --- rebuild ----------------------------------------------------------------------------------------------------------


@no_type_check
async def test_rebuild_evaluates_every_description_and_writes_those_that_changed(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    activity = await court.described()
    doctors = await court.described(label="Doctors", criteria=DOCTORS)
    await run_pending()
    await court.holds("Serntein")
    await court.Person.Create(label="Eck", title="Dr").save()
    forget_marks(db_driver)
    assert len(await out_of_date()) == 2

    done = await rebuild()

    assert (
        done.descriptions,
        done.evaluated,
        done.changed,
        done.broken,
        done.refused,
    ) == (
        2,
        2,
        2,
        0,
        0,
    )
    assert (done.anchored, done.root_first) == (1, 1)
    assert candidates(await court.Activity.get(activity.id)) == ["Serntein", "Waldauf"]
    assert candidates(await court.Activity.get(doctors.id)) == ["Eck"]
    assert await out_of_date() == []
    again = await rebuild()
    assert (again.descriptions, again.changed) == (2, 0)


@no_type_check
async def test_rebuild_of_a_class(clear_database, db_driver):
    court = await a_court("Waldauf")
    await court.described()
    await run_pending()
    await court.holds("Serntein")
    forget_marks(db_driver)

    assert (await rebuild("Office")).descriptions == 0
    assert len(await out_of_date()) == 1
    done = await rebuild("Person")
    assert (done.descriptions, done.changed) == (1, 1)
    assert await out_of_date() == []


@no_type_check
async def test_rebuild_marks_broken_criteria_once(clear_database, db_driver):
    court = await a_court("Waldauf")
    activity = await court.described()
    await run_pending()
    break_criteria(db_driver, description_of(activity).id)

    done = await rebuild()
    assert (done.broken, done.changed, done.evaluated) == (1, 1, 0)
    described = description_of(await court.Activity.get(activity.id))
    assert "shoe_size" in described.broken
    # (it keeps what it had)
    assert [p.label for p in described.target] == ["Waldauf"]

    again = await rebuild()
    assert (again.broken, again.changed) == (1, 0)


@no_type_check
async def test_rebuild_does_not_write_over_a_save_made_meanwhile(
    clear_database, db_driver, monkeypatch
):
    court = await a_court("Waldauf")
    activity = await court.described()
    await run_pending()
    await court.holds("Serntein")
    forget_marks(db_driver)
    maintenance = importlib.import_module("pangloss_criteria.maintenance")
    real = maintenance.evaluate_many

    async def evaluate_then_save(jobs, limit=None, counts=None):
        found = await real(jobs, limit, counts)
        read = await court.Activity.get(activity.id)
        payload = read.model_dump(mode="json", by_alias=True)
        payload.pop("meta")
        await court.Activity.Update(**{**payload, "label": "Saved meanwhile"}).save()
        return found

    monkeypatch.setattr(maintenance, "evaluate_many", evaluate_then_save)
    done = await rebuild()

    assert (done.changed, done.refused) == (0, 1)
    monkeypatch.undo()
    # (the save marked it: the worker does it)
    await run_pending()
    assert candidates(await court.Activity.get(activity.id)) == ["Serntein", "Waldauf"]


@no_type_check
async def test_rebuild_holds_the_lease_and_does_not_run_beside_a_worker(
    clear_database,
):
    await a_court("Waldauf")
    other = Worker()
    assert await other.take_lease()
    try:
        with pytest.raises(CriteriaWorkerBusy):
            await rebuild()
    finally:
        await other.give_up_lease()

    await rebuild()
    # (and gave it up: the worker of the process takes it)
    assert await worker.take_lease()
    await worker.give_up_lease()


# --- status -----------------------------------------------------------------------------------------------------------


@no_type_check
async def test_status_counts_each_kind(clear_database, db_driver, monkeypatch):
    monkeypatch.setattr("pangloss_criteria.evaluate.max_candidates", lambda: 1)
    court = await a_court("Waldauf", "Serntein")
    await court.described()
    await court.described(label="Doctors", criteria=DOCTORS)
    await court.described(label="Far", criteria=doctors_employer(court))
    broken = await court.described(label="Broken", criteria=DOCTORS)
    deleted = await court.described(label="Deleted", criteria=DOCTORS)
    await court.Activity.delete(deleted.id)
    await run_pending()
    break_criteria(db_driver, description_of(broken).id)
    assert await description_status() == {
        "descriptions": 4,
        "far": 1,
        # (the doctors: the broken one is not said to be of any kind)
        "no_anchor": 1,
        "far_no_anchor": 0,
        "too_broad": 1,
        "broken": 0,
        "not_fitting": 1,
        "shared_places": 0,
        "no_holder": 0,
    }

    await court.holds("Lang")
    await run_pending()
    found = await description_status()
    assert (found["broken"], found["not_fitting"]) == (1, 1)


# --- explain ----------------------------------------------------------------------------------------------------------


@no_type_check
async def test_explain_a_complete_description(clear_database):
    court = await a_court("Waldauf", "Serntein")
    activity = await court.described()
    await run_pending()
    described = description_of(await court.Activity.get(activity.id))
    secretary, maximilian = (
        str(court.offices["Secretary"].id),
        str(court.people["Maximilian"].id),
    )

    told = await explain(described.id)

    assert (told.reach, told.complete, told.error) == ("local", True, None)
    assert told.anchors == [
        {"ids": [maximilian], "hops": 1, "merged": {}},
        {"ids": [secretary], "hops": 1, "merged": {}},
    ]
    assert (told.linked, told.count) == (2, 2)
    assert any(
        f"names (now or before the write) {maximilian} and {secretary}" in line
        for line in told.chosen_for
    )
    # (from the one fewest heads refer to: the office, and Maximilian, are named by two)
    assert told.in_full.startswith(
        f"from the anchor {maximilian} (1 hops): 2 heads refer to it"
    )
    assert "MATCH" in told.query and "holder" in told.query
    assert told.params["limit"] == 50


@no_type_check
async def test_explain_far_root_first_merged_broken_and_unknown(
    clear_database, db_driver, monkeypatch
):
    court = await a_court("Waldauf")
    far = await court.described(label="Far", criteria=doctors_employer(court))
    doctors = await court.described(label="Doctors", criteria=DOCTORS)
    merged = await court.described()
    broken = await court.described(label="Broken", criteria=DOCTORS)
    await run_pending()
    break_criteria(db_driver, description_of(broken).id)
    await court.person("Maximilian I")
    await court.Person.merge(
        absorb=court.people["Maximilian"].id, into=court.people["Maximilian I"].id
    )

    told = await explain(description_of(far).id)
    assert (told.reach, told.complete) == ("far", False)
    assert any("far: a write may change a match" in line for line in told.chosen_for)
    assert told.in_full.startswith("from the anchor")

    told = await explain(description_of(doctors).id)
    assert (told.reach, told.complete, told.anchors) == ("local", False, [])
    assert told.in_full.startswith("root first")

    told = await explain(description_of(merged).id)
    maximilian = str(court.people["Maximilian"].id)
    (anchor,) = [a for a in told.anchors if a["ids"] == [maximilian]]
    assert anchor["merged"] == {maximilian: str(court.people["Maximilian I"].id)}
    monkeypatch.setattr(evaluating, "MAX_HEADS", 0)
    told = await explain(description_of(merged).id)
    assert told.in_full.startswith("root first: the anchor it would be evaluated from")

    told = await explain(description_of(broken).id)
    assert "shoe_size" in told.error and told.query == ""
    assert await explain("01a1c564-7def-70f0-bd21-410a35c82ab1") is None


@no_type_check
async def test_explain_a_description_saved_before_its_kind_was_stored(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    activity = await court.described()
    await run_pending()
    db_driver.execute_query(
        "MATCH (d:MatchesCriteria) SET d.reach = null, d.anchors = null, d.shape = null",
        database_=run_database(),
    )

    told = await explain(description_of(await court.Activity.get(activity.id)).id)

    assert told.stored == {"reach": None, "anchors": None}
    assert (told.reach, told.complete) == ("local", True)


# --- check ------------------------------------------------------------------------------------------------------------


@no_type_check
async def test_check_finds_criteria_that_no_longer_hold(clear_database, db_driver):
    court = await a_court("Waldauf")
    sigismund = await court.person("Sigismund")
    fine = await court.described()
    of_sigismund = await court.described(
        label="Of Sigismund",
        criteria=secretary_of(court.offices["Secretary"], sigismund),
    )
    broken = await court.described(label="Broken", criteria=DOCTORS)
    await run_pending()
    assert await check() == ([], [])

    break_criteria(db_driver, description_of(broken).id)
    await court.Person.delete(sigismund.id)
    await court.person("Maximilian I")
    await court.Person.merge(
        absorb=court.people["Maximilian"].id, into=court.people["Maximilian I"].id
    )
    problems, merged = await check()

    of = {str(description_of(a).id): a for a in (fine, of_sigismund, broken)}
    said = sorted((of[p.description].label, p.problem) for p in problems)
    assert len(said) == 2
    assert said[0][0] == "Broken" and "shoe_size" in said[0][1]
    assert said[1] == ("Of Sigismund", f"names {sigismund.id}, which is deleted")
    maximilian, survivor = (
        court.people["Maximilian"].id,
        court.people["Maximilian I"].id,
    )
    assert [(of[m.description].label, m.problem) for m in merged] == [
        ("A letter carried", f"{maximilian} merged into {survivor}")
    ]


@no_type_check
async def test_check_says_an_id_that_names_nothing(clear_database, db_driver):
    court = await a_court("Waldauf")
    nobody = "01a1c564-7def-70f0-bd21-410a35c82ab1"
    activity = await court.described(
        criteria={
            "type": "Person",
            "where": {
                "$incoming": [
                    {
                        "type": "HoldsOffice",
                        "field": "holder",
                        "where": {"employer": {"is": nobody}},
                    }
                ]
            },
        }
    )
    await run_pending()

    problems, merged = await check()

    assert [(p.description, p.problem) for p in problems] == [
        (str(description_of(activity).id), f"names {nobody}, which is not there")
    ]
    assert merged == []
