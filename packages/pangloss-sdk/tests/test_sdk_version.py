"""Telling the server which SDK this is, and what to do when it says it is out of date"""

import warnings
from uuid import uuid7

import pangloss_sdk
import pytest
from pangloss_models.exceptions import PanglossWriteError
from pangloss_sdk import (
    PanglossSdkMismatch,
    PanglossSdkOutOfDate,
    PanglossSdkOutOfDateWarning,
)
from pangloss_sdk import (
    client as sdk_client,
)
from pangloss_sdk.schemas import schema_hash
from sdk_support import FakeServer, head_json, make_models, settings

pytestmark = pytest.mark.asyncio

MANIFEST = {
    "project": "shop",
    "fingerprint": "abc123",
    "schema_position": {"shop": "0001_initial"},
}


def client_with(server, sdk=MANIFEST, **values):
    client = sdk_client.AsyncClient(
        settings(**values), server.async_transport(), None, sdk
    )
    sdk_client.install(client)
    return client


async def test_every_request_says_which_sdk_it_is():
    Person = make_models()
    server = FakeServer(lambda request: (200, head_json()))
    client_with(server)

    await Person.get(uuid7())

    headers = server.requests[0].headers
    assert headers["x-pangloss-sdk"] == "abc123"
    assert headers["x-pangloss-schema"] == schema_hash({"shop": "0001_initial"})


async def test_without_a_manifest_nothing_is_sent():
    Person = make_models()
    server = FakeServer(lambda request: (200, head_json()))
    client_with(server, sdk=None)
    await Person.get(uuid7())
    assert "x-pangloss-sdk" not in server.requests[0].headers


async def test_a_status_other_than_current_is_warned_of_once():
    Person = make_models()

    class Stale(FakeServer):
        def _respond(self, request):
            response = super()._respond(request)
            response.headers["x-pangloss-sdk-status"] = "schema-changed"
            return response

    client_with(Stale(lambda request: (200, head_json())))
    with pytest.warns(PanglossSdkOutOfDateWarning, match="schema-changed"):
        await Person.get(uuid7())
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await Person.get(uuid7())  # (once)


async def test_current_is_not_warned_of():
    Person = make_models()

    class Current(FakeServer):
        def _respond(self, request):
            response = super()._respond(request)
            response.headers["x-pangloss-sdk-status"] = "current"
            return response

    client_with(Current(lambda request: (200, head_json())))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await Person.get(uuid7())


async def test_a_refused_write_is_a_sdk_out_of_date_error():
    Person = make_models()
    body = {"detail": "update the SDK", "error": "PanglossSdkOutOfDate"}
    server = FakeServer(lambda request: (409, body))
    client_with(server, USERNAME="ada", PASSWORD="secret")

    with pytest.raises(PanglossSdkOutOfDate, match="update the SDK") as error:
        await Person.Create(label="x").save()
    assert not isinstance(error.value, PanglossWriteError)


def version_answer(**changes):
    body = {
        "project": "shop",
        "distribution": "shop-sdk",
        "version": "0.3",
        "fingerprint": "abc123",
        "schemaPosition": {"shop": "0001_initial"},
        "schemaHash": schema_hash({"shop": "0001_initial"}),
        **changes,
    }
    return lambda request: (200, body)


async def test_check_says_the_sdk_is_current():
    server = FakeServer(version_answer())
    client_with(server)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = await pangloss_sdk.check()
    assert result["current"] is True
    assert server.requests[0].url.path == "/api/sdk/version"


async def test_check_warns_of_a_different_package_and_of_a_changed_schema():
    client_with(FakeServer(version_answer(fingerprint="other")))
    with pytest.warns(PanglossSdkOutOfDateWarning):
        result = await pangloss_sdk.check()
    assert result["current"] is False and result["same_schema"] is True

    client_with(FakeServer(version_answer(schemaHash="ffff")))
    with pytest.warns(PanglossSdkOutOfDateWarning, match="moved on"):
        result = await pangloss_sdk.check()
    assert result["same_schema"] is False


async def test_check_raises_for_another_project_or_no_sdk():
    client_with(FakeServer(version_answer(project="other")))
    with pytest.raises(PanglossSdkMismatch, match="'shop'.*'other'"):
        await pangloss_sdk.check()

    client_with(
        FakeServer(lambda request: (503, {"detail": "The SDK is not built: x"}))
    )
    with pytest.raises(PanglossSdkMismatch, match="not built"):
        await pangloss_sdk.check()

    client_with(FakeServer(lambda request: (404, {"detail": "no"})))
    with pytest.raises(PanglossSdkMismatch):
        await pangloss_sdk.check()


async def test_check_without_a_manifest_only_reports():
    client_with(FakeServer(version_answer()), sdk=None)
    result = await pangloss_sdk.check()
    assert result["current"] is None and result["server"]["version"] == "0.3"
