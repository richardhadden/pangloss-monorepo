"""Criteria that name a class whose label is worked out by a template (the demo's `MemberOf`): a stored pattern is a
value, and the labels of a document are not worked out of what its values hold. (A save was refused: "MemberOf: its
label_template gives no label for what it holds", at `criteria.where`)"""

import importlib
from typing import no_type_check

import pangloss_criteria.models
import pytest
from pangloss_criteria import run_pending
from pangloss_models import Document, Entity, initialise

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Person(Entity):
        pass

    class Group(Entity):
        pass

    class MemberOf(Document):
        _meta = Document.Meta(label_template="{member} in {group}")
        member: Person
        group: Group

    class Activity(Document):
        _meta = Document.Meta(label_template="Done by {carried_out_by}")
        carried_out_by: Person | MatchesCriteria[Person]

    initialise()
    return Person, Group, MemberOf, Activity


@no_type_check
async def test_criteria_that_name_a_class_with_a_label_template_are_saved_as_they_are(
    clear_database,
):
    Person, Group, MemberOf, Activity = models()
    smith = await Person.Create(label="John Smith").save()
    posse = await Group.Create(label="The posse").save()
    await MemberOf.Create(
        member={"type": "Person", "id": smith.id},
        group={"type": "Group", "id": posse.id},
    ).save()
    criteria = {
        "type": "Person",
        "where": {
            "$incoming": [
                {
                    "type": "MemberOf",
                    "field": "member",
                    "where": {"group": {"is": str(posse.id)}},
                }
            ]
        },
    }

    saved = await Activity.Create(
        carried_out_by={
            "type": "MatchesCriteria",
            "wording": "A guy in the posse",
            "criteria": criteria,
        },
    ).save()
    await run_pending()

    read = await Activity.get(saved.id)
    # (nothing was written into the pattern)
    assert read.carried_out_by.criteria.data == criteria
    assert [each.label for each in read.carried_out_by.target] == ["John Smith"]
    # (in the label of its document, it is named by what the source says)
    assert read.label == "Done by A guy in the posse"


@no_type_check
async def test_a_description_is_named_in_a_label_by_its_wording_and_an_entity_by_its_label(
    clear_database,
):
    Person, Group, MemberOf, Activity = models()
    smith = await Person.Create(label="John Smith").save()
    posse = await Group.Create(label="The posse").save()
    criteria = {"type": "Person", "where": {"label": {"contains": "Smith"}}}
    named = await Activity.Create(
        carried_out_by={"type": "Person", "id": smith.id}
    ).save()
    assert (await Activity.get(named.id)).label == "Done by John Smith"

    described = await Activity.Create(
        carried_out_by={
            "type": "MatchesCriteria",
            "wording": "N. N.",
            "criteria": criteria,
        },
    ).save()
    await run_pending()
    read = await Activity.get(described.id)
    # (not by its candidates, though it has one now)
    assert [each.label for each in read.carried_out_by.target] == ["John Smith"]
    assert read.label == "Done by N. N."

    # (saved again as it was read, with its candidates: still by its wording)
    payload = read.model_dump(mode="json", by_alias=True)
    payload.pop("meta")
    await Activity.Update(**payload).save()
    assert (await Activity.get(described.id)).label == "Done by N. N."
    assert posse.id
