"""Stored criteria through migrations (implementation_docs/matches-criteria.md, "Migrations that make a pattern
invalid"): rewritten in each change of the data (`migrating.in_migration`), checked and worked out again after
`pangloss migrate` (`migrating.after_migrate`), broken where a change makes them wrong, listed (`broken`), and put
right by a migration by hand (`rewrite`) or by saving them again"""

import hashlib
import importlib
from enum import Enum
from typing import cast, no_type_check

import httpx2 as httpx
import pangloss_criteria
import pangloss_criteria.models
import pytest
from criteria_court_support import Court, candidates, description_of, ref
from pangloss_api import create_app
from pangloss_criteria import migrating, run_pending
from pangloss_criteria.pattern import SearchPattern
from pangloss_criteria.worker import is_pending, out_of_date
from pangloss_models import Document, Entity, hooks
from pangloss_models.migrations import Migration, PossibleRename, diff
from pangloss_models.migrations import changes as c
from pangloss_models.migrations.affected import affected_models
from pangloss_models.migrations.reverse import reverse_changes
from pangloss_testing.conformance.migration_support import declare
from pangloss_testing.live import run
from pangloss_testing.under_test import migration_backend as backend
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


# The models of the court, as a template: a migration changes a part (`court_models(employer="master")`)
SOURCE = """
class Gender(Enum):
    MALE = "{male}"
    FEMALE = "female"


class Person(Entity):
    gender: Gender | None = None


class Office(Entity):
    pass


class {holds}(Document):
    holder: list[Person | MatchesCriteria[Person]]
    office: Office
    {year}: int | None = None
    {employer}


class Activity(Document):
    carried_out_by: list[Person | MatchesCriteria[Person]]
    witnessed_by: list[Person]
"""


def court_models(
    employer="employer",
    holds="HoldsOffice",
    year="year",
    male="male",
    with_employer=True,
):
    """A function that declares the models of the court, with what a migration changes"""
    source = SOURCE.format(
        holds=holds,
        year=year,
        male=male,
        employer=f"{employer}: Person | None = None" if with_employer else "",
    )

    def declare_them():
        # (the registry was reset, and a module is only run once: its class is declared again)
        importlib.reload(pangloss_criteria.models)
        namespace = {
            "__name__": __name__,
            "Document": Document,
            "Entity": Entity,
            "Enum": Enum,
            "MatchesCriteria": pangloss_criteria.models.MatchesCriteria,
        }
        exec(source, namespace)
        return tuple(
            namespace[name] for name in ("Person", "Office", holds, "Activity")
        )

    return declare_them


def secretary(court: Court, employer="employer", **more) -> dict:
    return {
        "type": "Person",
        "where": {
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "holder",
                    "where": {
                        "office": {"is": str(court.offices["Secretary"].id)},
                        employer: {"is": str(court.people["Maximilian"].id)},
                        **more,
                    },
                }
            ]
        },
    }


async def a_court(*secretaries, year=None) -> tuple[Court, dict]:
    """Maximilian's court in the first models, his secretaries, and an activity of one described as his secretary
    (evaluated): the court, and the snapshot of the models"""
    made, state = declare(court_models())
    court = Court(*cast(tuple, made))
    await backend.ensure_ready()
    for holder in secretaries:
        await court.HoldsOffice.Create(
            label=f"{holder} is Secretary of Maximilian",
            holder=[ref(await court.person(holder))],
            office=ref(await court.office("Secretary")),
            employer=ref(await court.person("Maximilian")),
            year=year,
        ).save()
    court.activity = await court.described(
        criteria=secretary(
            court,
            **({"year": {"gt": 1490}} if year is not None else {}),
        )
    )
    await run_pending()
    return court, state


async def migrate(old, version, name, batch_size=None, **answers):
    """The changes from the models of `old` to those `version` declares, applied as the migration `name`: the
    migration, the models (as `declare` gives them) and the snapshot after it"""
    made, new = declare(version)
    result = diff(old, new, **answers)
    assert result.is_final, result.questions
    migration = Migration(app="courtapp", name=name, changes=tuple(result.changes))
    after = await backend.apply([migration], old, batch_size=batch_size)
    return migration, made, after


async def after_step(migration, after, complete=True, undone=False):
    """What `pangloss migrate` tells the app afterwards"""
    await hooks.run_after_migrate(
        hooks.Migrated(
            migrations=(str(migration),),
            changes=migration.changes,
            affected=tuple(sorted(affected_models(migration.changes, after))),
            complete=complete,
            undone=undone,
        )
    )


def stored(db_driver, court) -> dict:
    (row,) = run(
        db_driver,
        """
        MATCH (d:MatchesCriteria {head_node_id: $head})
        RETURN d.criteria AS criteria, d.broken AS broken, d.broken_since AS broken_since,
               d.depends_on AS depends_on, d.criteria_hash AS criteria_hash, d.names AS names
        """,
        head=str(court.activity.id),
    )
    return row


async def read_candidates(court, Activity) -> list[str]:
    return candidates(await Activity.get(court.activity.id))


async def saved_unchanged(Activity, id) -> None:
    read = await Activity.get(id)
    payload = read.model_dump(mode="json", by_alias=True)
    payload.pop("meta")
    await Activity.Update(**payload).save()


# --- renames ------------------------------------------------------------------------------------------------------------


@no_type_check
async def test_a_renamed_relation_is_renamed_in_stored_criteria_and_they_find_the_same(
    clear_database, db_driver
):
    court, old = await a_court("Serntein", "Waldauf")
    assert candidates(court.activity) == []
    assert await read_candidates(court, court.Activity) == ["Serntein", "Waldauf"]

    migration, (_, _, _, Activity), after = await migrate(
        old,
        court_models(employer="master"),
        "0002_master",
        confirmed=[
            PossibleRename(
                what="field", scope="HoldsOffice", old="employer", new="master"
            )
        ],
    )
    row = stored(db_driver, court)
    assert SearchPattern(row["criteria"]) == SearchPattern(
        secretary(court, employer="master")
    )
    assert row["broken"] is None

    await after_step(migration, after)
    assert await is_pending(court.activity.id)
    await run_pending()
    assert await read_candidates(court, Activity) == ["Serntein", "Waldauf"]
    assert await out_of_date() == []
    # (what is worked out of them is of the criteria as they are now)
    row = stored(db_driver, court)
    assert (
        row["criteria_hash"]
        == hashlib.sha1(SearchPattern(row["criteria"]).text().encode()).hexdigest()
    )


@no_type_check
async def test_a_renamed_class_is_renamed_in_stored_criteria_and_in_what_they_depend_on(
    clear_database, db_driver
):
    court, old = await a_court("Serntein")
    assert "HoldsOffice" in stored(db_driver, court)["depends_on"]

    migration, (_, _, Appointment, Activity), after = await migrate(
        old,
        court_models(holds="Appointment"),
        "0002_appointment",
        confirmed=[PossibleRename(what="model", old="HoldsOffice", new="Appointment")],
    )
    row = stored(db_driver, court)
    assert SearchPattern(row["criteria"]).where["$incoming"][0]["type"] == "Appointment"
    # (not worked out again until the models of the code describe the data)
    assert "HoldsOffice" in row["depends_on"]

    await after_step(migration, after)
    row = stored(db_driver, court)
    assert "Appointment" in row["depends_on"] and "HoldsOffice" not in row["depends_on"]
    await run_pending()
    assert await read_candidates(court, Activity) == ["Serntein"]

    # a new holder of the renamed class is followed by the worker
    await Appointment.Create(
        label="Waldauf is Secretary",
        holder=[ref(await court.person("Waldauf"))],
        office=ref(court.offices["Secretary"]),
        employer=ref(court.people["Maximilian"]),
    ).save()
    await run_pending()
    assert await read_candidates(court, Activity) == ["Serntein", "Waldauf"]


@no_type_check
async def test_a_renamed_literal_is_renamed_in_stored_criteria(
    clear_database, db_driver
):
    court, old = await a_court("Serntein", year=1495)
    assert await read_candidates(court, court.Activity) == ["Serntein"]
    migration, (_, _, _, Activity), after = await migrate(
        old,
        court_models(year="anno"),
        "0002_anno",
        confirmed=[
            PossibleRename(what="field", scope="HoldsOffice", old="year", new="anno")
        ],
    )
    where = SearchPattern(stored(db_driver, court)["criteria"]).where
    assert where["$incoming"][0]["where"]["anno"] == {"gt": 1490}
    await after_step(migration, after)
    await run_pending()
    assert await read_candidates(court, Activity) == ["Serntein"]


@no_type_check
async def test_a_changed_value_of_an_enum_is_changed_in_stored_criteria(
    clear_database, db_driver
):
    made, old = declare(court_models())
    court = Court(*cast(tuple, made))
    await backend.ensure_ready()
    await court.Person.Create(label="Serntein", gender="male").save()
    await court.Person.Create(label="Anna", gender="female").save()
    court.activity = await court.described(
        criteria={"type": "Person", "where": {"gender": {"eq": "male"}}}
    )
    await run_pending()
    assert await read_candidates(court, court.Activity) == ["Serntein"]

    migration, (_, _, _, Activity), after = await migrate(
        old, court_models(male="m"), "0002_m"
    )
    assert [change.kind for change in migration.changes] == ["AlterEnumMemberValue"]
    assert SearchPattern(stored(db_driver, court)["criteria"]).where == {
        "gender": {"eq": "m"}
    }
    await after_step(migration, after)
    await run_pending()
    assert await read_candidates(court, Activity) == ["Serntein"]


@no_type_check
async def test_a_migration_in_batches_rewrites_the_criteria_as_one_in_a_transaction_does(
    clear_database, db_driver
):
    court, old = await a_court("Serntein")
    migration, (_, _, _, Activity), after = await migrate(
        old,
        court_models(employer="master"),
        "0002_batches",
        batch_size=1,
        confirmed=[
            PossibleRename(
                what="field", scope="HoldsOffice", old="employer", new="master"
            )
        ],
    )
    assert SearchPattern(stored(db_driver, court)["criteria"]) == SearchPattern(
        secretary(court, employer="master")
    )
    await after_step(migration, after)
    await run_pending()
    assert await read_candidates(court, Activity) == ["Serntein"]


@no_type_check
async def test_a_dry_run_changes_no_criteria(clear_database, db_driver):
    court, old = await a_court("Serntein")
    before = stored(db_driver, court)
    _, new = declare(court_models(employer="master"))
    result = diff(
        old,
        new,
        confirmed=[
            PossibleRename(
                what="field", scope="HoldsOffice", old="employer", new="master"
            )
        ],
    )
    (report,) = await backend.dry_run(
        [Migration(app="courtapp", name="0002_tried", changes=tuple(result.changes))],
        old,
    )
    assert all(change.status != "error" for change in report.changes)
    assert stored(db_driver, court) == before


@no_type_check
async def test_after_migrations_that_leave_the_database_short_of_the_models_nothing_is_written(
    clear_database, db_driver
):
    court, old = await a_court("Serntein")
    migration, _, after = await migrate(
        old,
        court_models(holds="Appointment"),
        "0002_appointment",
        confirmed=[PossibleRename(what="model", old="HoldsOffice", new="Appointment")],
    )
    run(db_driver, "MATCH (p:PGPending) DELETE p")
    before = stored(db_driver, court)

    await after_step(migration, after, complete=False)
    assert stored(db_driver, court) == before
    assert not await is_pending(court.activity.id)


# --- what the next update keeps ---------------------------------------------------------------------------------------


@no_type_check
async def test_an_update_after_the_migrations_that_changes_nothing_keeps_the_candidates(
    clear_database, db_driver
):
    court, old = await a_court("Serntein")
    migration, (_, _, _, Activity), after = await migrate(
        old,
        court_models(holds="Appointment"),
        "0002_appointment",
        confirmed=[PossibleRename(what="model", old="HoldsOffice", new="Appointment")],
    )
    await after_step(migration, after)
    await run_pending()

    await saved_unchanged(Activity, court.activity.id)
    # (before the worker has run again: carried over by the update, as for any document saved unchanged)
    assert await read_candidates(court, Activity) == ["Serntein"]
    await run_pending()
    assert await read_candidates(court, Activity) == ["Serntein"]


@no_type_check
async def test_without_the_step_after_the_migrations_an_update_starts_the_description_again(
    clear_database, db_driver
):
    court, old = await a_court("Serntein")
    _, (_, _, _, Activity), _ = await migrate(
        old,
        court_models(holds="Appointment"),
        "0002_appointment",
        confirmed=[PossibleRename(what="model", old="HoldsOffice", new="Appointment")],
    )
    # (its criteria were rewritten in place, and nothing told the next update what the description now says)
    await saved_unchanged(Activity, court.activity.id)
    assert await read_candidates(court, Activity) == []
    await run_pending()
    assert await read_candidates(court, Activity) == ["Serntein"]


# --- broken -------------------------------------------------------------------------------------------------------------


async def logged_in(client) -> dict:
    await service.create_user("root", "root@example.com", PASSWORD, admin=True)
    response = await client.post(
        "/api/users/token", data={"username": "root", "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@no_type_check
async def test_a_removed_field_breaks_the_criteria_which_keep_their_candidates_and_are_listed(
    clear_database, db_driver
):
    court, old = await a_court("Serntein", "Waldauf")
    migration, (_, _, _, Activity), after = await migrate(
        old, court_models(with_employer=False), "0002_no_employer"
    )
    row = stored(db_driver, court)
    assert row["broken"] == (
        "$incoming.employer: the field 'employer' of HoldsOffice was removed"
    )
    assert row["broken_since"] == "courtapp.0002_no_employer"
    # (the condition is kept: without it the description would find every secretary)
    assert SearchPattern(row["criteria"]) == SearchPattern(secretary(court))

    await after_step(migration, after)
    await run_pending()
    # the worker leaves it as it is, with its candidates
    assert stored(db_driver, court)["broken"] == row["broken"]
    assert stored(db_driver, court)["broken_since"] == "courtapp.0002_no_employer"
    read = await Activity.get(court.activity.id)
    assert candidates(read) == ["Serntein", "Waldauf"]
    assert description_of(read).broken_since == "courtapp.0002_no_employer"
    assert await out_of_date() == []

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        assert (await client.get("/api/criteria/broken")).status_code == 401
        admin = await logged_in(client)
        listed = (await client.get("/api/criteria/broken", headers=admin)).json()
        (one,) = listed["results"]
        assert listed["count"] == 1 and listed["page"] == 1 and listed["pageSize"] == 25
        assert one["id"] == str(description_of(read).id)
        assert one["brokenSince"] == "courtapp.0002_no_employer"
        assert one["broken"] == row["broken"]
        assert one["wording"] == "N. N."
        assert one["criteria"] == SearchPattern(row["criteria"]).data
        assert one["head"] == {
            "id": str(court.activity.id),
            "type": "Activity",
            "label": "A letter carried",
        }
        page = (
            await client.get(
                f"/api/criteria/{description_of(read).id}/candidates", headers=admin
            )
        ).json()
        assert page["broken"] == row["broken"]
        assert page["brokenSince"] == "courtapp.0002_no_employer"


@no_type_check
async def test_the_broken_are_listed_in_pages_by_their_document_and_not_a_place_with_no_criteria(
    clear_database, db_driver
):
    import uuid

    court, old = await a_court("Serntein")
    mark = str(uuid.uuid4())
    # (a letter whose bearer is described twice: the second place says it is the same one, and has no criteria)
    await court.Activity.Create(
        label="B letter",
        carried_out_by=[
            {"type": "MatchesCriteria", "criteria": secretary(court), "same_one": mark},
            {"type": "MatchesCriteria", "wording": "the said", "same_one": mark},
        ],
        witnessed_by=[],
    ).save()
    gone = await court.Activity.Create(
        label="C letter",
        carried_out_by=[{"type": "MatchesCriteria", "criteria": secretary(court)}],
        witnessed_by=[],
    ).save()
    migration, (_, _, _, Activity), after = await migrate(
        old, court_models(with_employer=False), "0002_no_employer"
    )
    await Activity.delete(gone.id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        admin = await logged_in(client)

        async def page(number):
            response = await client.get(
                "/api/criteria/broken",
                params={"page": number, "pageSize": 1},
                headers=admin,
            )
            assert response.status_code == 200, response.text
            return response.json()

        first, second, third = await page(1), await page(2), await page(3)
    assert first["count"] == second["count"] == 2 and first["pageSize"] == 1
    assert [one["head"]["label"] for one in first["results"] + second["results"]] == [
        "A letter carried",
        "B letter",
    ]
    assert third["results"] == []
    assert all(
        one["brokenSince"] == "courtapp.0002_no_employer"
        for one in first["results"] + second["results"]
    )
    # (and from Python, on the server)
    listed = await pangloss_criteria.broken(page=1, page_size=10)
    assert [one.head.label for one in listed.results] == [
        "A letter carried",
        "B letter",
    ]
    del migration, after


@no_type_check
async def test_broken_criteria_are_still_brought_through_later_changes_and_stay_broken(
    clear_database, db_driver
):
    court, old = await a_court("Serntein")
    _, _, after = await migrate(
        old, court_models(with_employer=False), "0002_no_employer"
    )
    broken = stored(db_driver, court)
    await migrate(
        after,
        court_models(with_employer=False, holds="Appointment"),
        "0003_appointment",
        confirmed=[PossibleRename(what="model", old="HoldsOffice", new="Appointment")],
    )
    row = stored(db_driver, court)
    assert SearchPattern(row["criteria"]).where["$incoming"][0]["type"] == "Appointment"
    assert (row["broken"], row["broken_since"]) == (
        broken["broken"],
        "courtapp.0002_no_employer",
    )


@no_type_check
async def test_undoing_the_migration_that_broke_the_criteria_clears_them(
    clear_database, db_driver
):
    court, old = await a_court("Serntein")
    migration, _, after = await migrate(
        old, court_models(with_employer=False), "0002_no_employer"
    )
    assert stored(db_driver, court)["broken_since"] == "courtapp.0002_no_employer"

    reversal = reverse_changes(list(migration.changes), old)
    undoing = Migration(
        app=migration.app, name=migration.name, changes=tuple(reversal.changes)
    )
    declare(court_models())
    await backend.unapply([undoing], after)

    row = stored(db_driver, court)
    assert row["broken"] is None and row["broken_since"] is None
    assert SearchPattern(row["criteria"]) == SearchPattern(secretary(court))


@no_type_check
async def test_a_document_with_a_broken_description_is_not_saved_until_its_criteria_are_mended(
    clear_database, db_driver
):
    """(the user's decision, 2026-11-20) a save checks the criteria of every description of the document: one that
    is broken refuses it, also a save that changes something else"""
    from pangloss_models import PanglossWriteRefused

    court, old = await a_court("Serntein", "Waldauf")
    migration, (Person, Office, HoldsOffice, Activity), after = await migrate(
        old, court_models(with_employer=False), "0002_no_employer"
    )
    await after_step(migration, after)
    before = stored(db_driver, court)
    assert before["broken"] is not None

    read = await Activity.get(court.activity.id)
    payload = read.model_dump(mode="json", by_alias=True)
    payload.pop("meta")
    payload["label"] = "Another label, and the criteria as they were"
    with pytest.raises(PanglossWriteRefused) as refused:
        await Activity.Update(**payload).save()
    assert "criteria" in str(refused.value)

    assert (await Activity.get(court.activity.id)).label == read.label
    assert stored(db_driver, court) == before


@no_type_check
async def test_a_broken_description_saved_again_with_good_criteria_is_cleared_and_evaluated(
    clear_database, db_driver
):
    court, old = await a_court("Serntein", "Waldauf")
    migration, (Person, Office, HoldsOffice, Activity), after = await migrate(
        old, court_models(with_employer=False), "0002_no_employer"
    )
    await after_step(migration, after)
    await run_pending()

    read = await Activity.get(court.activity.id)
    payload = read.model_dump(mode="json", by_alias=True)
    payload.pop("meta")
    (description,) = payload["carriedOutBy"]
    description["criteria"] = {
        "type": "Person",
        "where": {
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "holder",
                    "where": {"office": {"is": str(court.offices["Secretary"].id)}},
                }
            ]
        },
    }
    await Activity.Update(**payload).save()
    row = stored(db_driver, court)
    assert row["broken"] is None and row["broken_since"] is None
    await run_pending()
    assert await read_candidates(court, Activity) == ["Serntein", "Waldauf"]


@no_type_check
async def test_a_description_found_broken_after_the_migrations_is_broken_since_the_last(
    clear_database, db_driver
):
    court, old = await a_court("Serntein")
    # (a query by hand, which alters no pattern: but the criteria no longer fit the models)
    migration = Migration(
        app="courtapp", name="0002_by_hand", changes=(c.RunCypher(query="RETURN 1"),)
    )
    after = await backend.apply([migration], old)
    run(
        db_driver,
        "MATCH (d:MatchesCriteria) SET d.criteria = $text",
        text=SearchPattern(
            {"type": "Person", "where": {"nickname": {"eq": "Hans"}}}
        ).text(),
    )
    await after_step(migration, after)
    row = stored(db_driver, court)
    assert row["broken"].startswith("nickname: Person has no field 'nickname'")
    assert row["broken_since"] == "courtapp.0002_by_hand"
    assert await is_pending(court.activity.id)


# --- by hand ------------------------------------------------------------------------------------------------------------

# (what `to_the_chancellery` puts in the place of the office the criteria name: set by the test)
CHANGED_OFFICE: dict[str, str] = {}


async def to_the_chancellery(tx, state):
    """A migration by hand: every description of a secretary is made one of a chancellor"""

    def rewritten(pattern: SearchPattern):
        where = pattern.where["$incoming"][0]["where"]
        if where.get("office") != {"is": CHANGED_OFFICE["from"]}:
            return None
        where["office"] = {"is": CHANGED_OFFICE["to"]}
        return pattern.data

    assert await pangloss_criteria.rewrite(tx, rewritten) == 1


@no_type_check
async def test_a_migration_by_hand_rewrites_the_criteria_with_rewrite(
    clear_database, db_driver
):
    court, old = await a_court("Serntein")
    chancellor = await court.office("Chancellor")
    await court.HoldsOffice.Create(
        label="Lang is Chancellor of Maximilian",
        holder=[ref(await court.person("Lang"))],
        office=ref(chancellor),
        employer=ref(court.people["Maximilian"]),
    ).save()
    await run_pending()
    CHANGED_OFFICE.update(
        {"from": str(court.offices["Secretary"].id), "to": str(chancellor.id)}
    )
    migration = Migration(
        app="courtapp",
        name="0002_chancellery",
        changes=(c.RunPython(function=to_the_chancellery),),
    )
    after = await backend.apply([migration], old)
    where = SearchPattern(stored(db_driver, court)["criteria"]).where
    assert where["$incoming"][0]["where"]["office"] == {"is": str(chancellor.id)}

    await after_step(migration, after)
    assert str(chancellor.id) in stored(db_driver, court)["names"]
    await run_pending()
    assert await read_candidates(court, court.Activity) == ["Lang"]


# --- the hook, as the package installs it --------------------------------------------------------------------------


async def test_the_package_gives_its_hooks_to_migrations():
    assert pangloss_criteria.rewrite_in_migration in hooks.migration_changes
    assert pangloss_criteria.check_after_migrate in hooks.after_migrate
    assert (
        migrating.since_of(
            hooks.MigrationStep(change=None, before={}, after={}, migration="a.0001")
        )
        == "a.0001"
    )
