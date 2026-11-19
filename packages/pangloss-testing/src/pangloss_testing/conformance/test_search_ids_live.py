"""`operations.search_ids`: a structured search that gives ids (how many fit, and the first by label), for what works
with a result; who may see a computed edge (`fragments.edge_visible`); and a `@create_validator` that refuses."""

from typing import Annotated, no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_models import (
    Computed,
    ComputedTarget,
    Document,
    Entity,
    Match,
    PanglossSearchError,
    PanglossWriteRefused,
    ReifiedRelation,
    create_validator,
    initialise,
    update_validator,
)
from pangloss_users import see_unpublished

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Person(Entity):
        pass

    class Guess[T](ReifiedRelation[T]):
        target: Annotated[list[T], Computed()] = []

    class Letter(Document):
        sender: Person
        maybe: list[Guess[Person]]
        near: Annotated[list[Person], Computed()] = []

    initialise()
    return Person, Guess, Letter


def ref(item):
    return {"type": "Person", "id": item.id}


def ops():
    return storage_of().operations


@no_type_check
async def people_and_letters():
    Person, Guess, Letter = models()
    people = {
        name: await Person.Create(label=name).save()
        for name in ("Dora", "anna", "Carl", "Bert")
    }
    letters = {}
    for name in ("Dora", "anna", "Carl"):
        letters[name] = await Letter.Create(
            label=f"From {name}", sender=ref(people[name]), maybe=[{"type": "Guess"}]
        ).save(detail=True)
    return Person, Letter, people, letters


SENDERS = Match(where={"$incoming": [{"type": "Letter", "field": "sender"}]})


@no_type_check
async def test_it_gives_the_count_and_the_first_by_label(clear_database):
    Person, Letter, people, letters = await people_and_letters()

    found = await ops().search_ids(Person, SENDERS, limit=2)

    assert found.count == 3
    assert [item["label"] for item in found.items] == ["anna", "Carl"]
    assert found.items[0] == {
        "id": str(people["anna"].id),
        "type": "Person",
        "label": "anna",
    }
    assert found.ids == [str(people["anna"].id), str(people["Carl"].id)]
    everyone = await ops().search_ids(Person)
    assert everyone.count == 4 and len(everyone.items) == 4
    none = await ops().search_ids(Person, Match(where={"label": {"eq": "Nobody"}}))
    assert none.count == 0 and none.items == []
    # (a limit of none: the count alone)
    counted = await ops().search_ids(Person, SENDERS, limit=0)
    assert counted.count == 3 and counted.items == []


@no_type_check
async def test_ids_can_be_left_out_or_be_all_that_is_looked_at(clear_database):
    Person, Letter, people, letters = await people_and_letters()

    without = await ops().search_ids(
        Person, SENDERS, without=[people["anna"].id, str(people["Bert"].id)]
    )
    assert without.count == 2
    assert [item["label"] for item in without.items] == ["Carl", "Dora"]

    among = await ops().search_ids(
        Person, SENDERS, among=[people["Dora"].id, people["Bert"].id, people["Dora"].id]
    )
    assert among.count == 1 and [i["label"] for i in among.items] == ["Dora"]
    # (an id of another class, or of nothing, is not found)
    other = await ops().search_ids(
        Person, among=[letters["Dora"].id, "00000000-0000-7000-8000-000000000000"]
    )
    assert other.count == 0
    assert (await ops().search_ids(Person, SENDERS, among=[])).count == 0
    both = await ops().search_ids(
        Person,
        SENDERS,
        among=[people["Dora"].id, people["Carl"].id],
        without=[people["Carl"].id],
    )
    assert [i["label"] for i in both.items] == ["Dora"]


@no_type_check
async def test_it_is_made_as_the_reader_named_whoever_asks(clear_database):
    Person, Letter, people, letters = await people_and_letters()
    await ops().set_published_in_db(Letter, letters["Dora"].id, False)

    assert (await ops().search_ids(Person, SENDERS, see_unpublished=True)).count == 3
    assert (await ops().search_ids(Person, SENDERS, see_unpublished=False)).count == 2
    # (not said: as whoever asks)
    assert (await ops().search_ids(Person, SENDERS)).count == 3
    token = see_unpublished.set(False)
    try:
        assert (await ops().search_ids(Person, SENDERS)).count == 2
        assert (
            await ops().search_ids(Person, SENDERS, see_unpublished=True)
        ).count == 3
    finally:
        see_unpublished.reset(token)


@no_type_check
async def test_it_takes_what_a_search_takes_and_refuses_what_one_refuses(
    clear_database,
):
    Person, Letter, people, letters = await people_and_letters()
    guess = letters["Dora"].maybe[0]
    await ops().set_computed(guess.id, {"target": [people["Bert"].id]})

    maybe = Match(where={"maybe": {"is": str(people["Bert"].id)}})
    assert (await ops().search_ids(Letter, maybe)).count == 1
    left_out = Match(
        where={"maybe": {"is": str(people["Bert"].id)}}, exclude_wrappers=["Guess"]
    )
    assert (await ops().search_ids(Letter, left_out)).count == 0
    assert (
        await ops().search_ids(Letter, Letter.Where(label={"contains": "carl"}))
    ).ids == [str(letters["Carl"].id)]
    with pytest.raises(PanglossSearchError, match="Letter has no field 'nothing'"):
        await ops().search_ids(Letter, Match(where={"nothing": {"eq": 1}}))


# --- who may see a computed edge --------------------------------------------------------------------------------------


@no_type_check
async def test_a_computed_edge_only_those_logged_in_see_is_in_no_read_of_anyone_else(
    clear_database,
):
    Person, Letter, people, letters = await people_and_letters()
    letter = letters["Dora"]
    guess = letter.maybe[0]
    await ops().set_computed(
        guess.id,
        {
            "target": [
                ComputedTarget(people["Bert"].id, seen_by="logged_in"),
                ComputedTarget(people["Carl"].id, seen_by="everyone"),
            ]
        },
    )
    await ops().set_computed(
        letter.id, {"near": [ComputedTarget(people["anna"].id, seen_by="logged_in")]}
    )
    bert, carl, anna = people["Bert"], people["Carl"], people["anna"]

    def incoming(view) -> list[str]:
        return sorted(
            item["label"]
            for value in view.model_dump().values()
            if isinstance(value, list)
            for item in value
            if isinstance(item, dict) and item.get("type") == "Letter"
        )

    async def letters_where(**where) -> int:
        return (await Letter.search(Match(where=where))).count

    async def seen():
        read = await Letter.get(letter.id)
        return (
            [p.label for p in read.maybe[0].target],
            [p.label for p in read.near],
            incoming(await Person.get(bert.id)),
            incoming(await Person.get(carl.id)),
            incoming(await Person.get(anna.id)),
            await letters_where(maybe={"is": str(bert.id)}),
            await letters_where(maybe={"is": str(carl.id)}),
            await letters_where(near={"is": str(anna.id)}),
            await letters_where(**{"$mentions": {"is": str(bert.id)}}),
            await letters_where(**{"$any": {"is": str(anna.id)}}),
            (
                await Person.search(
                    Match(where={"$incoming": [{"type": "Letter", "field": "maybe"}]})
                )
            ).count,
            (
                await Person.search(
                    Match(where={"$incoming": [{"type": "Letter", "field": "near"}]})
                )
            ).count,
        )

    assert await seen() == (
        ["Bert", "Carl"],
        ["anna"],
        ["From Dora"],
        ["From Carl", "From Dora"],
        ["From Dora", "From anna"],
        1,
        1,
        1,
        1,
        # (any relation to anna: the letter she sent, and the one she is computed to be near)
        2,
        2,
        1,
    )
    token = see_unpublished.set(False)
    try:
        assert await seen() == (
            ["Carl"],
            [],
            [],
            ["From Carl", "From Dora"],
            ["From anna"],
            0,
            1,
            0,
            0,
            1,
            1,
            0,
        )
    finally:
        see_unpublished.reset(token)


# --- a validator of what is written that refuses ------------------------------------------------------------------------


@no_type_check
async def test_a_validator_of_the_written_model_that_raises_refuses_the_write_and_says_where(
    clear_database,
):
    class Person(Entity):
        pass

    class Clause(Document):
        _meta = Document.Meta(create_directly=False)
        text: str

        @create_validator
        @update_validator
        def not_empty(self):
            if not self.text.strip():
                raise ValueError("text: a clause says something")

    class Deed(Document):
        clauses: list[Clause]

    initialise()

    with pytest.raises(
        PanglossWriteRefused, match="^text: a clause says something$"
    ) as refused:
        await Deed.Create(
            label="D",
            clauses=[
                {"type": "Clause", "label": "a", "text": "x"},
                {"type": "Clause", "label": "b", "text": " "},
            ],
        ).save()
    assert refused.value.path == ("clauses", 1)
    assert (await Deed.list()).count == 0

    deed = await Deed.Create(
        label="D", clauses=[{"type": "Clause", "label": "a", "text": "x"}]
    ).save(detail=True)
    with pytest.raises(PanglossWriteRefused) as refused:
        await Deed.Update(
            id=deed.id,
            label="D",
            clauses=[
                {"type": "Clause", "id": deed.clauses[0].id, "label": "a", "text": ""}
            ],
        ).save()
    assert refused.value.path == ("clauses", 0)
    assert (await Deed.get(deed.id)).clauses[0].text == "x"
