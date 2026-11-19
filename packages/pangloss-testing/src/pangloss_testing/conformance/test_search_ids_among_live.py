"""`operations.search_ids_among`: several searches as `search_ids`, each among ids of its own, in one call (for
`pangloss-criteria`, which keeps the results of many stored patterns up to date). Whatever it groups and however, each
result is what `search_ids` gives of the same search. Searches of one shape are one query where the backend's
compiler can make them so (`build_search_ids_rows_query`), and one query each where it cannot."""

from typing import no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_cypher import read_functions
from pangloss_cypher.search_query import ROWS_HOLDER, build_search_ids_rows_query
from pangloss_models import (
    Document,
    Entity,
    Match,
    ReifiedRelation,
    initialise,
)
from pangloss_models.search import check_match

from pangloss_testing.backends import under_test

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Person(Entity):
        title: str | None = None

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class Letter(Document):
        sender: Person
        witness: list[InRole[Person]] = []
        year: int | None = None

    initialise()
    return Person, InRole, Letter


def ref(item):
    return {"type": "Person", "id": item.id}


def ops():
    return storage_of().operations


NAMES = ("Dora", "anna", "Carl", "Bert", "Emil", "Fritz")


@no_type_check
async def letters_of_people():
    """Six people (Bert and Carl doctors); each but Fritz sent a letter, witnessed by the next of them; Bert's is not
    published"""
    Person, InRole, Letter = models()
    people = {
        name: await Person.Create(label=name, title="Dr" if name < "D" else None).save()
        for name in NAMES
    }
    letters = {}
    for index, name in enumerate(NAMES[:-1]):
        witness = NAMES[index + 1]
        letters[name] = await Letter.Create(
            label=f"From {name}",
            sender=ref(people[name]),
            witness=[
                {"type": "InRole", "role": "witness", "target": [ref(people[witness])]}
            ],
            year=1500 + index,
        ).save()
    await ops().set_published_in_db(Letter, letters["Bert"].id, False)
    return Person, Letter, people, letters


def sent_by(person) -> Match:
    """The letters someone sent"""
    return Match(where={"sender": {"is": str(person.id)}})


def senders(year=None) -> Match:
    where = {} if year is None else {"year": {"gte": year}}
    return Match(
        where={"$incoming": [{"type": "Letter", "field": "sender", "where": where}]}
    )


def witnesses_of(person, **more) -> Match:
    return Match(
        where={
            "$incoming": [
                {
                    "type": "Letter",
                    "field": "witness",
                    "where": {"sender": {"is": str(person.id)}},
                }
            ]
        },
        **more,
    )


def ids(people, *names) -> list[str]:
    return [str(people[name].id) for name in names]


async def each_alone(searches, limit, see_unpublished):
    return {
        key: await ops().search_ids(
            cls,
            pattern,
            among=among,
            without=without,
            limit=limit,
            see_unpublished=see_unpublished,
        )
        for key, cls, pattern, among, without in searches
    }


@no_type_check
async def test_each_result_is_what_search_ids_gives_of_the_same_search(clear_database):
    Person, Letter, people, letters = await letters_of_people()
    everyone = ids(people, *NAMES)
    searches = [
        # (several of one shape, each with ids and among of its own)
        ("dora", Person, witnesses_of(people["Dora"]), everyone, []),
        ("anna", Person, witnesses_of(people["anna"]), ids(people, "Carl", "Bert"), []),
        (
            "none among",
            Person,
            witnesses_of(people["anna"]),
            ids(people, "Dora", "Bert"),
            [],
        ),
        ("carl", Person, witnesses_of(people["Carl"]), ids(people, "Dora", "Bert"), []),
        # (other shapes, and another class)
        ("senders", Person, senders(), everyone, []),
        ("lately", Person, senders(1502), everyone, []),
        ("doctors", Person, Match(where={"title": {"eq": "Dr"}}), everyone, []),
        ("all", Person, None, everyone, []),
        (
            "letters",
            Letter,
            sent_by(people["Carl"]),
            [str(letter.id) for letter in letters.values()],
            [],
        ),
        (
            "letters by id",
            Letter,
            None,
            [str(letters["anna"].id), str(people["anna"].id)],
            [],
        ),
    ]
    for see_unpublished in (True, False):
        for limit in (100, 2):
            found = await ops().search_ids_among(
                searches, limit=limit, see_unpublished=see_unpublished
            )
            assert found == await each_alone(searches, limit, see_unpublished)

    found = await ops().search_ids_among(searches, limit=100, see_unpublished=True)
    assert [i["label"] for i in found["dora"].items] == ["anna"]
    assert [i["label"] for i in found["anna"].items] == ["Carl"]
    assert found["none among"].count == 0
    assert [i["label"] for i in found["carl"].items] == ["Bert"]
    assert found["senders"].count == 5
    assert found["doctors"].count == 2
    assert found["all"].count == 6
    assert [i["label"] for i in found["letters"].items] == ["From Carl"]
    assert [i["label"] for i in found["letters by id"].items] == ["From anna"]


@no_type_check
async def test_without_limit_and_who_is_reading(clear_database):
    Person, Letter, people, letters = await letters_of_people()
    everyone = ids(people, *NAMES)
    searches = [
        ("without", Person, senders(), everyone, ids(people, "anna", "Emil")),
        ("bert unpublished", Person, witnesses_of(people["Bert"]), everyone, []),
        ("emil", Person, witnesses_of(people["Emil"]), everyone, ids(people, "Fritz")),
    ]

    logged_in = await ops().search_ids_among(searches, limit=2, see_unpublished=True)
    others = await ops().search_ids_among(searches, limit=2, see_unpublished=False)

    # (the count is of all; the items the first by label)
    assert logged_in["without"].count == 3
    assert [i["label"] for i in logged_in["without"].items] == ["Bert", "Carl"]
    assert others["without"].count == 2
    assert [i["label"] for i in others["without"].items] == ["Carl", "Dora"]
    assert logged_in["bert unpublished"].ids == ids(people, "Emil")
    assert others["bert unpublished"].count == 0
    assert logged_in["emil"].count == 0
    assert logged_in == await each_alone(searches, 2, True)
    assert others == await each_alone(searches, 2, False)


@no_type_check
async def test_an_empty_among_finds_nothing_and_is_not_even_compiled(clear_database):
    Person, Letter, people, letters = await letters_of_people()

    found = await ops().search_ids_among(
        [
            ("nothing", Person, senders(), [], []),
            # (a pattern that could not be compiled: with nothing to look at, it is not)
            ("not looked at", Person, Match(where={"shoe_size": {"gt": 40}}), [], []),
            ("one", Person, senders(), ids(people, "Dora"), []),
        ],
        see_unpublished=True,
    )

    assert found["nothing"] == read_functions.FoundIds(0, [])
    assert found["not looked at"] == read_functions.FoundIds(0, [])
    assert found["one"].ids == ids(people, "Dora")
    assert await ops().search_ids_among([], see_unpublished=True) == {}


@no_type_check
async def test_a_search_that_leaves_wrappers_out_and_one_through_them(clear_database):
    Person, Letter, people, letters = await letters_of_people()
    everyone = ids(people, *NAMES)
    searches = [
        ("through", Person, witnesses_of(people["Dora"]), everyone, []),
        (
            "left out",
            Person,
            witnesses_of(people["Dora"], exclude_wrappers=["InRole"]),
            everyone,
            [],
        ),
        (
            "named",
            Person,
            Match(
                where={
                    "$incoming": [
                        {"type": "Letter", "field": "witness", "through": ["InRole"]}
                    ]
                }
            ),
            everyone,
            [],
        ),
    ]

    found = await ops().search_ids_among(searches, see_unpublished=True)

    assert found["through"].ids == ids(people, "anna")
    assert found["left out"].count == 0
    assert found["named"].count == 5
    assert found == await each_alone(searches, 100, True)


@no_type_check
async def test_a_key_may_be_anything_that_can_be_a_key(clear_database):
    Person, Letter, people, letters = await letters_of_people()
    everyone = ids(people, *NAMES)
    keys = [("a", 1), 7, "seven", None, frozenset({"x"})]

    found = await ops().search_ids_among(
        [(key, Person, witnesses_of(people["Dora"]), everyone, []) for key in keys],
        see_unpublished=True,
    )

    assert set(found) == set(keys)
    assert all(found[key].ids == ids(people, "anna") for key in keys)


@no_type_check
async def test_more_searches_of_one_shape_than_one_query_takes(
    clear_database, monkeypatch
):
    Person, Letter, people, letters = await letters_of_people()
    monkeypatch.setattr(read_functions, "SEARCH_ROWS_AT_ONCE", 2)
    everyone = ids(people, *NAMES)
    searches = [
        (name, Person, witnesses_of(people[name]), everyone, []) for name in NAMES
    ] + [
        (
            f"{name} sent",
            Letter,
            sent_by(people[name]),
            [str(l.id) for l in letters.values()],
            [],
        )
        for name in NAMES
    ]

    found = await ops().search_ids_among(searches, limit=1, see_unpublished=True)

    assert found == await each_alone(searches, 1, True)
    assert [found[name].count for name in NAMES] == [1, 1, 1, 1, 1, 0]
    assert [found[f"{name} sent"].count for name in NAMES] == [1, 1, 1, 1, 1, 0]


@no_type_check
async def test_searches_of_one_shape_are_one_query_where_the_compiler_allows(
    clear_database,
):
    Person, Letter, people, letters = await letters_of_people()

    def rows(pattern):
        return build_search_ids_rows_query(Person, check_match(Person, pattern))

    of_dora, of_anna = (
        rows(witnesses_of(people["Dora"])),
        rows(witnesses_of(people["anna"])),
    )
    doctors, professors = (
        rows(Match(where={"title": {"eq": "Dr"}})),
        rows(Match(where={"title": {"eq": "Prof"}})),
    )

    # (a pattern of literals is one query on every backend)
    assert doctors is not None and professors is not None
    assert doctors[0] == professors[0]
    assert doctors[1] != professors[1]
    assert f"{ROWS_HOLDER}p0" in doctors[0] and "$p0" not in doctors[0]
    if under_test().name == "memgraph":
        # (the same text, its values read from the row)
        assert of_dora is not None and of_anna is not None
        assert of_dora[0] == of_anna[0]
        assert of_dora[1] != of_anna[1]
        assert ROWS_HOLDER in of_dora[0]
    else:
        # (Neo4j's compiler finds what is related to given ids in a subquery before the `MATCH`, which cannot read
        # the row: each such search is a query of its own)
        assert of_dora is None and of_anna is None
