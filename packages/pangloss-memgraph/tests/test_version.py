"""The version of a head node: 1, and 1 more for each update. An update can say which
version it was made from, and is refused if that is not the latest."""

import asyncio
from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossVersionConflictError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity

from .helpers import count_nodes

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
async def test_the_version_starts_at_one_and_goes_up_with_each_update(
    db_driver, clear_database
):
    class Person(Entity):
        pass

    class Statement(Document):
        text: str

    initialise()

    person = await Person.Create(label="John").save()
    statement = await Statement.Create(label="S", text="one").save()

    assert (await Person.get(person.id)).meta.version == 1
    assert (await Person.get_for_edit(person.id)).meta.version == 1
    assert (await Statement.get(statement.id)).meta.version == 1

    for number in (2, 3, 4):
        await Person.Update(id=person.id, label=f"John {number}").save()
        await Statement.Update(id=statement.id, label="S", text=str(number)).save()
        assert (await Person.get(person.id)).meta.version == number
        assert (await Person.get_for_edit(person.id)).meta.version == number
        assert (await Statement.get(statement.id)).meta.version == number

    # (a delete and an undelete are not updates)
    await Statement.delete(statement.id)
    await Statement.undelete(statement.id)
    assert (await Statement.get(statement.id)).meta.version == 4


@no_type_check
async def test_an_update_from_the_latest_version_is_made(db_driver, clear_database):
    class Statement(Document):
        text: str

    initialise()
    saved = await Statement.Create(label="S", text="one").save()

    await Statement.Update(id=saved.id, label="S", text="two").save(expected_version=1)
    await Statement.Update(id=saved.id, label="S", text="three").save(expected_version=2)
    read = await Statement.get(saved.id)
    assert read.text == "three"
    assert read.meta.version == 3


@no_type_check
async def test_an_update_from_an_old_version_is_refused_and_writes_nothing(
    db_driver, clear_database
):
    class Statement(Document):
        text: str

    initialise()
    saved = await Statement.Create(label="S", text="one").save()
    await Statement.Update(id=saved.id, label="S", text="two").save()

    with pytest.raises(PanglossVersionConflictError) as error:
        await Statement.Update(id=saved.id, label="S", text="mine").save(
            expected_version=1
        )
    assert error.value.current_version == 2
    assert "version 2, not 1" in str(error.value)

    # (a version ahead of the latest is no better)
    with pytest.raises(PanglossVersionConflictError):
        await Statement.Update(id=saved.id, label="S", text="mine").save(
            expected_version=3
        )

    read = await Statement.get(saved.id)
    assert read.text == "two"
    assert read.meta.version == 2
    assert count_nodes(db_driver, "PGUpdate") == 1


@no_type_check
async def test_without_an_expected_version_the_update_is_made_whatever_it_is(
    db_driver, clear_database
):
    class Statement(Document):
        text: str

    initialise()
    saved = await Statement.Create(label="S", text="one").save()
    for text in ("two", "three"):
        await Statement.Update(id=saved.id, label="S", text=text).save()
    assert (await Statement.get(saved.id)).meta.version == 3


@no_type_check
async def test_two_updates_from_the_same_version_at_once_only_one_is_made(
    db_driver, clear_database
):
    class Statement(Document):
        text: str

    initialise()
    saved = await Statement.Create(label="S", text="one").save()

    results = await asyncio.gather(
        *[
            Statement.Update(id=saved.id, label="S", text=f"from {n}").save(
                expected_version=1
            )
            for n in range(4)
        ],
        return_exceptions=True,
    )

    conflicts = [r for r in results if isinstance(r, PanglossVersionConflictError)]
    made = [r for r in results if not isinstance(r, BaseException)]
    assert len(made) == 1, results
    assert len(conflicts) == 3, results
    assert (await Statement.get(saved.id)).meta.version == 2
    assert count_nodes(db_driver, "PGUpdate") == 1


@no_type_check
async def test_updating_something_that_is_not_there_is_not_found_not_a_conflict(
    db_driver, clear_database
):
    from uuid import uuid7

    from pangloss_models.exceptions import PanglossNotFoundError

    class Statement(Document):
        text: str

    initialise()
    with pytest.raises(PanglossNotFoundError):
        await Statement.Update(id=uuid7(), label="S", text="x").save(expected_version=1)
