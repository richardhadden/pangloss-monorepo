"""The same one in several places of a document (`same_one`, implementation_docs/matches-criteria.md, "The same one in
several places of a document", step 9): what a write of the places may be (refused from Python and over the API at the
place that is wrong), and the worker, `out_of_date` and the commands giving every place of a mark the result of the
criteria one of them holds"""

import importlib
import uuid
from typing import no_type_check

import httpx2 as httpx
import pangloss_criteria.models
import pytest
from criteria_court_support import Court, ref, secretary_of
from pangloss_api import create_app
from pangloss_core import storage_of
from pangloss_criteria import rebuild, run_pending
from pangloss_criteria.maintenance import check, description_status, explain
from pangloss_criteria.worker import out_of_date, worker
from pangloss_models import Document, Entity, PanglossWriteRefused, initialise
from pangloss_testing.live import run
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

NAME = "MatchesCriteria"
PASSWORD = "correct horse"


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Person(Entity):
        pass

    class Group(Entity):
        pass

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        holder: list[Person | MatchesCriteria[Person]]
        office: Office
        employer: Person

    class Carrying(Document):
        _meta = Document.Meta(create_directly=False)
        carried_out_by: list[Person | MatchesCriteria[Person]]

    class Activity(Document):
        """Who carried a letter, who was paid for it (the same one, it may be), who ordered it; and statements"""

        carried_out_by: list[Person | MatchesCriteria[Person]]
        paid: list[Person | MatchesCriteria[Person]]
        ordered_by: list[Group | MatchesCriteria[Group]]
        witnessed_by: list[Person]
        statements: list[Carrying]

    initialise()
    return Person, Office, HoldsOffice, Activity


class Places(Court):
    async def activity(
        self, carried=(), paid=(), ordered=(), statements=(), label="A letter"
    ):
        return await self.Activity.Create(
            label=label,
            carried_out_by=list(carried),
            paid=list(paid),
            ordered_by=list(ordered),
            witnessed_by=[],
            statements=[
                {"type": "Carrying", "label": "carried", "carried_out_by": list(s)}
                for s in statements
            ],
        ).save()

    async def secretary(self):
        return secretary_of(
            await self.office("Secretary"), await self.person("Maximilian")
        )


def place(mark, criteria=None, wording="N. N.", **more):
    return {
        "type": NAME,
        "wording": wording,
        "same_one": str(mark),
        **({"criteria": criteria} if criteria is not None else {}),
        **more,
    }


@no_type_check
async def a_court(*secretaries) -> Places:
    court = Places(*models())
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


def places_of(db_driver, head_id) -> list[dict]:
    """Each description of a head as stored: its id, mark, whether it holds criteria, its counts and its candidates
    (label, who may see it) in order"""
    rows = run(
        db_driver,
        f"""
        MATCH (d:{NAME} {{head_node_id: $head}})
        OPTIONAL MATCH (d)-[e:target]->(p)
        WHERE NOT coalesce(e.reverse, false)
        WITH d, e, p ORDER BY coalesce(e.pg_position, 0)
        WITH d, collect([p.label, coalesce(e.seen_by, 'everyone')]) AS found
        RETURN d.id AS id, d.same_one AS mark, d.criteria IS NOT NULL AS holds,
               d.wording AS wording, coalesce(d.candidate_count, 0) AS count,
               coalesce(d.candidate_count_everyone, 0) AS count_everyone,
               d.evaluated_when IS NOT NULL AS evaluated,
               [f IN found WHERE f[0] IS NOT NULL] AS candidates
        ORDER BY wording
        """,
        head=str(head_id),
    )
    return rows


def result(row) -> tuple:
    return (
        row["count"],
        row["count_everyone"],
        tuple(tuple(c) for c in row["candidates"]),
    )


# --- what may be written ----------------------------------------------------------------------------------------------


@no_type_check
async def test_one_holder_and_bare_places_in_other_fields_and_at_other_depths_are_written(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    mark = uuid.uuid4()
    activity = await court.activity(
        carried=[place(mark, await court.secretary(), wording="1 carried")],
        paid=[place(mark, wording="2 paid")],
        statements=[[place(mark, wording="3 nested")]],
    )
    read = await court.Activity.get(activity.id)
    assert read.carried_out_by[0].same_one == mark
    assert read.paid[0].same_one == mark and read.paid[0].criteria is None
    assert read.statements[0].carried_out_by[0].same_one == mark
    await run_pending()
    rows = places_of(db_driver, activity.id)
    assert [(r["wording"], r["holds"]) for r in rows] == [
        ("1 carried", True),
        ("2 paid", False),
        ("3 nested", False),
    ]
    assert {result(r) for r in rows} == {(1, 1, (("Waldauf", "everyone"),))}


@no_type_check
async def test_two_holders_with_equal_criteria_and_a_lone_holder_with_a_mark_are_written(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    mark, alone = uuid.uuid4(), uuid.uuid4()
    criteria = await court.secretary()
    activity = await court.activity(
        carried=[
            place(mark, criteria, wording="1"),
            place(alone, criteria, wording="3"),
        ],
        paid=[place(mark, {"where": criteria["where"], "type": "Person"}, wording="2")],
    )
    await run_pending()
    rows = places_of(db_driver, activity.id)
    assert [r["holds"] for r in rows] == [True, True, True]
    assert {result(r) for r in rows} == {(1, 1, (("Waldauf", "everyone"),))}


@no_type_check
async def test_what_cannot_be_the_same_one_is_refused_from_python_at_the_place(
    clear_database,
):
    court = await a_court()
    mark = uuid.uuid4()
    criteria = await court.secretary()

    async def refused(**places):
        with pytest.raises(PanglossWriteRefused) as error:
            await court.activity(**places)
        return str(error.value), error.value.path

    message, path = await refused(paid=[place(mark)])
    assert message.startswith(f"No place of this document with the mark {mark}")
    assert path == ("paid", 0, "same_one")
    message, path = await refused(
        carried=[place(mark, criteria)], paid=[place(mark, {"type": "Person"})]
    )
    assert message.startswith(
        f"The places with the mark {mark} hold different criteria"
    )
    assert path == ("carried_out_by", 0, "criteria")
    message, path = await refused(
        carried=[place(mark, criteria)], ordered=[place(mark)]
    )
    assert message == (
        f"The criteria of the mark {mark} are of Person, which is not taken here (Group)"
    )
    assert path == ("ordered_by", 0, "same_one")
    # (nothing was written)
    assert (await court.Activity.list()).count == 0


@no_type_check
async def test_an_update_that_removes_the_only_holder_is_refused(clear_database):
    court = await a_court()
    mark = uuid.uuid4()
    activity = await court.activity(
        carried=[place(mark, await court.secretary(), wording="1")],
        paid=[place(mark, wording="2")],
    )
    edit = (await court.Activity.get(activity.id)).model_dump()
    edit["carried_out_by"] = []
    for key in ("meta",):
        edit.pop(key, None)

    with pytest.raises(
        PanglossWriteRefused, match="^No place of this document"
    ) as error:
        await court.Activity.Update(**edit).save(expected_version=1)
    assert error.value.path == ("paid", 0, "same_one")
    assert (await court.Activity.get(activity.id)).meta.version == 1
    # (with the criteria moved to the place that stays, it goes through)
    edit["paid"][0]["criteria"] = await court.secretary()
    await court.Activity.Update(**edit).save(expected_version=1)
    assert (await court.Activity.get(activity.id)).meta.version == 2


@no_type_check
async def test_the_same_mark_in_two_documents_means_nothing(clear_database, db_driver):
    court = await a_court("Waldauf", "Serntein")
    mark = uuid.uuid4()
    first = await court.activity(
        carried=[place(mark, await court.secretary(), wording="1")],
        paid=[place(mark, wording="2")],
    )
    # (a place of another document cannot take the first's criteria)
    with pytest.raises(PanglossWriteRefused, match="^No place of this document"):
        await court.activity(paid=[place(mark)], label="Another")
    # (and its own holder of the mark is another description, with a result of its own)
    second = await court.activity(
        carried=[
            place(mark, {"type": "Person", "where": {"label": {"eq": "Serntein"}}})
        ],
        paid=[place(mark)],
        label="Another",
    )
    await run_pending()
    assert {result(r) for r in places_of(db_driver, first.id)} == {
        (
            2,
            2,
            (
                ("Serntein", "everyone"),
                ("Waldauf", "everyone"),
            ),
        )
    }
    assert {result(r) for r in places_of(db_driver, second.id)} == {
        (1, 1, (("Serntein", "everyone"),))
    }


async def bearer(client) -> dict:
    await service.create_user("root", "root@example.com", PASSWORD, admin=True)
    response = await client.post(
        "/api/users/token", data={"username": "root", "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@no_type_check
async def test_over_the_api_each_refusal_is_a_422_at_the_place(clear_database):
    court = await a_court()
    criteria = await court.secretary()
    mark = str(uuid.uuid4())
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        admin = await bearer(client)

        async def posted(**fields):
            body = {
                "label": "A letter",
                "carriedOutBy": [],
                "paid": [],
                "orderedBy": [],
                "witnessedBy": [],
                "statements": [],
                **fields,
            }
            return await client.post("/api/Activity", json=body, headers=admin)

        def bare(**more):
            return {"type": NAME, "sameOne": mark, **more}

        cases = [
            ({"paid": [bare()]}, ["body", "paid", 0, "sameOne"], "No place of"),
            (
                {
                    "carriedOutBy": [bare(criteria=criteria)],
                    "paid": [bare(criteria={"type": "Person"})],
                },
                ["body", "carriedOutBy", 0, "criteria"],
                "The places with the mark",
            ),
            (
                {"carriedOutBy": [bare(criteria=criteria)], "orderedBy": [bare()]},
                ["body", "orderedBy", 0, "sameOne"],
                "The criteria of the mark",
            ),
            (
                {
                    "carriedOutBy": [bare(criteria=criteria)],
                    "statements": [
                        {"type": "Carrying", "label": "c", "carriedOutBy": [bare()]}
                    ],
                    "orderedBy": [bare()],
                },
                ["body", "orderedBy", 0, "sameOne"],
                "The criteria of the mark",
            ),
        ]
        for fields, loc, message in cases:
            response = await posted(**fields)
            assert response.status_code == 422, response.text
            (error,) = response.json()["detail"]
            assert error["loc"] == loc, error
            assert error["msg"].startswith(message), error
        # (one holder, a place beside it and one nested: written)
        response = await posted(
            carriedOutBy=[bare(criteria=criteria)],
            paid=[bare()],
            statements=[{"type": "Carrying", "label": "c", "carriedOutBy": [bare()]}],
        )
        assert response.status_code == 201, response.text
        read = (
            await client.get(f"/api/Activity/{response.json()['id']}", headers=admin)
        ).json()
        assert (
            read["paid"][0]["sameOne"] == mark and read["paid"][0]["criteria"] is None
        )

        # an update that takes the holder away
        activity = response.json()["id"]
        edited = (
            await client.get(f"/api/Activity/{activity}/edit", headers=admin)
        ).json()
        edited["carriedOutBy"] = []
        updated = await client.put(
            f"/api/Activity/{activity}", json=edited, headers={**admin, "If-Match": "1"}
        )
        assert updated.status_code == 422, updated.text
        (error,) = updated.json()["detail"]
        assert error["loc"] == ["body", "paid", 0, "sameOne"], error


# --- the worker -------------------------------------------------------------------------------------------------------


@no_type_check
async def test_every_place_gets_the_candidates_counts_and_who_sees_them(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    hidden = await court.holds("Serntein")
    await storage_of().operations.set_published_in_db(
        court.HoldsOffice, hidden.id, False
    )
    await run_pending()
    mark = uuid.uuid4()
    activity = await court.activity(
        carried=[place(mark, await court.secretary(), wording="1")],
        paid=[place(mark, wording="2")],
        statements=[[place(mark, wording="3")]],
    )
    await run_pending()

    rows = places_of(db_driver, activity.id)
    assert all(r["evaluated"] for r in rows)
    assert [result(r) for r in rows] == [
        (
            2,
            1,
            (
                ("Serntein", "logged_in"),
                ("Waldauf", "everyone"),
            ),
        )
    ] * 3
    read = await court.Activity.get(activity.id)
    assert [p.label for p in read.paid[0].target] == ["Serntein", "Waldauf"]
    assert read.paid[0].candidate_count == 2
    assert await out_of_date() == []


@no_type_check
async def test_a_write_of_another_document_reaches_every_place(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    mark = uuid.uuid4()
    activity = await court.activity(
        carried=[place(mark, await court.secretary(), wording="1")],
        paid=[place(mark, wording="2")],
    )
    await run_pending()
    await court.holds("Lang")
    await run_pending()
    assert [result(r) for r in places_of(db_driver, activity.id)] == [
        (
            2,
            2,
            (
                ("Lang", "everyone"),
                ("Waldauf", "everyone"),
            ),
        )
    ] * 2
    # (one that bears on neither: the places are left as they are, together)
    await court.holds("Fugger", office="Banker")
    await run_pending()
    assert [result(r) for r in places_of(db_driver, activity.id)] == [
        (
            2,
            2,
            (
                ("Lang", "everyone"),
                ("Waldauf", "everyone"),
            ),
        )
    ] * 2
    assert await out_of_date() == []


@no_type_check
async def test_a_mark_with_two_holders_is_evaluated_once(clear_database, db_driver):
    court = await a_court("Waldauf")
    mark = uuid.uuid4()
    criteria = await court.secretary()
    before = dict(vars(worker.stats))
    activity = await court.activity(
        carried=[place(mark, criteria, wording="1")],
        paid=[place(mark, criteria, wording="2"), place(mark, wording="3")],
    )
    await run_pending()
    after = vars(worker.stats)
    evaluations = sum(
        after[k] - before[k] for k in ("seeded", "anchored", "root_first", "shared")
    )
    assert evaluations == 1
    assert [result(r) for r in places_of(db_driver, activity.id)] == [
        (1, 1, (("Waldauf", "everyone"),))
    ] * 3


@no_type_check
async def test_the_criteria_moved_from_one_place_to_another_by_an_update(
    clear_database, db_driver
):
    court = await a_court("Waldauf", "Serntein")
    mark = uuid.uuid4()
    activity = await court.activity(
        carried=[place(mark, await court.secretary(), wording="1")],
        paid=[place(mark, wording="2")],
    )
    await run_pending()
    edit = (await court.Activity.get(activity.id)).model_dump()
    edit.pop("meta", None)
    # (the criteria now of whoever is called Waldauf, held by the other place)
    edit["paid"][0]["criteria"] = {
        "type": "Person",
        "where": {"label": {"eq": "Waldauf"}},
    }
    edit["carried_out_by"][0]["criteria"] = None
    await court.Activity.Update(**edit).save(expected_version=1)
    await run_pending()

    rows = places_of(db_driver, activity.id)
    assert [(r["wording"], r["holds"]) for r in rows] == [("1", False), ("2", True)]
    assert [result(r) for r in rows] == [(1, 1, (("Waldauf", "everyone"),))] * 2
    assert await out_of_date() == []


@no_type_check
async def test_after_writes_of_every_kind_no_place_is_out_of_date(
    clear_database, db_driver
):
    """A sequence as the churn test's, of one document's places: made, updated, other writes, deleted and brought
    back, published and not"""
    court = await a_court("Waldauf")
    mark = uuid.uuid4()
    activity = await court.activity(
        carried=[place(mark, await court.secretary(), wording="1")],
        paid=[place(mark, wording="2")],
        statements=[[place(mark, wording="3")]],
    )
    serntein = await court.holds("Serntein")
    await run_pending()
    await storage_of().operations.set_published_in_db(
        court.HoldsOffice, serntein.id, False
    )
    lang = await court.holds("Lang")
    await run_pending()
    await court.HoldsOffice.delete(lang.id)
    edit = (await court.Activity.get(activity.id)).model_dump()
    edit.pop("meta", None)
    edit["witnessed_by"] = [ref(court.people["Waldauf"])]
    await court.Activity.Update(**edit).save(expected_version=1)
    await run_pending()
    assert await out_of_date() == []
    # (Waldauf is named by the document: no candidate of any place)
    assert [result(r) for r in places_of(db_driver, activity.id)] == [
        (1, 0, (("Serntein", "logged_in"),))
    ] * 3
    await court.Activity.delete(activity.id)
    await run_pending()
    await storage_of().operations.set_published_in_db(
        court.HoldsOffice, serntein.id, True
    )
    await run_pending()
    await court.Activity.undelete(activity.id)
    await run_pending()
    assert await out_of_date() == []
    assert [result(r) for r in places_of(db_driver, activity.id)] == [
        (1, 1, (("Serntein", "everyone"),))
    ] * 3


@no_type_check
async def test_a_place_left_stale_alone_is_out_of_date_and_rebuilt(
    clear_database, db_driver
):
    court = await a_court("Waldauf", "Serntein")
    mark = uuid.uuid4()
    activity = await court.activity(
        carried=[place(mark, await court.secretary(), wording="1")],
        paid=[place(mark, wording="2")],
    )
    await run_pending()
    assert await out_of_date() == []
    bare = (await court.Activity.get(activity.id)).paid[0]
    # (the place that holds no criteria given a result that is not its holder's, by hand)
    written = await storage_of().operations.set_computed(
        bare.id,
        {
            "target": [court.people["Waldauf"].id],
            "candidate_count": 1,
            "candidate_count_everyone": 1,
        },
    )
    assert written
    assert await out_of_date() == [str(bare.id)]

    done = await rebuild()
    assert done.changed == 1 and done.descriptions == 2
    assert await out_of_date() == []
    assert [result(r) for r in places_of(db_driver, activity.id)] == [
        (
            2,
            2,
            (
                ("Serntein", "everyone"),
                ("Waldauf", "everyone"),
            ),
        )
    ] * 2


@no_type_check
async def test_explain_status_and_check_take_a_place_by_its_holder(
    clear_database, db_driver
):
    court = await a_court("Waldauf")
    mark = uuid.uuid4()
    activity = await court.activity(
        carried=[place(mark, await court.secretary(), wording="1")],
        paid=[place(mark, wording="2")],
    )
    await run_pending()
    read = await court.Activity.get(activity.id)
    holder, bare = read.carried_out_by[0], read.paid[0]

    told = await explain(str(bare.id))
    assert told.error is None
    assert told.same_one == str(mark) and told.evaluated_by == str(holder.id)
    assert told.criteria == (await explain(str(holder.id))).criteria
    assert told.reach == "local" and told.complete and told.linked == 1
    status = await description_status()
    assert status["descriptions"] == 2 and status["shared_places"] == 1
    assert status["no_holder"] == 0 and status["far"] == 0
    assert await check() == ([], [])

    # (the holder's criteria taken away by hand: the API refuses such a write)
    run(
        db_driver,
        f"MATCH (d:{NAME} {{id: $id}}) SET d.criteria = null",
        id=str(holder.id),
    )
    problems, _ = await check()
    assert sorted(p.description for p in problems) == sorted(
        [str(holder.id), str(bare.id)]
    )
    assert {p.problem for p in problems} == {
        f"no place of its document with the mark {mark} holds criteria"
    }
    assert (await description_status())["no_holder"] == 2
    told = await explain(str(bare.id))
    assert told.error.startswith("it has no criteria, and no place of its document")
    assert told.evaluated_by is None
