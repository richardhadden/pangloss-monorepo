"""Structured search of entities by what refers to them"""

from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossSearchError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.search import Match

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Negative[T](SemanticSpace[T]):
        pass

    class Person(Entity):
        pass

    class Poet(Person):
        pass

    class Place(Entity):
        pass

    class Organisation(Entity):
        members: list[Person]
        seat: Place

    class Statement(Document):
        about: list[Person | Negative[Person]]

    class Factoid(Document):
        statements: list[Statement]

    class Letter(Document):
        sender: Person
        written_at: Place
        mentioned: list[Person]

    initialise()
    return Person, Poet, Place, Organisation, Statement, Factoid, Letter


def where(**conditions):
    return Match(where=conditions)  # type: ignore[arg-type]


def labels(found):
    return sorted(item.label for item in found.results)


@no_type_check
async def make(clear_database):
    Person, Poet, Place, Organisation, Statement, Factoid, Letter = models()
    john = await Person.Create(label="John").save()
    jane = await Poet.Create(label="Jane").save()
    kate = await Person.Create(label="Kate").save()
    venice = await Place.Create(label="Venice").save()
    rome = await Place.Create(label="Rome").save()

    async def letter(label, sender, at, mentioned=()):
        return await Letter.Create(
            label=label,
            sender=Person.ReferenceSet(id=sender.id),
            written_at=Place.ReferenceSet(id=at.id),
            mentioned=[Person.ReferenceSet(id=p.id) for p in mentioned],
        ).save()

    return (
        Person,
        Poet,
        Place,
        Organisation,
        Statement,
        Factoid,
        Letter,
        john,
        jane,
        kate,
        venice,
        rome,
        letter,
    )


@no_type_check
async def test_an_entity_by_the_documents_that_refer_to_it(clear_database):
    (
        Person,
        Poet,
        Place,
        Org,
        Statement,
        Factoid,
        Letter,
        john,
        jane,
        kate,
        venice,
        rome,
        letter,
    ) = await make(clear_database)
    await letter("from John in Venice", john, venice)
    await letter("from Jane in Rome", jane, rome, mentioned=[kate])

    async def people(*items, **more):
        return labels(await Person.search(where(**{"$incoming": list(items), **more})))

    assert await people({"type": "Letter"}) == ["Jane", "John", "Kate"]
    assert await people({"type": "Letter", "field": "sender"}) == ["Jane", "John"]
    assert await people({"type": "Letter", "field": "mentioned"}) == ["Kate"]
    # the referring node is described by a pattern of its own, as any is
    assert await people(
        {"type": "Letter", "where": {"label": {"contains": "venice"}}}
    ) == ["John"]
    assert await people(
        {
            "type": "Letter",
            "where": {"written_at": {"where": {"label": {"eq": "Rome"}}}},
        }
    ) == ["Jane", "Kate"]
    # each one has to hold, and of different documents
    assert (
        await people(
            {"type": "Letter", "field": "sender"},
            {"type": "Letter", "field": "mentioned"},
        )
        == []
    )
    # nothing that refers to them
    nobody = await Person.search(where(**{"$not": {"$incoming": [{"type": "Letter"}]}}))
    assert labels(nobody) == []
    await Person.Create(label="Lonely").save()
    nobody = await Person.search(where(**{"$not": {"$incoming": [{"type": "Letter"}]}}))
    assert labels(nobody) == ["Lonely"]


@no_type_check
async def test_a_document_that_has_been_deleted_refers_to_nothing(clear_database):
    (
        Person,
        Poet,
        Place,
        Org,
        Statement,
        Factoid,
        Letter,
        john,
        jane,
        kate,
        venice,
        rome,
        letter,
    ) = await make(clear_database)
    gone = await letter("gone", john, venice)
    await letter("kept", jane, venice)
    await Letter.delete(gone.id)

    found = await Person.search(where(**{"$incoming": [{"type": "Letter"}]}))

    assert labels(found) == ["Jane"]


@no_type_check
async def test_through_semantic_spaces_and_from_documents_inside_documents(
    clear_database,
):
    (
        Person,
        Poet,
        Place,
        Org,
        Statement,
        Factoid,
        Letter,
        john,
        jane,
        kate,
        venice,
        rome,
        letter,
    ) = await make(clear_database)
    await Factoid.Create(
        label="F",
        statements=[
            {
                "type": "Statement",
                "label": "plain",
                "about": [{"type": "Person", "id": john.id}],
            },
            {
                "type": "Statement",
                "label": "negated",
                "about": [
                    {
                        "type": "Negative",
                        "contents": [{"type": "Person", "id": jane.id}],
                    }
                ],
            },
        ],
    ).save()

    async def people(**item):
        return labels(await Person.search(where(**{"$incoming": [item]})))

    # (the statements are inside a factoid, not head documents: they refer all the same)
    assert await people(type="Statement") == ["Jane", "John"]
    assert await people(type="Statement", field="about") == ["Jane", "John"]
    assert await people(type="Statement", through=["Negative"]) == ["Jane"]
    assert await people(type="Statement", where={"label": {"eq": "plain"}}) == ["John"]
    assert await people(type="Statement", where={"label": {"eq": "negated"}}) == [
        "Jane"
    ]
    # a subclass of what is pointed at is found by its parent's relation
    poets = await Poet.search(where(**{"$incoming": [{"type": "Statement"}]}))
    assert labels(poets) == ["Jane"]


@no_type_check
async def test_an_entity_by_the_entities_that_refer_to_it_and_in_a_nested_pattern(
    clear_database,
):
    (
        Person,
        Poet,
        Place,
        Org,
        Statement,
        Factoid,
        Letter,
        john,
        jane,
        kate,
        venice,
        rome,
        letter,
    ) = await make(clear_database)
    await Org.Create(
        label="Guild",
        members=[Person.ReferenceSet(id=john.id), Person.ReferenceSet(id=kate.id)],
        seat=Place.ReferenceSet(id=venice.id),
    ).save()
    await letter("L", john, rome)

    people = await Person.search(
        where(
            **{
                "$incoming": [
                    {"type": "Organisation", "where": {"label": {"eq": "Guild"}}}
                ]
            }
        )
    )
    assert labels(people) == ["John", "Kate"]
    places = await Place.search(
        where(**{"$incoming": [{"type": "Organisation", "field": "seat"}]})
    )
    assert labels(places) == ["Venice"]

    # in a pattern for what a relation points at: letters whose sender is in an organisation,
    # and, from the other side, the people who sent a letter to Rome
    letters = await Letter.search(
        where(sender={"where": {"$incoming": [{"type": "Organisation"}]}})
    )
    assert labels(letters) == ["L"]
    rome_senders = await Person.search(
        where(
            **{
                "$incoming": [
                    {
                        "type": "Letter",
                        "field": "sender",
                        "where": {"written_at": {"where": {"label": {"eq": "Rome"}}}},
                    }
                ]
            }
        )
    )
    assert labels(rome_senders) == ["John"]


@no_type_check
async def test_what_cannot_be_asked_is_refused(clear_database):
    (
        Person,
        Poet,
        Place,
        Org,
        Statement,
        Factoid,
        Letter,
        john,
        jane,
        kate,
        venice,
        rome,
        letter,
    ) = await make(clear_database)
    bad = (
        (
            Letter,
            {"$incoming": [{"type": "Statement"}]},
        ),  # only an entity is referred to
        (Person, {"$incoming": [{"type": "Nothing"}]}),
        (Person, {"$incoming": [{"type": "Statement", "field": "nothing"}]}),
        (
            Person,
            {"$incoming": [{"type": "Letter", "field": "written_at"}]},
        ),  # (that is a Place)
        (
            Place,
            {"$incoming": [{"type": "Statement"}]},
        ),  # (a statement is about persons)
        (
            Person,
            {"$incoming": [{"type": "Letter", "through": ["Negative"]}]},
        ),  # (no wrappers in Letter)
        (Person, {"$incoming": [{"type": "Letter", "where": {"nothing": {"eq": 1}}}]}),
        (Person, {"$incoming": []}),
        (Person, {"$incoming": [{"field": "sender"}]}),
    )
    for model, condition in bad:
        with pytest.raises((PanglossSearchError, ValueError)):
            await model.search(where(**condition))
