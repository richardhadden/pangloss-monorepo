"""Criteria that ask the way of a relation (`via`: implementation_docs/relation-steps-plan.md, step 6): someone who
witnessed something in the role of scribe, by an edge that is sure. What makes one a match is all inside the document
that names them (a wrapper's own relation, the values of an edge), so the criteria are local, and the worker follows a
write of that document."""

import importlib
from typing import no_type_check

import pangloss_criteria.models
import pytest
from criteria_court_support import candidates, description_of, ref
from pangloss_criteria import analysis, run_pending
from pangloss_criteria.pattern import SearchPattern
from pangloss_testing.live import run
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    ReifiedRelation,
    ViaEdge,
    initialise,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Certainty(EdgeModel):
        value: int

    class Person(Entity):
        pass

    class RoleType(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: RoleType

    class Witnessed(Document):
        witness: list[InRole[ViaEdge[Person, Certainty]]]

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]

    initialise()
    return Person, RoleType, Witnessed, Activity


def a_sure_scribe(scribe, field: str | None = "witness") -> dict:
    item = {
        "type": "Witnessed",
        "via": [
            {"type": "InRole", "where": {"role": {"is": str(scribe.id)}}},
            {"type": "Certainty", "where": {"value": {"gte": 8}}},
        ],
    }
    if field:
        item["field"] = field
    return {"type": "Person", "where": {"$incoming": [item]}}


def witness(person, role, value: int) -> dict:
    return {
        "type": "InRole",
        "role": ref(role),
        "target": [{**ref(person), "edge_properties": {"value": value}}],
    }


@no_type_check
async def test_criteria_by_the_way_of_a_relation_are_evaluated_and_followed(
    clear_database, db_driver
):
    Person, RoleType, Witnessed, Activity = models()
    scribe = await RoleType.Create(label="scribe").save()
    notary = await RoleType.Create(label="notary").save()
    ann, bea, cat = [
        await Person.Create(label=label).save() for label in ("Ann", "Bea", "Cat")
    ]
    deed = await Witnessed.Create(
        label="A deed",
        witness=[
            witness(ann, scribe, 9),
            witness(bea, notary, 9),  # (not a scribe)
            witness(cat, scribe, 3),  # (not sure)
        ],
    ).save()
    criteria = a_sure_scribe(scribe)
    activity = await Activity.Create(
        label="A letter written",
        carried_out_by=[
            {"type": "MatchesCriteria", "wording": "the scribe", "criteria": criteria}
        ],
    ).save(detail=True)
    await run_pending()

    async def found() -> list[str]:
        return candidates(await Activity.get(activity.id))

    assert await found() == ["Ann"]
    assert description_of(await Activity.get(activity.id)).broken is None
    (row,) = run(
        db_driver,
        "MATCH (d:MatchesCriteria) RETURN d.depends_on AS depends_on, d.reach AS reach",
    )
    # (the wrapper asked for is a class the criteria depend on; an edge model is no node)
    assert row["depends_on"] == ["Person", "Witnessed", "InRole"]
    assert row["reach"] == analysis.LOCAL
    assert analysis.of(SearchPattern(criteria)).reach == analysis.LOCAL

    # (the deed written again: another role for one, a surer edge for another. The activity is not saved again)
    await Witnessed.Update(
        id=deed.id,
        label="A deed",
        witness=[
            witness(ann, notary, 9),
            witness(bea, notary, 9),
            witness(cat, scribe, 8),
        ],
    ).save()
    assert await found() == ["Ann"]
    await run_pending()
    assert await found() == ["Cat"]

    # (another document names one of them as a sure scribe)
    await Witnessed.Create(label="A will", witness=[witness(bea, scribe, 10)]).save()
    await run_pending()
    assert await found() == ["Bea", "Cat"]


@no_type_check
async def test_criteria_with_a_way_and_no_field_named(clear_database):
    Person, RoleType, Witnessed, Activity = models()
    scribe = await RoleType.Create(label="scribe").save()
    ann, bea = [await Person.Create(label=label).save() for label in ("Ann", "Bea")]
    await Witnessed.Create(
        label="A deed", witness=[witness(ann, scribe, 9), witness(bea, scribe, 1)]
    ).save()
    activity = await Activity.Create(
        label="A letter written",
        carried_out_by=[
            {
                "type": "MatchesCriteria",
                "wording": "the scribe",
                "criteria": a_sure_scribe(scribe, field=None),
            }
        ],
    ).save(detail=True)
    await run_pending()

    assert candidates(await Activity.get(activity.id)) == ["Ann"]
