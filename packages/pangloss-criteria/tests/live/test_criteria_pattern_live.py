"""A `SearchPattern` in the database: stored as text and read back as the pattern, searched with, and its merged ids
resolved (implementation_docs/matches-criteria.md, "The model", "What is searched")"""

import json
from typing import no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_criteria import SearchPattern, check_stored, resolve_merged
from pangloss_criteria.pattern import ids_named
from pangloss_models import Document, Entity, ReifiedRelation, initialise
from pangloss_testing.live import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Person(Entity):
        pass

    class Office(Entity):
        pass

    class Guess[T](ReifiedRelation[T]):
        wording: str | None = None

    class HoldsOffice(Document):
        holder: list[Person | Guess[Person]]
        office: Office
        employer: Person

    class Described(Document):
        criteria: SearchPattern | None = None
        others: list[SearchPattern] = []

    initialise()
    return Person, Office, HoldsOffice, Described


def ref(item):
    return {"type": type(item)._owner.__name__, "id": item.id}


def secretary_of(office, employer) -> dict:
    return {
        "type": "Person",
        "where": {
            "$incoming": [
                {
                    "type": "HoldsOffice",
                    "field": "holder",
                    "where": {
                        "office": {"is": str(office.id)},
                        "employer": {"is": str(employer.id)},
                    },
                }
            ]
        },
    }


@no_type_check
async def a_court(Person, Office, HoldsOffice):
    """Maximilian, who has two secretaries: one named, one someone only guessed to be it"""
    maximilian = await Person.Create(label="Maximilian").save()
    secretary = await Office.Create(label="Secretary").save()
    waldauf = await Person.Create(label="Waldauf").save()
    guessed = await Person.Create(label="Guessed").save()
    await HoldsOffice.Create(
        label="Waldauf is secretary",
        holder=[ref(waldauf)],
        office=ref(secretary),
        employer=ref(maximilian),
    ).save()
    await HoldsOffice.Create(
        label="Someone is secretary",
        holder=[{"type": "Guess", "wording": "N. N.", "target": [ref(guessed)]}],
        office=ref(secretary),
        employer=ref(maximilian),
    ).save()
    return maximilian, secretary, waldauf, guessed


@no_type_check
async def test_a_pattern_is_stored_as_text_and_read_back_as_the_pattern(
    clear_database, db_driver
):
    Person, Office, HoldsOffice, Described = models()
    maximilian, secretary, waldauf, guessed = await a_court(Person, Office, HoldsOffice)
    pattern = secretary_of(secretary, maximilian)

    saved = await Described.Create(
        label="D", criteria=pattern, others=[pattern, {"type": "Office"}]
    ).save(detail=True)

    assert saved.criteria == SearchPattern(pattern)
    assert saved.others == [SearchPattern(pattern), SearchPattern({"type": "Office"})]
    rows = run(
        db_driver,
        "MATCH (d:Described {id: $id}) RETURN d.criteria AS criteria, d.others AS others",
        id=str(saved.id),
    )
    assert isinstance(rows[0]["criteria"], str)
    assert json.loads(rows[0]["criteria"]) == pattern
    assert [json.loads(text) for text in rows[0]["others"]] == [
        pattern,
        {"type": "Office", "where": {}},
    ]
    # (changed by an update, and taken away by one)
    await Described.Update(
        id=saved.id, label="D", criteria={"type": "Office"}, others=[]
    ).save()
    read = await Described.get(saved.id)
    assert read.criteria.type == "Office" and read.others == []
    await Described.Update(id=saved.id, label="D", criteria=None).save()
    assert (await Described.get(saved.id)).criteria is None


@no_type_check
async def test_what_is_read_can_be_sent_back_as_it_is(clear_database):
    Person, Office, HoldsOffice, Described = models()
    maximilian, secretary, waldauf, guessed = await a_court(Person, Office, HoldsOffice)
    saved = await Described.Create(
        label="D", criteria=secretary_of(secretary, maximilian)
    ).save(detail=True)

    payload = saved.model_dump(mode="json", by_alias=True)
    payload.pop("meta")
    await Described.Update(**payload).save()

    again = await Described.get(saved.id)
    assert again.meta.version == 2 and again.criteria == saved.criteria


@no_type_check
async def test_a_stored_pattern_is_searched_with_and_can_leave_wrappers_out(
    clear_database,
):
    Person, Office, HoldsOffice, Described = models()
    maximilian, secretary, waldauf, guessed = await a_court(Person, Office, HoldsOffice)
    saved = await Described.Create(
        label="D", criteria=secretary_of(secretary, maximilian)
    ).save(detail=True)
    pattern = (await Described.get(saved.id)).criteria
    check_stored(pattern, [Person], exclude_wrappers=["Guess"])

    everyone = await Person.search(pattern.match())
    named = await Person.search(pattern.match(exclude_wrappers=["Guess"]))

    assert sorted(p.label for p in everyone.results) == ["Guessed", "Waldauf"]
    assert [p.label for p in named.results] == ["Waldauf"]


@no_type_check
async def test_the_ids_of_merged_entities_are_resolved_and_the_stored_pattern_is_not_rewritten(
    clear_database, db_driver
):
    Person, Office, HoldsOffice, Described = models()
    maximilian, secretary, waldauf, guessed = await a_court(Person, Office, HoldsOffice)
    # (a second Maximilian, whom the pattern names, and who is then found to be the first)
    duplicate = await Person.Create(label="Maximilian I").save()
    saved = await Described.Create(
        label="D", criteria=secretary_of(secretary, duplicate)
    ).save(detail=True)
    stored = saved.criteria
    assert (await Person.search(stored.match())).count == 0
    await Person.merge(duplicate.id, into=maximilian.id)

    # (as it is stored, it names an entity that nothing refers to any more)
    assert (await Person.search(stored.match())).count == 0
    resolved = await resolve_merged(stored)

    # (as read from the database, where the keys of the text are in order)
    assert sorted(ids_named(resolved)) == sorted(
        [str(secretary.id), str(maximilian.id)]
    )
    found = await Person.search(resolved.match(exclude_wrappers=["Guess"]))
    assert [p.label for p in found.results] == ["Waldauf"]
    # (nothing was written: the document says what it said)
    assert sorted(ids_named(stored)) == sorted([str(secretary.id), str(duplicate.id)])
    read = await Described.get(saved.id)
    assert read.criteria == stored and read.meta.version == 1
    # (a pattern that names nobody merged is itself; undone, the id is its own again)
    assert await resolve_merged(resolved) == resolved
    assert await resolve_merged(SearchPattern({"type": "Person"})) == SearchPattern(
        {"type": "Person"}
    )


@no_type_check
async def test_a_chain_of_merges_is_followed_to_its_end(clear_database):
    Person, Office, HoldsOffice, Described = models()
    first = await Person.Create(label="First").save()
    second = await Person.Create(label="Second").save()
    third = await Person.Create(label="Third").save()
    other = await Person.Create(label="Other").save()
    await Person.merge(first.id, into=second.id)
    await Person.merge(second.id, into=third.id)

    survivors = await storage_of().operations.survivors_of(
        [first.id, str(second.id), third.id, other.id, first.id]
    )

    assert survivors == {str(first.id): str(third.id), str(second.id): str(third.id)}
    assert await storage_of().operations.survivors_of([]) == {}
    pattern = SearchPattern(
        {
            "type": "Person",
            "where": {
                "$incoming": [
                    {
                        "type": "HoldsOffice",
                        "where": {
                            "employer": {
                                "is_any": [str(first.id), str(second.id), str(other.id)]
                            }
                        },
                    }
                ]
            },
        }
    )
    resolved = await resolve_merged(pattern)
    assert resolved.where["$incoming"][0]["where"]["employer"] == {
        "is_any": [str(third.id), str(other.id)]
    }
