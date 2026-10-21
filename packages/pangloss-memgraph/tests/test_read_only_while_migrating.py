"""While `pangloss migrate` runs (it holds a lock) the database can be read and not written to"""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_memgraph.databases.memgraph import migration_backend as backend
from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossReadOnlyError, PanglossWriteError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity

from .helpers import count_nodes, run

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
async def test_nothing_is_written_while_the_lock_is_held_and_all_can_be_read(db_driver, clear_database):
    class Person(Entity):
        name: str

    class Statement(Document):
        text: str

    initialise()
    person = await Person.Create(label="Ann", name="Ann").save()
    statement = await Statement.Create(label="S", text="t").save()

    await backend.ensure_ready()
    await backend.lock("someone")
    try:
        # reading is as usual
        assert (await Person.get(id=person.id)).name == "Ann"
        assert (await Statement.list(page_number=1, page_size=10)).count == 1

        # ... writing is not, whichever way
        with pytest.raises(PanglossReadOnlyError, match="being migrated"):
            await Person.Create(label="Bob", name="Bob").save()
        with pytest.raises(PanglossReadOnlyError):
            await Statement.Update(id=statement.id, label="S", text="changed").save()
        with pytest.raises(PanglossReadOnlyError):
            await Statement.delete(id=statement.id)
        assert isinstance(PanglossReadOnlyError("x"), PanglossWriteError)
        assert count_nodes(db_driver, "Person") == 1
        assert (await Statement.get(id=statement.id)).text == "t"
    finally:
        await backend.unlock()

    # once it is released, as before
    await Person.Create(label="Bob", name="Bob").save()
    assert count_nodes(db_driver, "Person") == 2


OUTSIDER: dict = {"model": None, "refused": []}


async def try_to_write(tx, state):
    """(a change of a migration, that has something else write while it runs)"""
    try:
        await OUTSIDER["model"].Create(label="Intruder", name="x").save()
    except PanglossReadOnlyError as error:
        OUTSIDER["refused"].append(error)


@no_type_check
async def test_a_migration_that_is_running_holds_the_lock(db_driver, clear_database):
    """What `pangloss migrate` does (the lock, then `apply`): a write made by a change in the middle of
    it, by something else, is refused"""
    from pangloss_models.migrations import changes as c
    from pangloss_models.migrations.files import EMPTY_SNAPSHOT, Migration

    class Person(Entity):
        name: str

    initialise()
    OUTSIDER.update(model=Person, refused=[])

    migration = Migration(
        app="locked", name="0001_initial", changes=(c.RunPython(function=try_to_write),)
    )
    await backend.ensure_ready()
    await backend.lock()
    try:
        await backend.apply([migration], EMPTY_SNAPSHOT)
    finally:
        await backend.unlock()
    assert len(OUTSIDER["refused"]) == 1
    assert count_nodes(db_driver, "Person") == 0
