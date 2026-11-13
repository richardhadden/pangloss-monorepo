""" "Search everything": head documents and entities of any class by their label, the most connected first"""

from typing import no_type_check

import pytest
from pangloss_models import Document, Entity, initialise
from pangloss_models.autocomplete import search_everything

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Agent(Entity):
        pass

    class Person(Agent):
        pass

    class Place(Entity):
        pass

    class Hidden(Entity):
        _meta = Entity.Meta(global_search=False)

    class NotHidden(Hidden):
        pass

    class Part(Document):
        _meta = Document.Meta(create_directly=False)

    class Statement(Document):
        about: list[Person]
        part: list[Part] = []

    initialise()
    return Agent, Person, Place, Hidden, NotHidden, Part, Statement


def labels(found):
    return [item.label for item in found.results]


@no_type_check
async def test_every_class_by_every_word_most_connected_first(clear_database):
    Agent, Person, Place, Hidden, NotHidden, Part, Statement = models()
    few = await Person.Create(label="Smith the Less").save()
    many = await Person.Create(label="Smith the Great").save()
    await Place.Create(label="Smith Town").save()
    await Person.Create(label="Jones").save()

    def ref(person):
        return {"type": "Person", "id": person.id}

    await Statement.Create(label="Letter", about=[ref(few), ref(many)], part=[]).save()
    await Statement.Create(label="Another", about=[ref(many)], part=[]).save()
    await Statement.Create(label="Smith Statement", about=[], part=[]).save()

    found = await search_everything("smith")
    assert found.count == 4
    assert labels(found)[:2] == ["Smith the Great", "Smith the Less"]
    assert {item.type for item in found.results} == {"Person", "Place", "Statement"}
    assert labels(await search_everything("smith great")) == ["Smith the Great"]


@no_type_check
async def test_narrowed_to_a_class_and_its_subclasses(clear_database):
    Agent, Person, Place, *_ = models()
    await Person.Create(label="Smith").save()
    await Place.Create(label="Smithfield").save()
    assert labels(await search_everything("smith", [Agent])) == ["Smith"]


@no_type_check
async def test_a_class_opted_out_is_not_found_but_its_subclass_is(clear_database):
    Agent, Person, Place, Hidden, NotHidden, *_ = models()
    await Hidden.Create(label="Secret One").save()
    await NotHidden.Create(label="Secret Two").save()
    assert labels(await search_everything("secret")) == ["Secret Two"]


@no_type_check
async def test_what_is_inside_a_document_and_what_is_deleted_are_not_found(
    clear_database,
):
    Agent, Person, Place, Hidden, NotHidden, Part, Statement = models()
    await Statement.Create(
        label="Outer", about=[], part=[Part.Create(label="Findable Inner")]
    ).save()
    gone = await Person.Create(label="Findable Gone").save()
    await Person.delete(gone.id)
    assert labels(await search_everything("findable")) == []


@no_type_check
async def test_nothing_typed_finds_nothing(clear_database):
    Agent, Person, *_ = models()
    await Person.Create(label="Someone").save()
    found = await search_everything("  ")
    assert found.count == 0 and found.results == []


@no_type_check
async def test_a_page_is_as_many_as_asked_with_the_count_of_all(clear_database):
    Agent, Person, *_ = models()
    for number in range(20):
        await Person.Create(label=f"Common {number}").save()
    found = await search_everything("common", page_size=15)
    assert len(found.results) == 15 and found.count == 20


@no_type_check
async def test_a_type_and_no_words_lists_the_most_connected_of_it(clear_database):
    Agent, Person, Place, Hidden, NotHidden, Part, Statement = models()
    few = await Person.Create(label="Aaron").save()
    many = await Person.Create(label="Zed").save()
    await Place.Create(label="Elsewhere").save()
    gone = await Person.Create(label="Gone").save()
    await Person.delete(gone.id)
    await Statement.Create(
        label="One",
        about=[{"type": "Person", "id": many.id}],
        part=[],
    ).save()
    await Statement.Create(
        label="Two",
        about=[{"type": "Person", "id": many.id}, {"type": "Person", "id": few.id}],
        part=[],
    ).save()

    found = await search_everything("", [Agent])
    assert labels(found) == ["Zed", "Aaron"]
    assert found.count == 2
    assert labels(await search_everything("", [Person, Place])) == [
        "Zed",
        "Aaron",
        "Elsewhere",
    ]


@no_type_check
async def test_naming_a_class_finds_what_is_inside_documents(clear_database):
    Agent, Person, Place, Hidden, NotHidden, Part, Statement = models()
    kept = await Statement.Create(
        label="Outer",
        about=[],
        part=[Part.Create(label="Findable Inner")],
    ).save()
    gone = await Statement.Create(
        label="Gone Outer",
        about=[],
        part=[Part.Create(label="Findable Deleted")],
    ).save()
    await Statement.delete(gone.id)

    assert labels(await search_everything("findable", [Part])) == ["Findable Inner"]
    assert labels(await search_everything("", [Part])) == ["Findable Inner"]
    assert labels(await search_everything("findable")) == []
    assert kept.id


@no_type_check
async def test_documents_only_leaves_out_every_entity(clear_database):
    Agent, Person, Place, Hidden, NotHidden, Part, Statement = models()
    await Person.Create(label="Smith").save()
    await Place.Create(label="Smithfield").save()
    await Statement.Create(label="Smith's letter", about=[], part=[]).save()

    assert labels(await search_everything("smith", documents_only=True)) == [
        "Smith's letter"
    ]
    # (a class of entity named as well: still none)
    assert labels(await search_everything("", [Person], documents_only=True)) == []
    assert len((await search_everything("smith")).results) == 3
