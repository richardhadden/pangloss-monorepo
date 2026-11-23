"""`hooks.resolved`: told, after the write, that a stand-in was resolved; a listener that fails is logged and never
fails the caller"""

import datetime
import logging
import uuid

import pytest
from pangloss_models import hooks


def a_resolution(**more) -> hooks.Resolution:
    return hooks.Resolution(
        **{
            "stand_in_id": uuid.uuid4(),
            "stand_in_type": "Unreconciled",
            "head_id": uuid.uuid4(),
            "head_type": "Factoid",
            "entity_id": uuid.uuid4(),
            "entity_type": "Person",
            "user": "ann",
            "at": datetime.datetime.now(datetime.UTC),
            "direct": True,
            **more,
        }
    )


@pytest.mark.asyncio
async def test_tell_resolved_with_no_listener_does_nothing(monkeypatch, caplog):
    monkeypatch.setattr(hooks, "resolved", [])
    with caplog.at_level(logging.DEBUG, logger="pangloss.models.hooks"):
        await hooks.tell_resolved(a_resolution())
    assert [r for r in caplog.records if r.levelno > logging.DEBUG] == []


@pytest.mark.asyncio
async def test_tell_resolved_tells_each_listener_in_turn(monkeypatch):
    told = []

    async def first(resolution):
        told.append(("first", resolution))

    async def second(resolution):
        told.append(("second", resolution))

    monkeypatch.setattr(hooks, "resolved", [first, second])
    resolution = a_resolution(label="John Smith", stood_for="Person", direct=False)
    await hooks.tell_resolved(resolution)
    assert told == [("first", resolution), ("second", resolution)]
    # (the defaults: no label, nothing stood for)
    bare = a_resolution()
    assert (bare.label, bare.stood_for) == (None, None)


@pytest.mark.asyncio
async def test_a_listener_that_raises_is_logged_and_the_others_are_still_told(
    monkeypatch, caplog
):
    told = []

    async def failing(resolution):
        raise RuntimeError("no")

    async def second(resolution):
        told.append(resolution)

    monkeypatch.setattr(hooks, "resolved", [failing, second])
    resolution = a_resolution()
    with caplog.at_level(logging.ERROR, logger="pangloss.models.hooks"):
        await hooks.tell_resolved(resolution)
    assert told == [resolution]
    (record,) = [r for r in caplog.records if r.levelno >= logging.ERROR]
    message = record.getMessage()
    assert str(resolution.stand_in_id) in message
    assert str(resolution.head_id) in message and "Factoid" in message
    assert record.exc_info is not None and isinstance(record.exc_info[1], RuntimeError)
