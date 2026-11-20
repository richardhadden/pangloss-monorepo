"""The criteria of shared descriptions through migrations (implementation_docs/matches-criteria.md, "Shared
descriptions" and "Migrations that make a pattern invalid", step 11): rewritten in each change as a mention's are;
a change that breaks them breaks every mention that cites them; undoing it clears those; after the migrations a
mention is checked and worked out by its effective criteria; and a broken shared description is not saved until it
is mended"""

import hashlib
from typing import no_type_check

import pangloss_criteria.models
import pytest
from criteria_court_support import candidates
from pangloss_criteria import run_pending
from pangloss_criteria.pattern import SearchPattern
from pangloss_criteria.worker import out_of_date
from pangloss_models import PanglossWriteRefused
from pangloss_models.migrations import Migration, PossibleRename
from pangloss_models.migrations.reverse import reverse_changes
from pangloss_testing.conformance.migration_support import declare
from pangloss_testing.live import run
from pangloss_testing.under_test import migration_backend as backend
from pydantic import ValidationError
from test_criteria_migrations_live import (
    a_court,
    after_step,
    court_models,
    migrate,
    secretary,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def citing(court, label="Maximilian's secretary", **more):
    """A shared description of Maximilian's secretary, and an activity that cites it: both, and the activity read"""
    Description = pangloss_criteria.models.Description
    shared = await Description.Create(
        label=label, criteria=secretary(court, **more)
    ).save()
    activity = await court.Activity.Create(
        label="Cited",
        carried_out_by=[
            {
                "type": "MatchesCriteria",
                "wording": "N. N.",
                "description": {"type": "Description", "id": str(shared.id)},
            }
        ],
        witnessed_by=[],
    ).save()
    await run_pending()
    return shared, activity


def shared_criteria(db_driver, shared) -> SearchPattern:
    (row,) = run(
        db_driver,
        "MATCH (s:Description {id: $id}) RETURN s.criteria AS criteria",
        id=str(shared.id),
    )
    return SearchPattern(row["criteria"])


def citer(db_driver, activity) -> dict:
    (row,) = run(
        db_driver,
        """
        MATCH (d:MatchesCriteria {head_node_id: $head})
        RETURN d.broken AS broken, d.broken_since AS broken_since, d.criteria_hash AS criteria_hash,
               d.depends_on AS depends_on
        """,
        head=str(activity.id),
    )
    return row


@no_type_check
async def test_a_rename_is_made_in_a_shared_description_and_its_citers_work_out_the_new_criteria(
    clear_database, db_driver
):
    court, old = await a_court("Serntein", "Waldauf")
    shared, activity = await citing(court)
    assert candidates(await court.Activity.get(activity.id)) == ["Serntein", "Waldauf"]

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
    renamed = shared_criteria(db_driver, shared)
    assert renamed == SearchPattern(secretary(court, employer="master"))
    assert citer(db_driver, activity)["broken"] is None

    await after_step(migration, after)
    row = citer(db_driver, activity)
    assert row["criteria_hash"] == hashlib.sha1(renamed.text().encode()).hexdigest()
    await run_pending()
    assert candidates(await Activity.get(activity.id)) == ["Serntein", "Waldauf"]
    assert await out_of_date() == []


@no_type_check
async def test_a_removal_breaks_every_mention_that_cites_it_and_undoing_it_clears_them(
    clear_database, db_driver
):
    court, old = await a_court("Serntein")
    shared, activity = await citing(court)
    other_shared, other = await citing(court, label="Another")
    migration, (_, _, _, Activity), after = await migrate(
        old, court_models(with_employer=False), "0002_no_employer"
    )
    for head in (activity, other):
        row = citer(db_driver, head)
        assert row["broken"] == (
            "$incoming.employer: the field 'employer' of HoldsOffice was removed"
        )
        assert row["broken_since"] == "courtapp.0002_no_employer"
    # (the condition is kept in the shared description)
    assert shared_criteria(db_driver, shared) == SearchPattern(secretary(court))

    await after_step(migration, after)
    await run_pending()
    assert citer(db_driver, activity)["broken_since"] == "courtapp.0002_no_employer"
    assert candidates(await Activity.get(activity.id)) == ["Serntein"]
    assert await out_of_date() == []

    # a broken shared description is not saved until it is mended
    Description = pangloss_criteria.models.Description
    with pytest.raises((PanglossWriteRefused, ValidationError), match="employer"):
        await Description.Update(
            id=shared.id, label=shared.label, criteria=secretary(court)
        ).save(acknowledge_citations=True)

    reversal = reverse_changes(list(migration.changes), old)
    undoing = Migration(
        app=migration.app, name=migration.name, changes=tuple(reversal.changes)
    )
    declare(court_models())
    await backend.unapply([undoing], after)
    for head in (activity, other):
        row = citer(db_driver, head)
        assert row["broken"] is None and row["broken_since"] is None


@no_type_check
async def test_a_broken_shared_description_mended_by_a_save_clears_its_citers(
    clear_database, db_driver
):
    court, old = await a_court("Serntein")
    shared, activity = await citing(court)
    migration, (_, _, HoldsOffice, Activity), after = await migrate(
        old, court_models(with_employer=False), "0002_no_employer"
    )
    await after_step(migration, after)
    Description = pangloss_criteria.models.Description
    mended = {
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
    await Description.Update(id=shared.id, label=shared.label, criteria=mended).save(
        acknowledge_citations=True
    )
    assert citer(db_driver, activity)["broken"] is None
    await run_pending()
    assert candidates(await Activity.get(activity.id)) == ["Serntein"]
    assert await out_of_date() == []
