"""The SDK against the real API, with the data in Memgraph.

The client's functions (`pangloss_sdk.databases.api.exposed_functions`) are called by hand,
over an in-process connection to the app, while the models stay bound to Memgraph: what the
SDK reads through the API must equal what the database module reads directly, and what it
raises must be what the database module raises.
"""

import pathlib
import sys
from uuid import uuid7

import httpx2 as httpx
import pytest
import pytest_asyncio
from pangloss_api.app import create_app
from pangloss_core import settings as core_settings
from pangloss_models import initialise
from pangloss_models.exceptions import (
    PanglossEntityInUseError,
    PanglossNotFoundError,
    PanglossReferenceError,
    PanglossVersionConflictError,
)
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry
from pangloss_sdk import client as sdk_client
from pangloss_sdk.databases.api import exposed_functions as sdk
from pangloss_sdk.settings import SdkSettings
from pangloss_users import service

sys.path.insert(
    0, str(pathlib.Path(__file__).parents[2] / "pangloss-models/tests/support")
)

import kitchen_sink
import sample_data

from .test_edit_cycle import differences, with_real_ids, without

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


async def sdk_for(app, username="sdkuser"):
    """The SDK's client, connected to the app in-process (the models' settings are kept)"""
    if await service.get_user(username) is None:
        await service.create_user(username, f"{username}@example.com", PASSWORD)
    server_settings = core_settings.SETTINGS
    try:
        settings = SdkSettings(
            URL="http://test",  # type: ignore[arg-type]
            USERNAME=username,
            PASSWORD=PASSWORD,  # type: ignore[arg-type]
        )
    finally:
        core_settings.SETTINGS = server_settings
    client = sdk_client.AsyncClient(settings, httpx.ASGITransport(app=app))
    sdk_client.install(client)
    return client


@pytest_asyncio.fixture(loop_scope="session")
async def through_the_api(clear_database):
    clients = []

    async def connect(app):
        clients.append(await sdk_for(app))
        return clients[0]

    yield connect
    for client in clients:
        await client.close()
    sdk_client.install(None)


async def read_directly_and_through_the_api(model, id, edit=False):
    entity = model.__metatype__ == "Entity"
    if edit and entity:
        return await model.get_for_edit(id), await sdk.get_entity_for_edit(model, id)
    if entity:
        return await model.get(id), await sdk.get_entity(model, id)
    return await model.get(id), await sdk.get_document(model, id)


async def test_every_kind_of_model_through_the_api_reads_as_it_does_directly(
    through_the_api,
):
    kitchen_sink.declare()
    initialise()
    app = create_app()
    await through_the_api(app)
    heads = {
        m.__name__: m
        for m in ModelRegistry._models
        if getattr(m, "__metatype__", None) in ("Document", "Entity")
    }
    samplable = [m for m in heads.values() if not getattr(m._meta, "abstract", False)]
    failures: list[str] = []

    for model in samplable:
        for choice in sample_data.CHOICES:
            label = f"{model.__name__} (choice {choice})"
            step = "sampling"
            try:
                sampler = sample_data.Sampler(choice)
                payload = sampler.head(model)
                payload.pop("type")
                ids = {}
                for entity_name, fake in sampler.references:
                    entity = heads[entity_name]
                    made = await sdk.create_head_node(
                        entity.Create(**sample_data.sample_payload(entity))
                    )
                    ids[fake] = made.id
                payload = with_real_ids(payload, ids)

                step = "creating through the API"
                created = await sdk.create_head_node(model.Create(**payload))

                step = "reading"
                directly, through = await read_directly_and_through_the_api(
                    model, created.id
                )
                assert through is not None, "not found through the API"
                assert directly is not None
                same = differences(directly.model_dump(), through.model_dump())
                assert not same, f"the API read differs: {same[:4]}"

                step = "reading to edit"
                directly, through = await read_directly_and_through_the_api(
                    model, created.id, edit=True
                )
                assert through is not None
                same = differences(directly.model_dump(), through.model_dump())
                assert not same, f"the edit read differs: {same[:4]}"

                step = "saving the edit through the API"
                dumped = without(through.model_dump())
                await sdk.update_head_node(
                    model.Update(**dumped), expected_version=through.meta.version
                )

                step = "reading again"
                directly, through = await read_directly_and_through_the_api(
                    model, created.id
                )
                assert through is not None and directly is not None
                same = differences(directly.model_dump(), through.model_dump())
                assert not same, f"the API read after the edit differs: {same[:4]}"
                _, edited_again = await read_directly_and_through_the_api(
                    model, created.id, edit=True
                )
                assert edited_again is not None
                changed = differences(dumped, without(edited_again.model_dump()))
                assert not changed, (
                    f"changed by saving what was read, unchanged: {changed[:4]}"
                )
            except Exception as error:
                failures.append(
                    f"{label} while {step}: {type(error).__name__}: "
                    f"{str(error).replace(chr(10), ' ')[:260]}"
                )

    assert not failures, "\n" + "\n".join(failures)


async def test_lists_and_errors_are_those_of_the_database_module(through_the_api):
    class Person(Entity):
        pass

    class Statement(Document):
        text: str
        about: Person

    initialise()
    app = create_app()
    await through_the_api(app)

    ada = await sdk.create_head_node(Person.Create(label="Ada"))
    bo = await sdk.create_head_node(Person.Create(label="Bo"))
    statement = await sdk.create_head_node(
        Statement.Create(label="S", text="t", about={"type": "Person", "id": ada.id}),
        detail=True,
    )
    assert isinstance(statement, Statement.HeadView)
    assert statement.about.id == ada.id  # type: ignore[attr-defined]

    # lists
    for terms, page_size in ((None, None), ("a", None), (None, 1)):
        directly = await Person.list(search_terms=terms, page_size=page_size)  # type: ignore[attr-defined]
        through = await sdk.list_items(Person, search_terms=terms, page_size=page_size)
        assert through.model_dump() == directly.model_dump()
    assert (await sdk.list_items(Person)).count == 2

    # versions
    edit = await sdk.get_entity_for_edit(Person, bo.id)
    assert edit is not None and edit.meta.version == 1
    await sdk.update_head_node(Person.Update(id=bo.id, label="Bob"), expected_version=1)
    with pytest.raises(PanglossVersionConflictError) as conflict:
        await sdk.update_head_node(
            Person.Update(id=bo.id, label="Bobby"), expected_version=1
        )
    assert conflict.value.current_version == 2
    with pytest.raises(PanglossVersionConflictError) as directly_raised:
        await Person.Update(id=bo.id, label="Bobby").save(expected_version=1)  # type: ignore[attr-defined]
    assert directly_raised.value.current_version == 2

    # missing, and a bad reference
    assert await sdk.get_entity(Person, uuid7()) is None
    with pytest.raises(PanglossNotFoundError):
        await sdk.update_head_node(Person.Update(id=uuid7(), label="x"))
    with pytest.raises(PanglossNotFoundError):
        await sdk.delete_entity(Person, uuid7())
    with pytest.raises(PanglossReferenceError):
        await sdk.create_head_node(
            Statement.Create(
                label="S", text="t", about={"type": "Person", "id": uuid7()}
            )
        )

    # an entity in use cannot be deleted; a document can, and be brought back
    with pytest.raises(PanglossEntityInUseError) as in_use:
        await sdk.delete_entity(Person, ada.id)
    assert [item["id"] for item in in_use.value.referenced_by] == [str(statement.id)]
    await sdk.delete_document(Statement, statement.id)
    assert await sdk.get_document(Statement, statement.id) is None
    await sdk.undelete_document(Statement, statement.id)
    assert await sdk.get_document(Statement, statement.id) is not None
