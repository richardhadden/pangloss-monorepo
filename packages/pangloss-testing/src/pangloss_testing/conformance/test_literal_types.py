"""The literal types that `pangloss_models.literals` admits are written and read back as the class declares them, on
either backend: pydantic's standard types stored as text with a format, the time types the databases have, a
`Literal[...]`, a set and a tuple; and the default a class declares is what is read back when a field was left out."""

import datetime
import ipaddress
import pathlib
import re
import uuid
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import Literal, no_type_check

import pytest
from pangloss_models import Document, Entity, Match, initialise
from pydantic import ByteSize, EmailStr, HttpUrl, ValidationError

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


class Colour(Enum):
    RED = "red"
    BLUE = "blue"


@no_type_check
async def test_standard_types_are_stored_as_text_with_a_format_and_read_back_as_themselves(
    db_driver, clear_database
):
    class Record(Document):
        identifier: uuid.UUID
        homepage: HttpUrl
        email: EmailStr
        address: ipaddress.IPv4Address
        path: pathlib.Path
        pattern: re.Pattern
        share: Fraction
        size: ByteSize
        identifiers: list[uuid.UUID]

    initialise()

    identifier = uuid.uuid4()
    saved = await Record.Create(
        label="r",
        identifier=identifier,
        homepage="https://example.org/a?b=1",
        email="a@example.org",
        address="10.0.0.1",
        path="/var/data",
        pattern="a+b",
        share="1/3",
        size="1 KiB",
        identifiers=[identifier],
    ).save()

    node = run(db_driver, "MATCH (n:Record) RETURN n")[0]["n"]
    assert node["identifier"] == str(identifier)
    assert node["homepage"] == "https://example.org/a?b=1"
    assert node["email"] == "a@example.org"
    assert node["address"] == "10.0.0.1"
    assert node["path"] == "/var/data"
    assert node["pattern"] == "a+b"
    assert node["share"] == "1/3"
    assert node["size"] == 1024
    assert node["identifiers"] == [str(identifier)]

    read = await Record.get(saved.id)
    assert read.identifier == identifier and isinstance(read.identifier, uuid.UUID)
    assert str(read.homepage) == "https://example.org/a?b=1"
    assert read.email == "a@example.org"
    assert read.address == ipaddress.IPv4Address("10.0.0.1")
    assert read.path == pathlib.Path("/var/data")
    assert read.pattern.pattern == "a+b"
    assert read.share == Fraction(1, 3)
    assert read.size == 1024
    assert read.identifiers == [identifier]


@no_type_check
async def test_a_time_a_duration_and_an_aware_datetime_are_stored_as_the_database_has_them(
    db_driver, clear_database
):
    class Event(Document):
        at: datetime.time
        lasted: datetime.timedelta
        recorded: datetime.datetime

    initialise()

    at = datetime.time(13, 45, 30)
    lasted = datetime.timedelta(days=1, hours=2, minutes=3, seconds=4, microseconds=5)
    recorded = datetime.datetime(2020, 5, 6, 7, 8, 9, tzinfo=datetime.UTC)
    saved = await Event.Create(
        label="e", at=at, lasted=lasted, recorded=recorded
    ).save()

    read = await Event.get(saved.id)
    assert read.at == at
    assert read.lasted == lasted
    assert read.recorded == recorded
    # (the offset survives: what is read back is aware, and the same instant)
    assert read.recorded.tzinfo is not None
    assert read.recorded.utcoffset() == datetime.timedelta(0)


@no_type_check
async def test_a_literal_choice_a_set_and_a_tuple_are_stored_as_values_and_lists(
    db_driver, clear_database
):
    class Record(Document):
        kind: Literal["a", "b"]
        level: Literal[1, 2, 3]
        tags: set[str]
        point: tuple[float, float]

    initialise()
    saved = await Record.Create(
        label="r", kind="b", level=2, tags=["x", "x", "y"], point=[1.5, 2.5]
    ).save()

    node = run(db_driver, "MATCH (n:Record) RETURN n")[0]["n"]
    assert node["kind"] == "b" and node["level"] == 2
    assert sorted(node["tags"]) == ["x", "y"]
    assert node["point"] == [1.5, 2.5]

    read = await Record.get(saved.id)
    assert read.kind == "b" and read.level == 2
    assert read.tags == {"x", "y"}
    assert read.point == (1.5, 2.5)
    with pytest.raises(ValidationError):
        Record.Create(label="r", kind="c", level=2, tags=[], point=[1, 2])


@no_type_check
async def test_a_default_the_class_declares_is_what_is_read_back_when_the_field_was_left_out(
    db_driver, clear_database
):
    class Record(Document):
        count: int = 0
        colour: Colour = Colour.RED
        tags: list[str] = []
        price: Decimal | None = Decimal("1.50")

    initialise()
    saved = await Record.Create(label="r").save()

    # (the default is a value like any other: it is written)
    node = run(db_driver, "MATCH (n:Record) RETURN n")[0]["n"]
    assert node["count"] == 0 and node["colour"] == "red" and node["tags"] == []
    assert node["price"] == "1.50"

    read = await Record.get(saved.id)
    assert read.count == 0 and read.colour is Colour.RED and read.tags == []
    assert read.price == Decimal("1.50")

    # (an update that leaves it out puts the default back)
    await Record.Update(id=saved.id, label="r", count=3).save()
    assert (await Record.get(saved.id)).count == 3
    await Record.Update(id=saved.id, label="r").save()
    assert (await Record.get(saved.id)).count == 0


@no_type_check
async def test_an_optional_list_is_not_written_when_it_is_left_out(
    db_driver, clear_database
):
    class Record(Document):
        tags: list[str] | None = None
        kept: list[str] = []

    initialise()
    saved = await Record.Create(label="r").save()
    node = run(db_driver, "MATCH (n:Record) RETURN n")[0]["n"]
    assert "tags" not in node and node["kept"] == []
    read = await Record.get(saved.id)
    assert read.tags is None and read.kept == []


@no_type_check
async def test_a_field_with_a_format_is_searched_as_the_text_it_is_stored_as(
    db_driver, clear_database
):
    class Record(Document):
        identifier: uuid.UUID
        homepage: HttpUrl
        at: datetime.time

    initialise()
    first, second = uuid.uuid4(), uuid.uuid4()
    await Record.Create(
        label="one",
        identifier=first,
        homepage="https://a.org/x",
        at=datetime.time(9, 0),
    ).save()
    await Record.Create(
        label="two",
        identifier=second,
        homepage="https://b.org/y",
        at=datetime.time(17, 0),
    ).save()

    found = await Record.search(Match(where={"identifier": {"eq": str(first)}}))
    assert [r.label for r in found.results] == ["one"]
    found = await Record.search(Match(where={"homepage": {"starts_with": "https://b"}}))
    assert [r.label for r in found.results] == ["two"]
    found = await Record.search(Match(where={"at": {"gt": "12:00:00"}}))
    assert [r.label for r in found.results] == ["two"]


@no_type_check
async def test_a_key_the_model_has_no_field_for_is_refused_over_the_api(
    db_driver, clear_database
):
    from pangloss_api import create_app

    from .test_api_models import client_for, logged_in

    class Person(Entity):
        pass

    class Record(Document):
        text: str
        about: Person

    app = create_app()
    async with client_for(app) as client:
        john = await logged_in(client)
        person = (
            await client.post("/api/Person", json={"label": "P"}, headers=john)
        ).json()
        good = {
            "label": "r",
            "text": "t",
            "about": {"type": "Person", "id": person["id"]},
        }
        assert (
            await client.post("/api/Record", json=good, headers=john)
        ).status_code == 201

        refused = await client.post(
            "/api/Record", json={**good, "txet": "typo"}, headers=john
        )
        assert refused.status_code == 422
        problems = refused.json()["detail"]
        assert problems[0]["loc"] == ["body", "txet"]
        assert "not permitted" in problems[0]["msg"]
        assert run(db_driver, "MATCH (n:Record) RETURN count(n) AS c")[0]["c"] == 1
