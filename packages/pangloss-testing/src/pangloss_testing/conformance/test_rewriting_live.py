"""A head written again with a part replaced (`pangloss_models.rewriting`): `prepare_rewrite` reads, changes and
validates, and writes nothing; `rewrite` saves it based on the version read or given, with the options of `save`"""

from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    Entity,
    PanglossVersionConflictError,
    initialise,
    prepare_rewrite,
    rewrite,
)
from pangloss_models.rewriting import Missing, Prepared, replaced
from pydantic import ValidationError
from uuid import uuid7

from .test_write_instructions_live import (  # noqa: F401
    NAME,
    counts,
    instructed,
    marked,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def declare():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(create_directly=False)
        about: Person

    class Letter(Document):
        statements: list[Statement]

    initialise()
    return Person, Place, Letter


def ref(item) -> dict:
    return {"type": type(item)._owner.__name__, "id": item.id}


@no_type_check
async def a_letter():
    Person, Place, Letter = declare()
    ann = await Person.Create(label="Ann").save()
    bo = await Person.Create(label="Bo").save()
    paris = await Place.Create(label="Paris").save()
    letter = await Letter.Create(
        label="L", statements=[{"type": "Statement", "label": "S", "about": ref(ann)}]
    ).save(detail=True)
    return Letter, letter, bo, paris


def about(view) -> str:
    return str(view.statements[0].id)


@no_type_check
async def test_prepare_rewrite_makes_the_update_and_writes_nothing(
    db_driver, clear_database
):
    Letter, letter, bo, paris = await a_letter()
    before = counts(db_driver)

    def to_bo(data):
        return replaced(data, about(letter), lambda part: {**part, "about": ref(bo)})

    prepared = await prepare_rewrite(Letter, letter.id, to_bo)
    assert isinstance(prepared, Prepared)
    assert prepared.version == 1 and prepared.view.id == letter.id
    assert prepared.update.statements[0].about.id == bo.id

    assert await prepare_rewrite(Letter, uuid7(), to_bo) == Missing("head")
    nothing = lambda data: replaced(data, str(uuid7()), lambda part: part)  # noqa: E731
    assert await prepare_rewrite(Letter, letter.id, nothing) == Missing("part")
    with pytest.raises(ValidationError):
        await prepare_rewrite(
            Letter,
            letter.id,
            lambda data: replaced(
                data, about(letter), lambda part: {**part, "about": ref(paris)}
            ),
        )
    assert counts(db_driver) == before
    assert (await Letter.get(letter.id)).meta.version == 1


@no_type_check
async def test_rewrite_saves_on_the_version_read_or_given_with_the_options_of_save(
    db_driver,
    clear_database,
    instructed,  # noqa: F811
):
    Letter, letter, bo, _ = await a_letter()

    def to_bo(data):
        return replaced(data, about(letter), lambda part: {**part, "about": ref(bo)})

    with pytest.raises(PanglossVersionConflictError):
        await rewrite(Letter, letter.id, to_bo, version=7)
    assert (await Letter.get(letter.id)).meta.version == 1

    done = await rewrite(Letter, letter.id, to_bo, instructions={NAME: True})
    assert isinstance(done, Prepared) and done.version == 1
    read = await Letter.get(letter.id)
    assert read.meta.version == 2 and read.statements[0].about.id == bo.id
    assert str(letter.id) in marked(db_driver)

    # (a version given that is the latest: written; the version read is not used)
    done = await rewrite(Letter, letter.id, to_bo, version=2)
    assert (await Letter.get(letter.id)).meta.version == 3
    # (nothing to change: nothing written)
    assert await rewrite(Letter, uuid7(), to_bo) == Missing("head")
