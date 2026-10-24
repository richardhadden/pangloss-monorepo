"""`connect()`, and going through pages"""

from uuid import uuid7

import pangloss_sdk
import pytest
from pangloss_core import settings as core_settings
from sdk_support import FakeServer, head_json, make_models, reference_json

pytestmark = pytest.mark.asyncio


async def test_connect_initialises_the_models_of_the_apps_with_the_api_bound(an_app):
    server = FakeServer(lambda request: (200, head_json(label="Ada")))
    pangloss_sdk.connect(
        "http://pangloss.test", apps=[an_app], transport=server.async_transport()
    )
    from an_sdk_test_app.models import Person  # type: ignore[import-not-found]

    person = await Person.get(uuid7())  # type: ignore[attr-defined]

    assert person.label == "Ada"
    assert isinstance(core_settings.SETTINGS, pangloss_sdk.SdkSettings)
    assert core_settings.SETTINGS.DATABASE_MODULE == "pangloss_sdk.databases.api"
    await pangloss_sdk.disconnect()


async def test_settings_come_from_the_environment(an_app, monkeypatch):
    monkeypatch.setenv("PANGLOSS_URL", "http://from-the-environment.test")
    monkeypatch.setenv("PANGLOSS_USERNAME", "ada")
    server = FakeServer()
    pangloss_sdk.connect(apps=[an_app], transport=server.async_transport())

    settings = core_settings.SETTINGS
    assert str(settings.URL) == "http://from-the-environment.test/"  # type: ignore[attr-defined]
    assert settings.USERNAME == "ada"  # type: ignore[attr-defined]
    await pangloss_sdk.disconnect()


async def test_using_a_model_function_before_connecting_says_so():
    Person = make_models()
    with pytest.raises(pangloss_sdk.PanglossNotConnected):
        await Person.get(uuid7())


async def test_iterate_goes_through_every_page():
    Person = make_models()
    pages = {
        "1": ([reference_json(label="a"), reference_json(label="b")], 2),
        "2": ([reference_json(label="c")], None),
    }

    def answer(request):
        results, next_page = pages[request.url.params["page"]]
        return 200, {
            "results": results,
            "count": 3,
            "page": int(request.url.params["page"]),
            "pageSize": 2,
            "nextPage": next_page,
            "previousPage": None,
        }

    server = FakeServer(answer)
    pangloss_sdk.connect("http://pangloss.test", transport=server.async_transport())
    # (connect() has initialised the models: use the ones that are registered)
    labels = [item.label async for item in pangloss_sdk.iterate(Person.list)]  # type: ignore[attr-defined]

    assert labels == ["a", "b", "c"]
    assert len(server.requests) == 2
    await pangloss_sdk.disconnect()
