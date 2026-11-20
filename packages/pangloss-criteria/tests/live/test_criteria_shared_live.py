"""Shared descriptions (implementation_docs/matches-criteria.md, "Shared descriptions", step 11): a `Description` that
mentions cite, with criteria of their own or none. What a save of a mention checks and works out (of its effective
criteria: the shared ones and its own), what a write of the description does to the mentions that cite it, the
worker, `out_of_date`, citations' protection, a merge, and the commands"""

import hashlib
import importlib
import uuid
from typing import no_type_check

import pangloss_criteria.models
import pytest
from criteria_court_support import Court, secretary_of
from pangloss_criteria import effective, rebuild, run_pending
from pangloss_criteria.effective import Shared
from pangloss_criteria.maintenance import check, description_status, explain
from pangloss_criteria.pattern import SearchPattern, combined
from pangloss_criteria.worker import is_pending, out_of_date, worker
from pangloss_models import (
    Document,
    Entity,
    PanglossCitedError,
    PanglossReferenceError,
    PanglossWriteRefused,
    initialise,
)
from pangloss_testing.live import run

pytestmark = pytest.mark.asyncio(loop_scope="session")

NAME = "MatchesCriteria"


def models():
    # (the registry was reset, and a module is only run once: its classes are declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria
    Description = pangloss_criteria.models.Description

    class Person(Entity):
        gender: str | None = None

    class Monk(Person):
        pass

    class Group(Entity):
        pass

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        holder: list[Person | MatchesCriteria[Person]]
        office: Office
        employer: Person

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]
        paid: list[Person | MatchesCriteria[Person]]
        ordered_by: list[Group | MatchesCriteria[Group]]
        witnessed_by: list[Person]

    initialise()
    return Description, Person, Monk, Group, Office, HoldsOffice, Activity


class Shared_(Court):
    """The court, with the shared descriptions"""

    def __init__(self, Description, Person, Monk, Group, Office, HoldsOffice, Activity):
        super().__init__(Person, Office, HoldsOffice, Activity)
        self.Description, self.Monk, self.Group = Description, Monk, Group

    def make(self, **fields):
        """An activity (its lists empty unless given)"""
        return self.Activity.Create(
            **{
                "carried_out_by": [],
                "paid": [],
                "ordered_by": [],
                "witnessed_by": [],
                **fields,
            }
        )

    async def secretary(self, employer="Maximilian") -> dict:
        return secretary_of(await self.office("Secretary"), await self.person(employer))

    async def shared(self, label="Maximilian's secretary", criteria=None):
        return await self.Description.Create(
            label=label, criteria=criteria or await self.secretary()
        ).save()

    async def citing(
        self, description, own=None, label="A letter", field="carried_out_by", **more
    ):
        mention = {
            "type": NAME,
            "wording": "N. N.",
            "description": {"type": "Description", "id": str(description.id)},
            **({"criteria": own} if own is not None else {}),
            **more,
        }
        return await self.make(label=label, **{field: [mention]}).save()


@no_type_check
async def a_court(*secretaries) -> Shared_:
    court = Shared_(*models())
    await court.office("Secretary")
    await court.person("Maximilian")
    for name in secretaries:
        await court.holds(name)
    await run_pending()
    return court


@pytest.fixture(autouse=True)
def no_work_left(clear_database):
    yield
    worker.settings.batch = 200


def mentions(db_driver, head_id) -> list[dict]:
    """The mentions of a head as stored"""
    return run(
        db_driver,
        f"""
        MATCH (d:{NAME} {{head_node_id: $head}})
        OPTIONAL MATCH (d)-[e:target]->(p)
        WHERE NOT coalesce(e.reverse, false)
        WITH d, p ORDER BY p.label
        WITH d, [x IN collect(p.label) WHERE x IS NOT NULL] AS candidates
        RETURN d.id AS id, d.criteria AS criteria, d.criteria_hash AS criteria_hash, d.names AS names,
               d.depends_on AS depends_on, d.anchors AS anchors, d.reach AS reach, d.stands_for AS stands_for,
               d.broken AS broken, d.broken_since AS broken_since,
               coalesce(d.candidate_count, 0) AS count, candidates
        ORDER BY id
        """,
        head=str(head_id),
    )


def candidates_of(db_driver, head_id) -> list[str]:
    (row,) = mentions(db_driver, head_id)
    return row["candidates"]


def hash_of(pattern: SearchPattern) -> str:
    return hashlib.sha1(pattern.text().encode()).hexdigest()


async def acknowledged(court, description, criteria, label=None):
    """The shared description written again with other criteria, acknowledging what cites it"""
    return await court.Description.Update(
        id=description.id, label=label or description.label, criteria=criteria
    ).save(acknowledge_citations=True)


# --- the spike, kept: a citation inside a generic reified relation ---------------------------------------------------


@no_type_check
async def test_a_mention_cites_a_shared_description_and_reads_it_as_any_citation(
    clear_database,
):
    court = await a_court("Waldauf")
    shared = await court.shared()
    activity = await court.citing(shared)
    read = await court.Activity.get(activity.id)
    (mention,) = read.carried_out_by
    assert mention.criteria is None
    citation = mention.description
    assert citation.type == "PGCitation"
    assert citation.target_id == shared.id and citation.target_type == "Description"
    assert citation.target_label == "Maximilian's secretary"
    assert citation.target_state == "there" and citation.changed_since_cited is False
    # (as JSON: what the interface reads)
    payload = read.model_dump(mode="json", by_alias=True)
    assert payload["carriedOutBy"][0]["description"]["targetId"] == str(shared.id)
    # (sent back as it was read, it is kept)
    await court.Activity.Update(**read.model_dump()).save(expected_version=1)
    again = await court.Activity.get(activity.id)
    assert again.carried_out_by[0].description.target_id == shared.id
    assert [c["id"] for c in await court.Description.cited_by(shared.id)] == [
        str(activity.id)
    ]
    await run_pending()
    assert [
        p.label
        for p in (await court.Activity.get(activity.id)).carried_out_by[0].target
    ] == ["Waldauf"]


# --- what a save checks, and works out -----------------------------------------------------------------------------


@no_type_check
async def test_what_is_worked_out_of_a_citing_mention_is_of_its_effective_criteria(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    shared = await court.shared()
    male = {"type": "Person", "where": {"gender": {"eq": "male"}}}
    only = await court.citing(shared, label="Only")
    narrowed = await court.citing(shared, own=male, label="Narrowed")
    secretary = SearchPattern(await court.secretary())

    (row,) = mentions(db_driver, only.id)
    assert row["criteria"] is None
    assert row["criteria_hash"] == hash_of(secretary)
    assert set(row["names"]) == {
        str(court.offices["Secretary"].id),
        str(court.people["Maximilian"].id),
    }
    assert "HoldsOffice" in row["depends_on"] and row["reach"] == "local"
    assert sorted(row["anchors"]) == sorted(row["names"])
    assert "Person" in row["stands_for"] and "Group" not in row["stands_for"]

    (row,) = mentions(db_driver, narrowed.id)
    both = combined(secretary, SearchPattern(male))
    assert SearchPattern(row["criteria"]) == SearchPattern(male)
    assert row["criteria_hash"] == hash_of(both)
    # (two conditions: not complete, so no anchors kept for the first choice)
    assert row["anchors"] == []
    assert set(row["names"]) == {
        str(court.offices["Secretary"].id),
        str(court.people["Maximilian"].id),
    }


@no_type_check
async def test_a_mention_needs_criteria_or_a_description_or_a_mark(clear_database):
    court = await a_court()
    with pytest.raises(PanglossWriteRefused, match="shared description") as refused:
        await court.make(
            label="Nothing", carried_out_by=[{"type": NAME, "wording": "N. N."}]
        ).save()
    assert refused.value.path[:2] == ("carried_out_by", 0)


@no_type_check
async def test_its_own_criteria_must_be_of_the_shared_class_or_below_it(clear_database):
    court = await a_court("Waldauf")
    shared = await court.shared()
    # (a class below: a monk who was Maximilian's secretary)
    await court.citing(shared, own={"type": "Monk", "where": {}})
    monks = await court.shared("A monk", {"type": "Monk", "where": {}})
    with pytest.raises(PanglossWriteRefused, match="nor a class below it") as refused:
        await court.citing(monks, own={"type": "Person", "where": {}})
    assert refused.value.path == ("carried_out_by", 0, "criteria")
    # (of a class the place does not take: refused with them alone)
    with pytest.raises(PanglossWriteRefused, match="not what is described here"):
        await court.citing(shared, own={"type": "Group", "where": {}})
    # (own criteria are checked as a pattern of their own class, before the shared ones are read)
    with pytest.raises(PanglossWriteRefused, match="criteria") as refused:
        await court.citing(
            shared, own={"type": "Person", "where": {"nothing": {"eq": 1}}}
        )
    assert refused.value.path[:2] == ("carried_out_by", 0)


@no_type_check
async def test_the_shared_class_must_be_one_the_place_takes(clear_database):
    court = await a_court()
    companies = await court.shared("A company", {"type": "Group", "where": {}})
    with pytest.raises(PanglossWriteRefused, match="not taken here") as refused:
        await court.citing(companies)
    assert refused.value.path == ("carried_out_by", 0, "description")
    # (where a group goes it is taken)
    await court.citing(companies, field="ordered_by")


@no_type_check
async def test_citing_what_is_not_a_shared_description_is_refused(clear_database):
    court = await a_court("Waldauf")
    holding = await court.holds("Serntein")
    with pytest.raises(PanglossReferenceError, match="cite|Description"):
        await court.make(
            label="Wrong",
            carried_out_by=[
                {
                    "type": NAME,
                    "description": {"type": "HoldsOffice", "id": str(holding.id)},
                }
            ],
        ).save()
    with pytest.raises(PanglossReferenceError):
        await court.make(
            label="Nothing there",
            carried_out_by=[
                {
                    "type": NAME,
                    "description": {"type": "Description", "id": str(uuid.uuid4())},
                }
            ],
        ).save()


@no_type_check
async def test_the_same_one_with_a_cited_holder(clear_database, db_driver):
    court = await a_court("Waldauf")
    shared = await court.shared()
    mark = str(uuid.uuid4())
    cited = {"type": "Description", "id": str(shared.id)}
    activity = await court.make(
        label="Carried and paid",
        carried_out_by=[
            {"type": NAME, "wording": "1", "same_one": mark, "description": cited}
        ],
        paid=[{"type": NAME, "wording": "2", "same_one": mark}],
    ).save()
    await run_pending()
    rows = mentions(db_driver, activity.id)
    assert [r["candidates"] for r in rows] == [["Waldauf"], ["Waldauf"]]
    assert await out_of_date() == []

    # two places that hold the same: the same description cited, and the same criteria of their own
    await court.make(
        label="Both cite",
        carried_out_by=[{"type": NAME, "same_one": mark, "description": cited}],
        paid=[{"type": NAME, "same_one": mark, "description": cited}],
    ).save()
    other = await court.shared("Another", await court.secretary("Sigismund"))
    with pytest.raises(PanglossWriteRefused, match="different criteria") as refused:
        await court.make(
            label="Two descriptions",
            carried_out_by=[{"type": NAME, "same_one": mark, "description": cited}],
            paid=[
                {
                    "type": NAME,
                    "same_one": mark,
                    "description": {"type": "Description", "id": str(other.id)},
                }
            ],
        ).save()
    assert refused.value.path[-1] == "description"
    # a bare place whose field does not take what the cited holder finds
    with pytest.raises(PanglossWriteRefused, match="not taken here") as refused:
        await court.make(
            label="A person where a group goes",
            carried_out_by=[{"type": NAME, "same_one": mark, "description": cited}],
            ordered_by=[{"type": NAME, "same_one": mark}],
        ).save()
    assert refused.value.path == ("ordered_by", 0, "same_one")


@no_type_check
async def test_a_description_changed_between_the_save_reading_it_and_writing_is_worked_out_in_the_write(
    clear_database, db_driver, monkeypatch
):
    court = await a_court("Waldauf", "Lang")
    await court.holds("Lang", employer="Sigismund")
    shared = await court.shared()
    sigismund = SearchPattern(await court.secretary("Sigismund"))
    # (the save reads the description as it was, before a write of it that came between)
    read_shared = effective.read_shared

    async def as_it_was(ids):
        found = await read_shared(ids)
        return {
            key: Shared(
                key, value.label, SearchPattern(await court.secretary()).text(), False
            )
            for key, value in found.items()
        }

    await acknowledged(court, shared, sigismund.data)
    monkeypatch.setattr(effective, "read_shared", as_it_was)
    activity = await court.citing(shared)
    monkeypatch.setattr(effective, "read_shared", read_shared)
    (row,) = mentions(db_driver, activity.id)
    assert row["criteria_hash"] == hash_of(sigismund)
    assert str(court.people["Sigismund"].id) in row["names"]


# --- the worker -----------------------------------------------------------------------------------------------------


@no_type_check
async def test_mentions_that_only_cite_are_evaluated_once_and_a_narrowing_one_finds_the_subset(
    clear_database, db_driver
):
    court = await a_court("Waldauf", "Serntein")
    await court.Person.Update(
        id=court.people["Waldauf"].id, label="Waldauf", gender="male"
    ).save()
    await run_pending()
    shared = await court.shared()
    first = await court.citing(shared, label="First")
    second = await court.citing(shared, label="Second")
    narrowed = await court.citing(
        shared,
        own={"type": "Person", "where": {"gender": {"eq": "male"}}},
        label="Narrowed",
    )
    before = worker.stats.shared
    await run_pending()
    # (the two that only cite are identical criteria: evaluated once for both)
    assert worker.stats.shared - before == 2
    assert candidates_of(db_driver, first.id) == ["Serntein", "Waldauf"]
    assert candidates_of(db_driver, second.id) == ["Serntein", "Waldauf"]
    assert candidates_of(db_driver, narrowed.id) == ["Waldauf"]
    assert await out_of_date() == []

    # a new holder is followed for every mention that cites it
    await court.holds("Lang")
    await run_pending()
    assert candidates_of(db_driver, first.id) == ["Lang", "Serntein", "Waldauf"]
    assert candidates_of(db_driver, narrowed.id) == ["Waldauf"]
    assert await out_of_date() == []


@no_type_check
async def test_editing_a_cited_description_needs_the_acknowledgement_and_every_citer_follows(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    await court.holds("Lang", employer="Sigismund")
    shared = await court.shared()
    first = await court.citing(shared, label="First")
    second = await court.citing(
        shared, label="Second", own={"type": "Person", "where": {}}
    )
    await run_pending()
    assert candidates_of(db_driver, first.id) == ["Waldauf"]

    sigismund = await court.secretary("Sigismund")
    with pytest.raises(PanglossCitedError):
        await court.Description.Update(
            id=shared.id, label=shared.label, criteria=sigismund
        ).save()
    assert not await is_pending(first.id)

    await acknowledged(court, shared, sigismund)
    # (in its transaction: what is worked out of each citer is of the new criteria, and their documents are marked)
    for head in (first, second):
        assert await is_pending(head.id)
        (row,) = mentions(db_driver, head.id)
        assert str(court.people["Sigismund"].id) in row["names"]
    await run_pending()
    assert candidates_of(db_driver, first.id) == ["Lang"]
    assert candidates_of(db_driver, second.id) == ["Lang"]
    assert await out_of_date() == []
    read = await court.Activity.get(first.id)
    assert read.carried_out_by[0].description.changed_since_cited is True

    # a change of the label alone changes no criteria: nothing is marked
    await court.Description.Update(
        id=shared.id, label="Sigismund's secretary", criteria=sigismund
    ).save(acknowledge_citations=True)
    assert not await is_pending(first.id)


@no_type_check
async def test_a_change_that_no_longer_fits_a_citer_breaks_it_and_another_mends_it(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    shared = await court.shared()
    monks = await court.citing(shared, own={"type": "Monk", "where": {}}, label="Monks")
    anyone = await court.citing(shared, label="Anyone")
    await run_pending()

    # (of groups: a monk is no group, and a person's place takes no group)
    await acknowledged(court, shared, {"type": "Group", "where": {}})
    for head in (monks, anyone):
        (row,) = mentions(db_driver, head.id)
        assert row["broken"] is not None and row["broken_since"] is None
        assert await is_pending(head.id)
    (row,) = mentions(db_driver, monks.id)
    assert "Monk" in row["broken"]
    (row,) = mentions(db_driver, anyone.id)
    assert "not taken here" in row["broken"]
    await run_pending()
    # (the worker leaves them as they are, with their candidates)
    assert candidates_of(db_driver, anyone.id) == ["Waldauf"]
    assert mentions(db_driver, anyone.id)[0]["broken"] is not None
    assert await out_of_date() == []
    assert {p.description for p in (await check())[0]} >= {
        mentions(db_driver, monks.id)[0]["id"],
        mentions(db_driver, anyone.id)[0]["id"],
    }

    await acknowledged(court, shared, await court.secretary())
    for head in (monks, anyone):
        assert mentions(db_driver, head.id)[0]["broken"] is None
    await run_pending()
    assert candidates_of(db_driver, anyone.id) == ["Waldauf"]
    assert candidates_of(db_driver, monks.id) == []
    assert await out_of_date() == []


@no_type_check
async def test_a_cited_description_is_not_deleted_and_removed_by_an_admin_its_citers_are_broken(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    shared = await court.shared()
    activity = await court.citing(shared)
    await run_pending()
    with pytest.raises(PanglossCitedError):
        await court.Description.delete(shared.id)

    await court.Description.delete(shared.id, acknowledge_citations="removals")
    (row,) = mentions(db_driver, activity.id)
    assert "is not there" in row["broken"]
    await run_pending()
    assert candidates_of(db_driver, activity.id) == ["Waldauf"]
    assert await out_of_date() == []

    await court.Description.undelete(shared.id)
    assert mentions(db_driver, activity.id)[0]["broken"] is None
    await run_pending()
    assert await out_of_date() == []


@no_type_check
async def test_a_changed_description_then_a_save_of_the_citer_as_read_starts_it_empty_and_the_worker_refills_it(
    clear_database, db_driver
):
    """Decision 6: nothing renews the basis of the candidates when the description changes"""
    court = await a_court("Waldauf", "Serntein")
    await court.holds("Lang", employer="Sigismund")
    shared = await court.shared()
    activity = await court.citing(shared)
    await run_pending()
    assert candidates_of(db_driver, activity.id) == ["Serntein", "Waldauf"]

    # the description changes; the worker puts the citer right without any save of it
    await acknowledged(court, shared, await court.secretary("Sigismund"))
    await run_pending()
    assert candidates_of(db_driver, activity.id) == ["Lang"]
    read = await court.Activity.get(activity.id)
    assert read.carried_out_by[0].description.changed_since_cited is True

    # the citer saved as it was read: another basis (its citation is marked, its criteria are others), so empty
    await court.Activity.Update(**read.model_dump()).save(
        expected_version=read.meta.version
    )
    assert candidates_of(db_driver, activity.id) == []
    assert await is_pending(activity.id)
    await run_pending()
    assert candidates_of(db_driver, activity.id) == ["Lang"]
    assert await out_of_date() == []

    # and saved again as read, nothing changed: kept (what the write set on the citation is not what it says)
    read = await court.Activity.get(activity.id)
    await court.Activity.Update(**read.model_dump()).save(
        expected_version=read.meta.version
    )
    assert candidates_of(db_driver, activity.id) == ["Lang"]
    # "seen": the mark taken off is another basis, and the save's own mark refills it
    read = await court.Activity.get(activity.id)
    data = read.model_dump()
    data["carried_out_by"][0]["description"]["changed_since_cited"] = False
    await court.Activity.Update(**data).save(expected_version=read.meta.version)
    assert candidates_of(db_driver, activity.id) == []
    await run_pending()
    assert candidates_of(db_driver, activity.id) == ["Lang"]
    assert await out_of_date() == []


@no_type_check
async def test_a_merge_of_an_entity_a_shared_description_names_reaches_its_citers(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    other = await court.Person.Create(label="Maximilian I").save()
    shared = await court.shared(
        "Secretary of Maximilian I",
        secretary_of(court.offices["Secretary"], other),
    )
    activity = await court.citing(shared)
    await run_pending()
    assert candidates_of(db_driver, activity.id) == []
    (row,) = mentions(db_driver, activity.id)
    assert str(other.id) in row["names"]

    await court.Person.merge(absorb=other.id, into=court.people["Maximilian"].id)
    await run_pending()
    assert candidates_of(db_driver, activity.id) == ["Waldauf"]
    assert await out_of_date() == []


# --- the commands ---------------------------------------------------------------------------------------------------


@no_type_check
async def test_rebuild_explain_check_and_status_know_of_shared_descriptions(
    clear_database, db_driver
):
    court = await a_court("Waldauf", "Serntein")
    shared = await court.shared()
    activity = await court.citing(
        shared, own={"type": "Person", "where": {"gender": {"eq": "male"}}}
    )
    plain = await court.citing(shared, label="Plain")
    await run_pending()

    status = await description_status()
    assert status["shared_descriptions"] == 1 and status["citing"] == 2
    assert status["descriptions"] == 2 and status["not_fitting"] == 0

    (row,) = mentions(db_driver, activity.id)
    told = await explain(row["id"])
    assert told.error is None
    assert told.description["id"] == str(shared.id)
    assert told.description["label"] == "Maximilian's secretary"
    assert SearchPattern(told.description["criteria"]) == SearchPattern(
        await court.secretary()
    )
    assert SearchPattern(told.own) == SearchPattern(
        {"type": "Person", "where": {"gender": {"eq": "male"}}}
    )
    assert "$all" in told.criteria
    assert told.query

    # the stored result made wrong by hand: rebuild puts it right, by the effective criteria
    run(
        db_driver,
        f"MATCH (d:{NAME} {{head_node_id: $head}})-[e:target]-() DELETE e",
        head=str(plain.id),
    )
    run(
        db_driver,
        f"MATCH (d:{NAME} {{head_node_id: $head}}) SET d.candidate_count = 0, d.candidate_count_everyone = 0",
        head=str(plain.id),
    )
    assert await out_of_date() == [mentions(db_driver, plain.id)[0]["id"]]
    done = await rebuild()
    assert done.changed == 1 and done.broken == 0
    assert candidates_of(db_driver, plain.id) == ["Serntein", "Waldauf"]
    assert await out_of_date() == []
    problems, _ = await check()
    assert problems == []

    # a shared description that names an entity that is deleted is a problem of each citer
    named = await court.Person.Create(label="Nobody").save()
    gone = await court.shared(
        "Of nobody", secretary_of(court.offices["Secretary"], named)
    )
    citer = await court.citing(gone, label="Of nobody")
    await court.Person.delete(named.id)
    problems, _ = await check()
    assert [p.problem for p in problems if p.head == str(citer.id)] == [
        f"names {named.id}, which is deleted"
    ]
