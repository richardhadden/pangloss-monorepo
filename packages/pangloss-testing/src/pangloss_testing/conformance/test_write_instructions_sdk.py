"""The instructions of one write through the SDK, against the real API (`hooks.declare_write_instruction`): the SDK's
create, update and with-companions send them, the server's write routes give them to the save, and a refusal comes
back as the database module raises it"""

from typing import no_type_check

import pytest
from pangloss_api import create_app
from pangloss_models import (
    Companion,
    Document,
    Entity,
    PanglossInstructionError,
    initialise,
)
from pangloss_sdk import PanglossRequestError
from pangloss_sdk.databases.api import exposed_functions as sdk

from .test_sdk_contract import through_the_api  # noqa: F401
from .test_write_instructions_live import (  # noqa: F401
    NAME,
    counts,
    instructed,
    marked,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
async def test_create_update_and_with_companions_send_them_through_the_api(
    db_driver,
    through_the_api,  # noqa: F811
    instructed,  # noqa: F811
):
    class Person(Entity):
        _meta = Entity.Meta(
            companions=[
                Companion(name="naming", document="Naming", entity_field="named")
            ]
        )

    class Naming(Document):
        named: Person

    initialise()
    await through_the_api(create_app())

    ann = await sdk.create_head_node(
        Person.Create(label="Ann"), instructions={NAME: True}
    )
    bo = await sdk.create_head_node(Person.Create(label="Bo"))
    assert marked(db_driver) == {str(ann.id)}
    await sdk.update_head_node(
        Person.Update(id=bo.id, label="Bob"),
        expected_version=1,
        instructions={NAME: True},
    )
    await sdk.update_head_node(
        Person.Update(id=ann.id, label="Ann"),
        expected_version=1,
        instructions={NAME: False},
    )
    assert marked(db_driver) == {str(bo.id)}
    cy, (naming,) = await sdk.save_with_companions(
        Person.Create(label="Cy"),
        {"naming": {"label": "Cy named"}},
        instructions={NAME: "true"},
    )
    assert marked(db_driver) == {str(bo.id), str(cy.id), str(naming.id)}
    assert ("Person", {NAME: "true"}) in instructed.asked
    assert ("Naming", {NAME: "true"}) in instructed.asked

    # refused before anything is written: a bad value as the database module refuses it, an undeclared name as a
    # parameter the route does not have
    before = counts(db_driver)
    with pytest.raises(PanglossInstructionError, match="not 'maybe'"):
        await sdk.create_head_node(
            Person.Create(label="Di"), instructions={NAME: "maybe"}
        )
    with pytest.raises(PanglossInstructionError):
        await sdk.update_head_node(
            Person.Update(id=bo.id, label="B"), instructions={NAME: "maybe"}
        )
    with pytest.raises(
        PanglossRequestError, match="Unknown query parameter 'nonsense'"
    ):
        await sdk.create_head_node(
            Person.Create(label="Di"), instructions={"nonsense": True}
        )
    with pytest.raises(PanglossRequestError, match="nonsense"):
        await sdk.save_with_companions(
            Person.Create(label="Di"), {}, instructions={"nonsense": True}
        )
    assert counts(db_driver) == before
