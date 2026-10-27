"""Structured search of documents and entities in Memgraph (step 1: fields with values, entities by id)"""

import datetime
import enum
from decimal import Decimal
from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.exceptions import PanglossSearchError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.search import Match

pytestmark = pytest.mark.asyncio(loop_scope="session")


class Status(enum.Enum):
    DRAFT = "draft"
    DONE = "done"


made = []  # (the Attachment class of the last `models()`)


def models():
    class Person(Entity):
        born: int | None = None

    class Poet(Person):
        pass

    class Attachment(Document):
        name: str
        size: int

    class Letter(Document):
        title: str
        attachments: list[Attachment]
        pages: int | None = None
        sent: datetime.date | None = None
        price: Decimal | None = None
        status: Status | None = None
        urgent: bool | None = None
        tags: list[str]
        sender: Person
        copies_to: list[Person]

    initialise()
    made.append(Attachment)
    return Person, Poet, Letter


def where(**conditions):
    return Match(where=conditions)  # type: ignore[arg-type]


def titles(found):
    return sorted(item.label for item in found.results)


@no_type_check
async def make(clear_database):
    Person, Poet, Letter = models()
    john = await Person.Create(label="John").save()
    jane = await Poet.Create(label="Jane").save()

    async def letter(label, sender, **more):
        return await Letter.Create(
            label=label,
            title=more.pop("title", label),
            sender=Person.ReferenceSet(id=sender.id),
            copies_to=[Person.ReferenceSet(id=p.id) for p in more.pop("copies", [])],
            tags=more.pop("tags", []),
            attachments=more.pop("attachments", []),
            **more,
        ).save()

    return Person, Poet, Letter, john, jane, letter


@no_type_check
async def test_text_number_date_and_choice_fields(clear_database):
    Person, Poet, Letter, john, jane, letter = await make(clear_database)
    await letter(
        "Plague in Venice",
        john,
        pages=3,
        sent=datetime.date(1576, 5, 1),
        price=Decimal("1.10"),
        status=Status.DRAFT,
        urgent=True,
    )
    await letter(
        "Wedding",
        jane,
        pages=10,
        sent=datetime.date(1620, 1, 1),
        price=Decimal("12.50"),
        status=Status.DONE,
        urgent=False,
    )
    await letter("Bare", jane)

    async def find(**conditions):
        return titles(await Letter.search(where(**conditions)))

    assert await find() == ["Bare", "Plague in Venice", "Wedding"]
    assert await find(title={"contains": "VENICE"}) == ["Plague in Venice"]
    assert await find(label={"starts_with": "wed"}) == ["Wedding"]
    assert await find(title={"eq": "Wedding"}) == ["Wedding"]
    assert await find(title={"in": ["Wedding", "Bare"]}) == ["Bare", "Wedding"]
    assert await find(pages={"gt": 5}) == ["Wedding"]
    assert await find(pages={"gte": 3, "lt": 10}) == ["Plague in Venice"]
    assert await find(pages={"between": [1, 10]}) == ["Plague in Venice", "Wedding"]
    assert await find(sent={"lt": "1600-01-01"}) == ["Plague in Venice"]
    assert await find(sent={"exists": False}) == ["Bare"]
    assert await find(status={"eq": "done"}) == ["Wedding"]
    assert await find(status={"ne": "done"}) == ["Bare", "Plague in Venice"]
    assert await find(urgent={"eq": True}) == ["Plague in Venice"]
    # a Decimal is compared as a number: 1.1 is the 1.10 that was stored
    assert await find(price={"eq": "1.1"}) == ["Plague in Venice"]
    assert await find(price={"gt": 2}) == ["Wedding"]


@no_type_check
async def test_lists_and_entity_relations(clear_database):
    Person, Poet, Letter, john, jane, letter = await make(clear_database)
    await letter("A", john, tags=["x", "y"], copies=[jane])
    await letter("B", jane, tags=["y"], copies=[john, jane])
    await letter("C", jane)

    async def find(**conditions):
        return titles(await Letter.search(where(**conditions)))

    assert await find(tags={"contains": "y"}) == ["A", "B"]
    assert await find(tags={"contains_all": ["x", "y"]}) == ["A"]
    assert await find(tags={"contains_any": ["x", "z"]}) == ["A"]
    assert await find(sender={"is": str(john.id)}) == ["A"]
    assert await find(sender={"is": str(jane.id)}) == ["B", "C"]
    assert await find(sender={"is_any": [str(john.id), str(jane.id)]}) == [
        "A",
        "B",
        "C",
    ]
    # a letter with both of the people as a copy is found once
    assert await find(copies_to={"is_any": [str(john.id), str(jane.id)]}) == ["A", "B"]
    assert await find(sender={"is": str(jane.id)}, copies_to={"is": str(john.id)}) == [
        "B"
    ]


@no_type_check
async def test_entities_by_their_fields_and_subclasses(clear_database):
    Person, Poet, Letter, john, jane, letter = await make(clear_database)
    await Person.Create(label="Old", born=1500).save()

    found = await Person.search(where(born={"lt": 1600}))
    assert titles(found) == ["Old"]
    assert titles(await Person.search(where(label={"contains": "j"}))) == [
        "Jane",
        "John",
    ]
    # (a Poet is a Person: it is found, and is read as a Poet)
    both = await Person.search(where(label={"eq": "Jane"}))
    assert [item.type for item in both.results] == ["Poet"]
    assert titles(await Poet.search(where())) == ["Jane"]


@no_type_check
async def test_paging_total_and_what_is_deleted(clear_database):
    Person, Poet, Letter, john, jane, letter = await make(clear_database)
    for n in range(5):
        await letter(f"L{n}", john)
    gone = await letter("Gone", john)
    await Letter.delete(gone.id)

    first = await Letter.search(where(), page_number=1, page_size=2)
    assert titles(first) == ["L0", "L1"]
    assert (first.count, first.next_page, first.previous_page) == (5, 2, None)
    last = await Letter.search(where(), page_number=3, page_size=2)
    assert titles(last) == ["L4"] and last.next_page is None
    past = await Letter.search(where(), page_number=9, page_size=2)
    assert past.results == [] and past.count == 5


@no_type_check
async def test_a_pattern_that_cannot_be_made_is_refused(clear_database):
    Person, Poet, Letter, *_ = await make(clear_database)
    for bad in (
        {"nothing": {"eq": 1}},
        {"pages": {"contains": "x"}},
        {"pages": {"eq": "many"}},
        {"title": {"gt": "a"}},
        {"title": {}},
    ):
        with pytest.raises(PanglossSearchError):
            await Letter.search(where(**bad))
    with pytest.raises(PanglossSearchError):
        await Letter.search(Match(type="Person"))


@no_type_check
async def test_a_relation_to_a_pattern_in_entities_and_in_nested_documents(
    clear_database,
):
    Person, Poet, Letter, john, jane, letter = await make(clear_database)
    Attachment = made[-1]
    old = await Person.Create(label="Old Smith", born=1500).save()
    await letter(
        "A", old, attachments=[Attachment.Create(label="map", name="map", size=5)]
    )
    await letter(
        "B", jane, attachments=[Attachment.Create(label="pic", name="pic", size=50)]
    )
    await letter("C", john)

    async def find(**conditions):
        return titles(await Letter.search(where(**conditions)))

    assert await find(sender={"where": {"born": {"lt": 1600}}}) == ["A"]
    assert await find(sender={"where": {"label": {"contains": "smith"}}}) == ["A"]
    # (a Poet is a Person; asked for as the type, it is only the poets)
    assert await find(sender={"type": "Poet"}) == ["B"]
    assert await find(sender={"type": "Person"}) == ["A", "B", "C"]
    assert await find(attachments={"where": {"size": {"gt": 10}}}) == ["B"]
    assert await find(attachments={"exists": True}) == ["A", "B"]
    assert await find(attachments={"exists": False}) == ["C"]
    # two conditions on one relation have to hold of the same thing it points at
    assert (
        await find(attachments={"where": {"size": {"gt": 10}, "name": {"eq": "map"}}})
        == []
    )
    assert await find(
        sender={"where": {"label": {"contains": "old"}}},
        attachments={"where": {"name": {"eq": "map"}}},
    ) == ["A"]


@no_type_check
async def test_all_any_of_and_not(clear_database):
    Person, Poet, Letter, john, jane, letter = await make(clear_database)
    await letter("A", john, pages=1, copies=[jane])
    await letter("B", jane, pages=5, copies=[john, jane])
    await letter("C", jane, pages=9)
    await letter("D", john)

    async def find(**conditions):
        return titles(await Letter.search(where(**conditions)))

    assert await find(
        **{
            "$any_of": [
                {"pages": {"lt": 2}},
                {"sender": {"is": str(jane.id)}, "pages": {"gt": 8}},
            ]
        }
    ) == ["A", "C"]
    assert await find(**{"$not": {"sender": {"is": str(john.id)}}}) == ["B", "C"]
    # what has no value is not "pages > 4": so it is "not" that
    assert await find(**{"$not": {"pages": {"gt": 4}}}) == ["A", "D"]
    assert await find(
        **{
            "$all": [
                {"copies_to": {"is": str(john.id)}},
                {"copies_to": {"is": str(jane.id)}},
            ]
        }
    ) == ["B"]
    assert await find(
        **{"$not": {"$any_of": [{"title": {"eq": "A"}}, {"title": {"eq": "B"}}]}}
    ) == ["C", "D"]
    assert await find(
        **{"$not": {"copies_to": {"exists": True}}, "pages": {"exists": True}}
    ) == ["C"]
