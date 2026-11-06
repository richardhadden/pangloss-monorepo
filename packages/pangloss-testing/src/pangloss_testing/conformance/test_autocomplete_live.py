"""Finding entities by label over several types"""

from typing import no_type_check

import pytest
from pangloss_models import Entity, initialise

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

    # (blank, it is as if nothing was typed: see below)
    for text in ("(", ".*", "[a-", "\\", "a)b("):
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
    from pangloss_models import Trait

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
    from pangloss_models import Document

    class Paper(Document):
        pass

    class Person(Entity):
        pass

    initialise()
    await Paper.Create(label="Smith paper").save()
    await Person.Create(label="Smith").save()

    assert labels(await Entity.autocomplete("smith")) == ["Smith"]


@no_type_check
async def test_with_nothing_typed_the_entities_most_referred_to_come_first(
    clear_database,
):
    from typing import Annotated

    from pangloss_models import Document, RelationConfig

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Letter(Document):
        mentions: Annotated[list[Person], RelationConfig(reverse_name="mentioned_in")]

    initialise()
    alice = await Person.Create(label="Alice").save()
    bob = await Person.Create(label="Bob").save()
    await Person.Create(label="Carol").save()
    await Place.Create(label="Atlanta").save()
    deleted = await Person.Create(label="Dave").save()
    for mentioned in ([bob], [bob, alice], [bob]):
        await Letter.Create(
            label="A letter",
            mentions=[{"type": "Person", "id": p.id} for p in mentioned],
        ).save()
    await Person.delete(deleted.id)

    found = await Person.autocomplete("")
    assert labels(found) == ["Bob", "Alice", "Carol"]
    assert found.count == 3

    assert labels(await Person.autocomplete("  ", page_size=1)) == ["Bob"]
    second = await Person.autocomplete(page_number=2, page_size=2)
    assert labels(second) == ["Carol"]
    assert second.previous_page == 1
    assert labels(await Entity.autocomplete(types=[Place])) == ["Atlanta"]


@no_type_check
async def test_an_entity_is_found_by_a_word_that_is_in_many_labels_of_other_things(
    clear_database, db_driver
):
    """The index of labels is of documents and what is in them too, and a text index gives a first few hits (Memgraph:
    1000) unless it is asked for more: a person was not found by a surname that 1000 statements had in their labels"""
    from pangloss_testing.conformance.helpers import run

    _, Person, *_ = models()
    run(
        db_driver,
        """
        UNWIND range(1, 1100) AS i
        CREATE (:PGIndexableNode {
            id: 'note-' + toString(i), type: 'Note',
            label: 'A note on Smith ' + toString(i), label_folded: 'a note on smith ' + toString(i)
        })
        """,
    )
    await Person.Create(label="Anna Smith").save()
    await Person.Create(label="Smith of the Notes").save()

    found = await Person.autocomplete("smith")
    assert sorted(labels(found)) == ["Anna Smith", "Smith of the Notes"]
    assert labels(await Person.autocomplete("smith note")) == ["Smith of the Notes"]


@no_type_check
async def test_a_very_long_word_finds_nothing_and_is_not_an_error(clear_database):
    """(Memgraph's index refused the pattern of a word of some 490 characters: an internal error, for a pasted line of
    text with no spaces)"""
    _, Person, *_ = models()
    long_but_a_word = "pneumonoultramicroscopicsilicovolcanoco"  # (39 letters)
    await Person.Create(label=f"John {long_but_a_word}").save()

    for text in ("a" * 500, "john " + "b" * 2000):
        assert (await Person.autocomplete(text)).count == 0
        assert (await Person.list(search_terms=text)).count == 0
        assert (await Person.list(search_terms=text, deep_search=True)).count == 0
    # (a long word that is a word is found)
    assert labels(await Person.autocomplete(long_but_a_word)) == [
        f"John {long_but_a_word}"
    ]
    assert (await Person.list(search_terms=long_but_a_word)).count == 1
