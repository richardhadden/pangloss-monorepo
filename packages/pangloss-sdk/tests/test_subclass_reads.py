"""A read by a class gives an item of a subclass as that subclass"""

import datetime
from types import SimpleNamespace
from uuid import uuid7

from pangloss_models import initialise
from pangloss_models.model_bases.entity import Entity
from pangloss_sdk import protocol
from pangloss_sdk.client import client_arguments
from pangloss_sdk.settings import SdkSettings


def models():
    class Base(Entity):
        pass

    class Sub(Base):
        extra: str | None = None

    initialise()
    return Base, Sub


def answer(payload, status=200):
    return SimpleNamespace(
        status_code=status, is_success=status < 400, json=lambda: payload
    )


def head(type_, **more):
    return {
        "type": type_,
        "id": str(uuid7()),
        "label": "x",
        "urls": [],
        "meta": {
            "createdBy": "john",
            "createdWhen": datetime.datetime(2026, 1, 1).isoformat(),
            "updatedBy": None,
            "updatedWhen": None,
            "version": 1,
        },
        **more,
    }


def test_the_head_view_is_that_of_the_subclass_the_server_says_it_is():
    Base, Sub = models()

    read = protocol.got(Base, answer(head("Sub", extra="x")))

    assert isinstance(read, Sub.HeadView) and read.extra == "x"


def test_the_edit_view_is_the_subclasss_too():
    Base, Sub = models()

    read = protocol.got_for_edit(Base, answer(head("Sub", extra="x")))

    assert isinstance(read, Sub.EditView)


def test_an_item_of_the_class_itself_and_a_missing_one_are_as_before():
    Base, Sub = models()

    assert isinstance(protocol.got(Base, answer(head("Base"))), Base.HeadView)
    assert protocol.got(Base, answer({}, 404)) is None


def test_a_type_that_is_not_a_subclass_is_not_trusted():
    Base, Sub = models()

    class Other(Entity):
        pass

    initialise()
    try:
        protocol.got(Sub, answer(head("Other")))
    except Exception as error:
        assert "type" in str(error)
    else:  # pragma: no cover
        raise AssertionError("an Other was read as a Sub")


def test_the_client_follows_the_redirect_to_the_subclasss_edit_route():
    assert (
        client_arguments(SdkSettings(URL="http://x.test/"))["follow_redirects"] is True
    )
