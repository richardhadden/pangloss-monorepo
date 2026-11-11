"""Labels worked out by a template (implementation_docs/label-templates.md): on a write, the label of each automatic node
is worked out from what it holds, naming what it refers to by the label in the database; stored with `label_auto`;
read back; worked out again on an update; a label written by hand is kept"""

from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    Entity,
    LabelTemplate,
    PanglossWriteRefused,
    ReifiedRelation,
    initialise,
)

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def declare():
    class Person(Entity):
        forename: str | None = None
        surname: str | None = None
        _meta = Entity.Meta(
            label_template=LabelTemplate("{forename} {surname}", "{surname}")
        )

    class Identification[T](ReifiedRelation[T]):
        pass

    class Bequest(Document):
        item: str
        recipient: Identification[Person]
        _meta = Document.Meta(label_template="{item} to {recipient}")

    class Will(Document):
        testator: Person
        bequests: list[Bequest]
        _meta = Document.Meta(
            label_template='Will of {testator}[: {bequests|join("; ", "; and ")}]'
        )

    initialise()
    return Person, Will


def bequest(item, person, **more):
    return {
        "type": "Bequest",
        "item": item,
        "recipient": {"type": "Identification", "target": [person]},
        **more,
    }


@no_type_check
async def test_labels_are_worked_out_on_create_from_what_is_held_and_referred_to(
    db_driver, clear_database
):
    Person, Will = declare()
    anne = await Person.Create(forename="Anne", surname="Hathaway").save()
    assert anne.label == "Anne Hathaway"
    judith = await Person.Create(surname="Quiney").save()

    made = await Will.Create(
        testator={"type": "Person", "id": anne.id},
        bequests=[
            bequest("a cup", {"type": "Person", "id": judith.id}),
            bequest(
                "my bed",
                {"type": "Person", "id": anne.id},
                label="The second-best bed, by hand",
            ),
        ],
    ).save()
    assert made.label == (
        "Will of Anne Hathaway: a cup to Quiney; and The second-best bed, by hand"
    )
    stored = run(
        db_driver,
        "MATCH (n:Bequest) RETURN n.label AS label, n.label_auto AS auto ORDER BY n.label",
    )
    assert [(row["label"], row["auto"]) for row in stored] == [
        ("The second-best bed, by hand", False),
        ("a cup to Quiney", True),
    ]
    read = await Will.get(made.id)
    assert read.label_auto is True
    assert [b.label_auto for b in read.bequests] == [True, False]


@no_type_check
async def test_an_update_works_the_automatic_labels_out_again_and_keeps_those_by_hand(
    db_driver, clear_database
):
    Person, Will = declare()
    anne = await Person.Create(forename="Anne", surname="Hathaway").save()
    made = await Will.Create(
        testator={"type": "Person", "id": anne.id},
        bequests=[bequest("a cup", {"type": "Person", "id": anne.id})],
    ).save()
    # (the label sent back is the old one: as `label_auto` is true, it is replaced)
    edit = (await Will.get(made.id)).model_dump()
    edit["bequests"][0]["item"] = "two cups"
    edit["bequests"].append(
        bequest("a ring", {"type": "Person", "id": anne.id}, label="A ring, by hand")
    )
    await Will.Update(**edit).save()
    read = await Will.get(made.id)
    assert read.label == (
        "Will of Anne Hathaway: two cups to Anne Hathaway; and A ring, by hand"
    )

    # (an entity renamed later: the label of what names it is as it was made)
    await Person.Update(
        **(await Person.get_for_edit(anne.id)).model_dump() | {"forename": "Agnes"}
    ).save()
    assert (await Person.get(anne.id)).label == "Agnes Hathaway"
    assert (await Will.get(made.id)).label.startswith("Will of Anne Hathaway")


@no_type_check
async def test_a_label_the_template_gives_nothing_for_is_refused(
    db_driver, clear_database
):
    Person, _ = declare()
    with pytest.raises(PanglossWriteRefused, match="gives no label"):
        await Person.Create().save()
    assert run(db_driver, "MATCH (n:Person) RETURN n") == []
