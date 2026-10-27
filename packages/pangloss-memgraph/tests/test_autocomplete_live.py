"""Finding entities by label over several types"""

from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.entity import Entity

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Agent(Entity):
        pass

    class Person(Agent):
        pass

    class Organisation(Agent):
        pass

    class Place(Entity):
        pass

    class Letter(Entity):
        pass

    initialise()
    return Agent, Person, Organisation, Place, Letter


def labels(found):
    return [item.label for item in found.results]


@no_type_check
async def test_finds_by_every_word_in_any_of_the_types_and_their_subclasses(
    clear_database,
):
    Agent, Person, Organisation, Place, Letter = models()
    await Person.Create(label="John Smith").save()
    await Organisation.Create(label="Smith & Sons").save()
    await Place.Create(label="Smithfield").save()
    await Letter.Create(label="Letter from Smith").save()
    await Person.Create(label="Jane Jones").save()

    both = await Entity.autocomplete("smith", types=[Agent, Place])
    assert sorted(labels(both)) == ["John Smith", "Smith & Sons", "Smithfield"]
    assert both.count == 3

    words = await Entity.autocomplete("smith john", types=[Agent])
    assert labels(words) == ["John Smith"]

    only = await Person.autocomplete("smith")
    assert labels(only) == ["John Smith"]


@no_type_check
async def test_the_item_has_the_class_the_entity_was_made_as(clear_database):
    Agent, Person, *_ = models()
    made = await Person.Create(label="John Smith").save()

    found = await Agent.autocomplete("john")

    assert [(i.id, i.type, i.label) for i in found.results] == [
        (made.id, "Person", "John Smith")
    ]


@no_type_check
async def test_matches_the_start_of_a_word_or_the_middle_and_ignores_case(
    clear_database,
):
    *_, Place, _ = models()
    await Place.Create(label="Smithfield").save()

    assert labels(await Place.autocomplete("SMI")) == ["Smithfield"]
    assert labels(await Place.autocomplete("field")) == ["Smithfield"]
    assert labels(await Place.autocomplete("fieldx")) == []


@no_type_check
async def test_a_label_that_begins_with_what_was_typed_comes_first(clear_database):
    *_, Place, _ = models()
    await Place.Create(label="Old Cambridge").save()
    await Place.Create(label="Cambridge").save()
    await Place.Create(label="Cambridgeshire").save()

    found = await Place.autocomplete("cambridge")

    assert labels(found)[:2] == ["Cambridge", "Cambridgeshire"]
    assert labels(found)[2] == "Old Cambridge"


@no_type_check
async def test_a_deleted_entity_is_not_found(clear_database):
    *_, Place, _ = models()
    gone = await Place.Create(label="Atlantis").save()
    await Place.Create(label="Atlanta").save()
    await Place.delete(gone.id)

    assert labels(await Place.autocomplete("atlant")) == ["Atlanta"]


@no_type_check
async def test_pages_with_a_total(clear_database):
    *_, Place, _ = models()
    for number in range(25):
        await Place.Create(label=f"Town {number:02}").save()

    first = await Place.autocomplete("town", page_size=10)
    last = await Place.autocomplete("town", page_number=3, page_size=10)
    beyond = await Place.autocomplete("town", page_number=9, page_size=10)

    assert (first.count, len(first.results), first.next_page, first.previous_page) == (
        25,
        10,
        2,
        None,
    )
    assert (last.count, len(last.results), last.next_page, last.previous_page) == (
        25,
        5,
        None,
        2,
    )
    assert (beyond.count, beyond.results) == (25, [])


@no_type_check
async def test_nothing_typed_but_punctuation_finds_nothing_and_breaks_nothing(
    clear_database,
):
    *_, Place, _ = models()
    await Place.Create(label="Smithfield").save()

    for text in ("(", ".*", "[a-", "\\", "   ", "a)b("):
        found = await Place.autocomplete(text)
        assert found.results == [], text


@no_type_check
async def test_text_with_punctuation_in_it_still_finds(clear_database):
    *_, Place, _ = models()
    await Place.Create(label="O'Brien, Dublin").save()

    assert labels(await Place.autocomplete("o'brien (dublin")) == ["O'Brien, Dublin"]


@no_type_check
async def test_any_entity(clear_database):
    Agent, Person, Organisation, Place, Letter = models()
    await Person.Create(label="Smith").save()
    await Letter.Create(label="Smith letter").save()

    assert len((await Entity.autocomplete("smith")).results) == 2


@no_type_check
async def test_a_trait_finds_the_entities_that_have_it_and_nothing_else(clear_database):
    from pangloss_models.model_bases.trait import Trait

    class Marked(Trait):
        pass

    class Thing(Entity, Marked):
        pass

    class Plain(Entity):
        pass

    initialise()
    await Thing.Create(label="A marked thing").save()
    await Plain.Create(label="A plain thing").save()

    found = await Entity.autocomplete("thing", types=[Marked])

    assert labels(found) == ["A marked thing"]


@no_type_check
async def test_an_entity_with_an_id_of_its_own_is_found(clear_database):
    class Site(Entity):
        _meta = Entity.Meta(create_with_id=True)

    initialise()
    from uuid import uuid7

    id_ = uuid7()
    await Site.Create(id=id_, create_new=True, label="Hill fort").save()

    assert [i.id for i in (await Site.autocomplete("fort")).results] == [id_]


@no_type_check
async def test_documents_are_not_found(clear_database):
    from pangloss_models.model_bases.document import Document

    class Paper(Document):
        pass

    class Person(Entity):
        pass

    initialise()
    await Paper.Create(label="Smith paper").save()
    await Person.Create(label="Smith").save()

    assert labels(await Entity.autocomplete("smith")) == ["Smith"]
