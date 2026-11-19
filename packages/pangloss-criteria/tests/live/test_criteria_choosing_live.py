"""Which descriptions of other documents the worker evaluates after a write, and how (the table "Which descriptions,
and how" of `pangloss_criteria.worker`; implementation_docs/matches-criteria.md, "As built", step 7). Each test says
both what the candidates become and how they were reached (`worker.stats`: skipped, seeded, anchored, root first,
chosen), and none saves the description's document again: its version stays 1."""

import importlib
from typing import ClassVar, no_type_check

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
from pangloss_criteria import run_pending
from pangloss_criteria.worker import out_of_date, worker
from pangloss_cypher import pending
from pangloss_models import (
    Document,
    Entity,
    hooks,
    initialise,
)
from pangloss_testing.live import run

pytestmark = pytest.mark.asyncio(loop_scope="session")

HOW = ("chosen", "skipped", "seeded", "anchored", "root_first")


@pytest.fixture(autouse=True)
def placeholder_stands_in():
    """A document a relation to a person takes in the person's place (as `Unreconciled` does)"""
    stand_in = hooks.StandIn(
        document="Placeholder",
        stands_for=lambda model: getattr(model, "replaceable", False),
    )
    hooks.stand_ins.append(stand_in)
    yield
    hooks.stand_ins.remove(stand_in)


@pytest.fixture(autouse=True)
def no_work_left(clear_database):
    yield
    worker.settings.batch = 200


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Placeholder(Document):
        _meta = Document.Meta(create_directly=False)
        name: str

    class Agent(Entity):
        _meta = Entity.Meta(abstract=True)

    class Person(Agent):
        replaceable: ClassVar[bool] = True
        title: str | None = None

    class Group(Agent):
        pass

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        holder: list[Person | Group | MatchesCriteria[Person]]
        office: Office
        employer: Person

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]
        witnessed_by: list[Person]

    initialise()
    return Person, Group, Office, HoldsOffice, Activity


class Watched(Court):
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
async def a_court(*secretaries, criteria=None, named=()) -> Watched:
    """Maximilian's court, and an activity carried out by someone described (as a secretary of Maximilian, or by
    the criteria given), evaluated once"""
    Person, Group, Office, HoldsOffice, Activity = models()
    court = Watched(Person, Office, HoldsOffice, Activity)
    court.Group = Group
    await court.office("Secretary")
    await court.person("Maximilian")
    for name in secretaries:
        await court.holds(name)
    if callable(criteria):
        criteria = criteria(court)
    court.activity = await court.described(criteria=criteria, named=named)
    await run_pending()
    return court


def how() -> dict[str, int]:
    return {key: getattr(worker.stats, key) for key in HOW}


def grew(before: dict[str, int]) -> dict[str, int]:
    """What each count of `HOW` grew by since"""
    return {key: getattr(worker.stats, key) - before[key] for key in HOW}


def counted(chosen=0, skipped=0, seeded=0, anchored=0, root_first=0) -> dict[str, int]:
    return {
        "chosen": chosen,
        "skipped": skipped,
        "seeded": seeded,
        "anchored": anchored,
        "root_first": root_first,
    }


async def done(court) -> dict[str, int]:
    """Run the worker; what it did. When it is done, every description is what a full evaluation gives"""
    before = how()
    await run_pending()
    grown = grew(before)
    assert await out_of_date() == []
    return grown


def doctor_secretaries(court) -> dict:
    """Not complete: a condition on the person beside the document that names the anchor"""
    secretaries = secretary_of(court.offices["Secretary"], court.people["Maximilian"])
    return {
        "type": "Person",
        "where": {**secretaries["where"], "title": {"eq": "Dr"}},
    }


ANY_ACTIVITY = {
    "type": "Person",
    "where": {"$incoming": [{"type": "Activity", "field": "carried_out_by"}]},
}


# --- complete ("secretary of Maximilian") -----------------------------------------------------------------------------


@no_type_check
async def test_complete_a_write_naming_the_anchors_and_a_new_holder_is_seeded(
    clear_database,
):
    court = await a_court("Waldauf")

    await court.holds("Serntein")

    assert await done(court) == counted(chosen=1, seeded=1)
    assert await court.candidates() == ["Serntein", "Waldauf"]


@no_type_check
async def test_complete_a_write_naming_neither_anchor_chooses_nothing_and_one_of_two_is_skipped(
    clear_database,
):
    court = await a_court("Waldauf")

    await court.holds("Lang", employer="Sigismund", office="Courier")
    assert await done(court) == counted()

    # (it names the office and not the employer: each group of anchors has to be named)
    await court.holds("Kurz", employer="Sigismund")
    assert await done(court) == counted(skipped=1)
    assert await court.candidates() == ["Waldauf"]


@no_type_check
async def test_complete_an_update_that_takes_the_employer_out_loses_the_holder(
    clear_database,
):
    court = await a_court("Waldauf")
    held = await court.holds("Serntein")
    await run_pending()

    await court.update(held, employer=ref(await court.person("Sigismund")))

    assert await done(court) == counted(chosen=1, seeded=1)
    assert await court.candidates() == ["Waldauf"]


@no_type_check
async def test_complete_an_update_that_takes_the_holder_out_loses_them(clear_database):
    court = await a_court("Waldauf")
    held = await court.holds("Serntein")
    await run_pending()

    await court.update(held, holder=[ref(await court.person("Lang"))])

    assert await done(court) == counted(chosen=1, seeded=1)
    assert await court.candidates() == ["Lang", "Waldauf"]


@no_type_check
async def test_complete_without_what_the_mark_kept_the_employer_taken_out_is_missed(
    clear_database, monkeypatch
):
    court = await a_court("Waldauf")
    held = await court.holds("Serntein")
    await run_pending()

    async def kept_nothing(tx, kind, head_ids):
        return {}

    monkeypatch.setattr(pending, "before_of", kept_nothing)
    await court.update(held, employer=ref(await court.person("Sigismund")))
    before = how()
    await run_pending()

    # (the write names neither Maximilian nor, as a written head, Serntein: this is what `before_refs` is for)
    assert grew(before) == counted(skipped=1)
    assert await court.candidates() == ["Serntein", "Waldauf"]
    assert await out_of_date() == [str((await court.description()).id)]


# --- local, not complete ----------------------------------------------------------------------------------------------


@no_type_check
async def test_not_complete_the_person_gets_the_title_and_loses_it(clear_database):
    court = await a_court("Waldauf", criteria=doctor_secretaries)
    assert await court.candidates() == []
    waldauf = court.people["Waldauf"]

    # (a write that names no anchor, of someone who is no candidate)
    await court.Person.Update(id=waldauf.id, label="Waldauf", title="Dr").save()
    assert await done(court) == counted(chosen=1, seeded=1)
    assert await court.candidates() == ["Waldauf"]

    await court.Person.Update(id=waldauf.id, label="Waldauf", title=None).save()
    assert await done(court) == counted(chosen=1, seeded=1)
    assert await court.candidates() == []


@no_type_check
async def test_no_anchor_local_is_seeded(clear_database):
    court = await a_court(criteria=ANY_ACTIVITY)
    assert await court.candidates() == []

    await court.Activity.Create(
        label="Rode",
        carried_out_by=[ref(await court.person("Lang"))],
        witnessed_by=[],
    ).save()

    assert await done(court) == counted(chosen=1, seeded=1)
    assert await court.candidates() == ["Lang"]


@no_type_check
async def test_no_anchor_with_more_candidates_than_are_linked_is_evaluated_in_full(
    clear_database, monkeypatch
):
    monkeypatch.setattr("pangloss_criteria.evaluate.max_candidates", lambda: 2)
    court = await a_court(criteria=ANY_ACTIVITY)
    activities = {}
    for name in ("Abel", "Bach", "Cles", "Dorn"):
        activities[name] = await court.Activity.Create(
            label=f"{name} rode",
            carried_out_by=[ref(await court.person(name))],
            witnessed_by=[],
        ).save()
    await run_pending()
    assert await court.candidates() == ["Abel", "Bach"]
    assert (await court.description()).candidate_count == 4

    # (a write that unmakes a match that is not linked)
    await court.Activity.delete(activities["Dorn"].id)

    assert await done(court) == counted(chosen=1, root_first=1)
    assert await court.candidates() == ["Abel", "Bach"]
    assert (await court.description()).candidate_count == 3


# --- far --------------------------------------------------------------------------------------------------------------


def secretaries_of_doctors(court, office=True) -> dict:
    where = {"employer": {"type": "Person", "where": {"title": {"eq": "Dr"}}}}
    if office:
        where["office"] = {"is": str(court.offices["Secretary"].id)}
    return {
        "type": "Person",
        "where": {
            "$incoming": [{"type": "HoldsOffice", "field": "holder", "where": where}]
        },
    }


@no_type_check
async def test_far_is_evaluated_in_full_from_the_anchor_or_root_first(clear_database):
    court = await a_court("Waldauf", criteria=secretaries_of_doctors)
    other = await court.described(
        label="Another", criteria=secretaries_of_doctors(court, office=False)
    )
    await run_pending()
    maximilian = court.people["Maximilian"]

    # (a write of Maximilian alone: neither document is written, and neither names him)
    await court.Person.Update(id=maximilian.id, label="Maximilian", title="Dr").save()

    assert await done(court) == counted(chosen=2, anchored=1, root_first=1)
    assert await court.candidates() == ["Waldauf"]
    assert candidates(await court.Activity.get(other.id)) == ["Waldauf"]


# --- merges -----------------------------------------------------------------------------------------------------------


@no_type_check
async def test_a_person_with_documents_merged_into_the_anchor(clear_database):
    court = await a_court("Waldauf")
    await court.holds("Fugger", employer="Maximilian I")
    await run_pending()

    await court.Person.merge(
        absorb=court.people["Maximilian I"].id, into=court.people["Maximilian"].id
    )

    # (it names the survivor: in full)
    assert await done(court) == counted(chosen=1, anchored=1)
    assert await court.candidates() == ["Fugger", "Waldauf"]


@no_type_check
async def test_the_anchor_merged_into_another(clear_database):
    court = await a_court("Waldauf")
    await court.holds("Fugger", employer="Maximilian I")
    await run_pending()

    await court.Person.merge(
        absorb=court.people["Maximilian"].id, into=court.people["Maximilian I"].id
    )

    assert await done(court) == counted(chosen=1, anchored=1)
    assert await court.candidates() == ["Fugger", "Waldauf"]


@no_type_check
async def test_a_chain_of_merges_is_followed_to_a_later_write(clear_database):
    """The criteria name X0, merged into X long ago; X is merged into Z; later a document names Z"""
    court = await a_court("Waldauf")
    await court.person("Maximilian I")
    await court.person("Maximilian der Große")
    await court.Person.merge(
        absorb=court.people["Maximilian"].id, into=court.people["Maximilian I"].id
    )
    await court.Person.merge(
        absorb=court.people["Maximilian I"].id,
        into=court.people["Maximilian der Große"].id,
    )
    await run_pending()
    assert await court.candidates() == ["Waldauf"]

    await court.holds("Lang", employer="Maximilian der Große")

    assert await done(court) == counted(chosen=1, seeded=1)
    assert await court.candidates() == ["Lang", "Waldauf"]


@no_type_check
async def test_a_merge_undone(clear_database):
    court = await a_court("Waldauf")
    await court.holds("Fugger", employer="Maximilian I")
    await run_pending()
    result = await court.Person.merge(
        absorb=court.people["Maximilian I"].id, into=court.people["Maximilian"].id
    )
    await run_pending()

    await court.Person.unmerge(result.merge.id)

    assert await done(court) == counted(chosen=1, anchored=1)
    assert await court.candidates() == ["Waldauf"]


@no_type_check
async def test_a_merge_undone_when_the_survivor_is_named_beside_the_description(
    clear_database,
):
    """Hans is named in the description's own document (never its candidate). Kurz, a secretary, is merged into
    him and the merge undone: Kurz is a secretary again"""
    court = await a_court("Waldauf", "Kurz", named=["Hans"])
    assert await court.candidates() == ["Kurz", "Waldauf"]
    result = await court.Person.merge(
        absorb=court.people["Kurz"].id, into=court.people["Hans"].id
    )
    await run_pending()
    assert await court.candidates() == ["Waldauf"]

    await court.Person.unmerge(result.merge.id)

    # (the undo marks the heads whose edges it moves back: Kurz's document names the anchors again)
    assert await done(court) == counted(chosen=1, seeded=1)
    assert await court.candidates() == ["Kurz", "Waldauf"]


# --- a change of class ------------------------------------------------------------------------------------------------


@no_type_check
async def test_a_linked_candidate_whose_class_is_changed_to_another_is_lost(
    clear_database,
):
    court = await a_court("Waldauf", "Serntein")
    waldauf = court.people["Waldauf"]

    await court.Group.Update(id=waldauf.id, label="Waldauf").save(
        changing_class_from=court.Person
    )

    # (the change takes the computed edge to it away and marks the description's document: evaluated as one
    # whose document was written)
    assert await done(court) == counted(anchored=1)
    assert await court.candidates() == ["Serntein"]


@no_type_check
async def test_a_candidate_not_linked_whose_class_is_changed_to_another_is_lost(
    clear_database, monkeypatch
):
    monkeypatch.setattr("pangloss_criteria.evaluate.max_candidates", lambda: 1)
    court = await a_court("Waldauf", "Serntein")
    assert await court.candidates() == ["Serntein"]
    assert (await court.description()).candidate_count == 2
    waldauf = court.people["Waldauf"]

    await court.Group.Update(id=waldauf.id, label="Waldauf").save(
        changing_class_from=court.Person
    )

    # (more candidates than are linked: in full)
    assert await done(court) == counted(chosen=1, anchored=1)
    assert await court.candidates() == ["Serntein"]
    assert (await court.description()).candidate_count == 1


@no_type_check
async def test_a_holder_whose_class_is_changed_to_the_one_of_the_criteria_is_gained(
    clear_database,
):
    court = await a_court("Waldauf")
    chancery = await court.Group.Create(label="Chancery").save()
    await court.HoldsOffice.Create(
        label="The chancery is secretary",
        holder=[{"type": "Group", "id": chancery.id}],
        office=ref(court.offices["Secretary"]),
        employer=ref(court.people["Maximilian"]),
    ).save()
    await run_pending()
    assert await court.candidates() == ["Waldauf"]

    await court.Person.Update(id=chancery.id, label="Chancery").save(
        changing_class_from=court.Group
    )
    await run_pending()

    assert await court.candidates() == ["Chancery", "Waldauf"]


# --- an anchor that stands in for a person ----------------------------------------------------------------------------


@no_type_check
async def test_complete_anchored_at_a_stand_in_gains_a_new_holder(
    clear_database, db_driver
):
    Person, Group, Office, HoldsOffice, Activity = models()
    court = Watched(Person, Office, HoldsOffice, Activity)
    secretary = await court.office("Secretary")
    unknown = await HoldsOffice.Create(
        label="Fugger is secretary of a king",
        holder=[ref(await court.person("Fugger"))],
        office=ref(secretary),
        employer={"type": "Placeholder", "label": "a king", "name": "a king"},
    ).save()
    (row,) = run(db_driver, "MATCH (p:Placeholder) RETURN p.id AS id")
    court.activity = await court.described(
        criteria={
            "type": "Person",
            "where": {
                "$incoming": [
                    {
                        "type": "HoldsOffice",
                        "field": "holder",
                        "where": {
                            "office": {"is": str(secretary.id)},
                            "employer": {"is": row["id"]},
                        },
                    }
                ]
            },
        }
    )
    await run_pending()
    assert await court.candidates() == ["Fugger"]

    await HoldsOffice.Update(
        id=unknown.id,
        label="Fugger and Hans are secretaries of a king",
        holder=[ref(court.people["Fugger"]), ref(await court.person("Hans"))],
        office=ref(secretary),
        employer={
            "type": "Placeholder",
            "id": row["id"],
            "label": "a king",
            "name": "a king",
        },
    ).save()
    await run_pending()

    assert await court.candidates() == ["Fugger", "Hans"]


# --- descriptions of before, and inside a written head ----------------------------------------------------------------


@no_type_check
async def test_a_description_saved_before_reach_and_anchors_were_worked_out_is_followed(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    db_driver.execute_query(
        "MATCH (d:MatchesCriteria) SET d.reach = null, d.anchors = null, d.shape = null",
        database_=run_database(),
    )

    await court.holds("Serntein")

    # (chosen in the database by its classes; what it is, is worked out of its criteria)
    assert await done(court) == counted(chosen=1, seeded=1)
    assert await court.candidates() == ["Serntein", "Waldauf"]


@no_type_check
async def test_a_description_inside_a_written_head_is_evaluated_in_full(
    clear_database,
):
    court = await a_court("Waldauf", criteria=doctor_secretaries)
    before = how()
    read = await court.Activity.get(court.activity.id)
    payload = read.model_dump(mode="json", by_alias=True)
    payload.pop("meta")
    await court.Activity.Update(**{**payload, "label": "Saved again"}).save()
    await run_pending()

    assert grew(before) == counted(anchored=1)
    no_anchor = await court.described(label="Any", criteria=ANY_ACTIVITY)
    before = how()
    await run_pending()
    assert grew(before) == counted(root_first=1)
    assert candidates(await court.Activity.get(no_anchor.id)) == []
