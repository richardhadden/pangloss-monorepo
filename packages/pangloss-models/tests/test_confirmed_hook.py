"""`hooks.confirmed`: told, after the write, that a toolchain's suggestion was confirmed by a person; a listener that
fails is logged and never fails the caller"""

import datetime
import logging
import uuid

import pytest
from pangloss_models import hooks


def a_confirmation(**more) -> hooks.Confirmation:
    return hooks.Confirmation(
        **{
            "suggestion_id": uuid.uuid4(),
            "suggestion_type": "IdentificationByToolchain",
            "confirmed_type": "Identification",
            "head_id": uuid.uuid4(),
            "head_type": "Factoid",
            "user": "ann",
            "at": datetime.datetime.now(datetime.UTC),
            "entities": ((str(uuid.uuid4()), "Person"),),
            "direct": True,
            **more,
        }
    )


@pytest.mark.asyncio
async def test_tell_confirmed_with_no_listener_does_nothing(monkeypatch, caplog):
    monkeypatch.setattr(hooks, "confirmed", [])
    with caplog.at_level(logging.DEBUG, logger="pangloss.models.hooks"):
        await hooks.tell_confirmed(a_confirmation())
    assert [r for r in caplog.records if r.levelno > logging.DEBUG] == []


@pytest.mark.asyncio
async def test_tell_confirmed_tells_each_listener_in_turn(monkeypatch):
    told = []

    async def first(confirmation):
        told.append(("first", confirmation))

    async def second(confirmation):
        told.append(("second", confirmation))

    monkeypatch.setattr(hooks, "confirmed", [first, second])
    confirmation = a_confirmation(
        entities=(("a", "Person"), ("b", "Person"), ("c", "Group")), direct=False
    )
    await hooks.tell_confirmed(confirmation)
    assert told == [("first", confirmation), ("second", confirmation)]


@pytest.mark.asyncio
async def test_a_listener_that_raises_is_logged_and_the_others_are_still_told(
    monkeypatch, caplog
):
    told = []

    async def failing(confirmation):
        raise RuntimeError("no")

    async def second(confirmation):
        told.append(confirmation)

    monkeypatch.setattr(hooks, "confirmed", [failing, second])
    confirmation = a_confirmation()
    with caplog.at_level(logging.ERROR, logger="pangloss.models.hooks"):
        await hooks.tell_confirmed(confirmation)
    assert told == [confirmation]
    (record,) = [r for r in caplog.records if r.levelno >= logging.ERROR]
    message = record.getMessage()
    assert str(confirmation.suggestion_id) in message
    assert str(confirmation.head_id) in message and "Factoid" in message
    assert record.exc_info is not None and isinstance(record.exc_info[1], RuntimeError)
