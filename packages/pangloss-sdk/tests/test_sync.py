"""The blocking database module does the same, with the blocking client"""

from uuid import uuid7

import pangloss_sdk

from pangloss_models import initialise
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_registry import ModelRegistry
from pangloss_core.settings import ClientSettings
from pangloss_sdk.databases.api_sync import exposed_functions as sync_api

from sdk_support import FakeServer, head_json, reference_json, sync_client


def make_sync_models():
    ModelRegistry._reset()
    ClientSettings(
        INSTALLED_APPS=[], DATABASE_MODULE="pangloss_sdk.databases.api_sync"
    )

    class Person(Entity):
        pass

    initialise()
    return Person


def test_the_functions_are_bound_and_block():
    Person = make_sync_models()
    id = uuid7()
    server = FakeServer(lambda request: (200, head_json(id)))
    sync_client(server)

    person = Person.get(id)  # (no await)

    assert isinstance(person, Person.HeadView)
    assert Person.Create.save is sync_api.create_head_node


def test_a_write_logs_in_and_saves():
    Person = make_sync_models()
    server = FakeServer(lambda request: (201, reference_json(label="Ada")))
    sync_client(server, USERNAME="ada", PASSWORD="secret")

    created = Person.Create(label="Ada").save()

    assert created.label == "Ada"
    assert server.logins == 1


def test_an_expired_token_is_renewed():
    Person = make_sync_models()
    server = FakeServer(lambda request: (200, head_json()))
    sync_client(server, USERNAME="ada", PASSWORD="secret")
    Person.get_for_edit(uuid7())

    server.expire_access_tokens()
    Person.get_for_edit(uuid7())

    assert (server.logins, server.refreshes) == (1, 1)


def test_connect_sync_binds_the_blocking_module(an_app):
    server = FakeServer(lambda request: (200, head_json(label="Ada")))
    pangloss_sdk.connect(
        "http://pangloss.test", apps=[an_app], sync=True, transport=server.sync_transport()
    )
    from an_sdk_test_app.models import Person  # type: ignore[import-not-found]

    assert Person.get(uuid7()).label == "Ada"  # type: ignore[attr-defined]
    pangloss_sdk.disconnect_sync()
