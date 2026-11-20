"""Structured search by what is on the way of a relation: the fields of an edge model (`edge`), and what is asked of a
wrapper the relation passes through and of the edge that leaves it (`Through`)"""

import datetime
from typing import no_type_check

import pytest
from pangloss_models import (
    Compare,
    Conjunction,
    Document,
    EdgeModel,
    Entity,
    Match,
    PanglossSearchError,
    ReifiedRelation,
    Rel,
    SemanticSpace,
    Text,
    Through,
    ViaEdge,
    initialise,
)

from pydantic import ValidationError

from .test_merge_api import api  # noqa: F401
from .test_sdk_contract import through_the_api  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Certainty(EdgeModel):
        value: int
        note: str | None = None
        on: datetime.date | None = None

    class Share(EdgeModel):
        percent: int

    class Unused(EdgeModel):
        weight: int

    class Negative[T](SemanticSpace[T]):
        pass

    class Alternative[T](Conjunction):
        options: list[ViaEdge[T, Share]]

    class Identification[T](ReifiedRelation[T]):
        by: str | None = None
        score: int = 0

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Event(Document):
        # (directly with a certainty; through an identification; through alternatives, each perhaps an identification)
        who: list[
            ViaEdge[Person, Certainty]
            | Identification[Person]
            | Alternative[Person | Identification[Person]]
            | Negative[Person]
        ]
        where_: list[Place]

    initialise()
    return (
        Person,
        Place,
        Event,
        Certainty,
        Share,
        Unused,
        Negative,
        Alternative,
        Identification,
    )


def ref(entity):
    return {
        "type": type(entity).__name__.removesuffix("ReferenceView"),
        "id": entity.id,
    }


def person(p):
    return {"type": "Person", "id": p.id}


def direct(p, value, note=None, on=None):
    properties = {"value": value}
    if note is not None:
        properties["note"] = note
    if on is not None:
        properties["on"] = on
    return {**person(p), "edge_properties": properties}


def identified(p, by=None, score=0):
    return {"type": "Identification", "by": by, "score": score, "target": [person(p)]}


def alternatives(*options):
    """`(what, percent)` each: a person, or an identification of one"""
    return {
        "type": "Alternative",
        "options": [
            {**what, "edge_properties": {"percent": percent}}
            for what, percent in options
        ],
    }


def labels(found):
    return sorted(item.label for item in found.results)


@no_type_check
async def make(clear_database):
    (
        Person,
        Place,
        Event,
        Certainty,
        Share,
        Unused,
        Negative,
        Alternative,
        Identification,
    ) = models()
    john = await Person.Create(label="John").save()
    jane = await Person.Create(label="Jane").save()
    kate = await Person.Create(label="Kate").save()

    async def event(label, *who):
        return await Event.Create(label=label, who=list(who), where_=[]).save()

    await event("sure of john", direct(john, 9, note="seen", on="1500-01-02"))
    await event("unsure of john", direct(john, 2, note="heard"))
    await event("sure of jane", direct(jane, 8))
    await event("john identified by a", identified(john, by="a", score=5))
    await event("john identified by b", identified(john, by="b", score=1))
    await event(
        "john likely or jane",
        alternatives((person(john), 80), (person(jane), 20)),
    )
    await event(
        "jane likely or john",
        alternatives((person(john), 30), (person(jane), 70)),
    )
    await event(
        "kate identified, likely",
        alternatives((identified(kate, by="a", score=7), 90), (person(jane), 10)),
    )
    await event("not john", {"type": "Negative", "contents": [person(john)]})
    await event("nobody")
    return locals()


@no_type_check
async def test_the_edge_that_reaches_what_a_relation_is_to_is_tested_by_its_edge_model(
    clear_database,
):
    m = await make(clear_database)
    Event, Certainty, john, jane = m["Event"], m["Certainty"], m["john"], m["jane"]

    async def found(rel):
        return labels(await Event.search(Event.Where(who=rel)))

    sure = Certainty.Where(value=Compare[int](gte=8))
    assert await found(Rel(is_=john, edge=sure)) == ["sure of john"]
    assert await found(Rel(is_=jane, edge=sure)) == ["sure of jane"]
    assert await found(Rel(edge=sure)) == ["sure of jane", "sure of john"]
    assert await found(Rel(exists=True, edge=sure)) == ["sure of jane", "sure of john"]
    # (text, and a date, of the edge)
    assert await found(Rel(edge=Certainty.Where(note=Text(contains="HEAR")))) == [
        "unsure of john"
    ]
    assert await found(
        Rel(
            edge=Certainty.Where(
                on=Compare[datetime.date](lt=datetime.date(1600, 1, 1))
            )
        )
    ) == ["sure of john"]
    # (a value it does not have: `exists`. An edge says which edge model it is of, so this is of the `Certainty`
    # edges alone: not an edge of another edge model, or of none, which has no such value either)
    assert await found(
        Rel(is_=jane, edge=Certainty.Where(note=Text(exists=False)))
    ) == ["sure of jane"]
    assert await found(Rel(edge=Certainty.Where(note=Text(exists=False)))) == [
        "sure of jane"
    ]
    assert await found(Rel(is_=john, edge=Certainty.Where(note=Text(exists=True)))) == [
        "sure of john",
        "unsure of john",
    ]
    # (with a pattern for what it is to)
    assert await found(
        Rel(match=m["Person"].Where(label=Text(eq="John")), edge=sure)
    ) == ["sure of john"]
    # (combinators of the edge's own fields)
    either = Certainty.Where(value=Compare[int](lte=2)) | Certainty.Where(
        note=Text(eq="seen")
    )
    assert await found(Rel(is_=john, edge=either)) == ["sure of john", "unsure of john"]
    # (as with any "not": an edge with no such value is not one that has it)
    unsure = await found(Rel(is_=john, edge=~sure))
    assert "unsure of john" in unsure and "sure of john" not in unsure


@no_type_check
async def test_the_json_of_an_edge_condition_is_taken_as_the_classes_are(
    clear_database,
):
    m = await make(clear_database)
    Event, john = m["Event"], m["john"]
    found = await Event.search(
        Match(
            where={
                "who": {
                    "is": str(john.id),
                    "edge": {"type": "Certainty", "where": {"value": {"lt": 5}}},
                }
            }
        )
    )
    assert labels(found) == ["unsure of john"]
    found = await Event.search(
        Match(
            where={
                "who": {
                    "through": [
                        {
                            "type": "Alternative",
                            "edge": {
                                "type": "Share",
                                "where": {"percent": {"gte": 75}},
                            },
                        }
                    ]
                }
            }
        )
    )
    assert labels(found) == ["john likely or jane", "kate identified, likely"]


@no_type_check
async def test_no_relation_with_such_an_edge(clear_database):
    m = await make(clear_database)
    Event, Certainty = m["Event"], m["Certainty"]
    found = await Event.search(
        Event.Where(
            who=Rel(exists=False, edge=Certainty.Where(value=Compare[int](gte=8)))
        )
    )
    assert "sure of john" not in labels(found)
    assert "sure of jane" not in labels(found)
    assert "unsure of john" in labels(found)
    assert "nobody" in labels(found)
    assert len(labels(found)) == 8


@no_type_check
async def test_the_edge_out_of_the_last_wrapper_is_the_edge_that_reaches_it(
    clear_database,
):
    """`edge` is of the last edge of the relation, whichever node it leaves: out of an alternative, the share"""
    m = await make(clear_database)
    Event, Share, john, jane = m["Event"], m["Share"], m["john"], m["jane"]

    async def found(rel):
        return labels(await Event.search(Event.Where(who=rel)))

    likely = Share.Where(percent=Compare[int](gte=60))
    assert await found(Rel(is_=john, edge=likely)) == ["john likely or jane"]
    assert await found(Rel(is_=jane, edge=likely)) == ["jane likely or john"]
    # (kate is in an identification inside the alternative: the edge that reaches her is the identification's)
    assert await found(Rel(is_=m["kate"], edge=likely)) == []
    # (whether there is one with such an edge: through the alternative too, not only the edges out of the event)
    assert await found(Rel(exists=True, edge=likely)) == [
        "jane likely or john",
        "john likely or jane",
    ]
    assert "john likely or jane" not in await found(Rel(exists=False, edge=likely))


@no_type_check
async def test_through_a_wrapper_by_the_edge_that_leaves_it(clear_database):
    m = await make(clear_database)
    Event, Share, Alternative = m["Event"], m["Share"], m["Alternative"]
    john, jane, kate = m["john"], m["jane"], m["kate"]

    async def found(rel):
        return labels(await Event.search(Event.Where(who=rel)))

    def likely(at_least):
        return Through(
            Alternative, edge=Share.Where(percent=Compare[int](gte=at_least))
        )

    assert await found(Rel(is_=john, through=[likely(60)])) == ["john likely or jane"]
    assert await found(Rel(is_=john, through=[likely(25)])) == [
        "jane likely or john",
        "john likely or jane",
    ]
    assert await found(Rel(is_=jane, through=[likely(60)])) == ["jane likely or john"]
    # (the edge is the one on the way to what the relation is to: kate at 90, through an identification as well)
    assert await found(Rel(is_=kate, through=[likely(60)])) == [
        "kate identified, likely"
    ]
    assert await found(Rel(is_=jane, through=[likely(5)])) == [
        "jane likely or john",
        "john likely or jane",
        "kate identified, likely",
    ]
    assert await found(Rel(is_=jane, through=[likely(15)])) == [
        "jane likely or john",
        "john likely or jane",
    ]
    # (without `is_`: any relation through such an edge)
    assert await found(Rel(through=[likely(85)])) == ["kate identified, likely"]
    # (a wrapper asked for with nothing more, as a `Through` or as the class)
    assert (
        await found(Rel(is_=john, through=[Through(Alternative)]))
        == await found(Rel(is_=john, through=[Alternative]))
        == ["jane likely or john", "john likely or jane"]
    )


@no_type_check
async def test_through_a_wrapper_by_its_own_values(clear_database):
    m = await make(clear_database)
    Event, Identification, Alternative, Share = (
        m["Event"],
        m["Identification"],
        m["Alternative"],
        m["Share"],
    )
    john, kate = m["john"], m["kate"]

    async def found(rel):
        return labels(await Event.search(Event.Where(who=rel)))

    by_a = Through(Identification, where=Identification.Where(by=Text(eq="a")))
    assert await found(Rel(is_=john, through=[by_a])) == ["john identified by a"]
    assert await found(Rel(through=[by_a])) == [
        "john identified by a",
        "kate identified, likely",
    ]
    good = Through(
        Identification, where=Identification.Where(score=Compare[int](gte=5))
    )
    assert await found(Rel(is_=john, through=[good])) == ["john identified by a"]
    # (two wrappers on the one way, each with what is asked of it)
    likely = Through(Alternative, edge=Share.Where(percent=Compare[int](gte=60)))
    assert await found(Rel(through=[likely, good])) == ["kate identified, likely"]
    assert await found(Rel(is_=kate, through=[likely, by_a])) == [
        "kate identified, likely"
    ]
    unlikely = Through(Alternative, edge=Share.Where(percent=Compare[int](lt=60)))
    assert await found(Rel(is_=kate, through=[unlikely, by_a])) == []
    # (what is beside an identification in an alternative is not reached through it: the way does not go back up)
    assert await found(Rel(is_=m["jane"], through=[Identification])) == []
    assert await found(Rel(is_=m["jane"], through=[by_a])) == []
    # (with the name of a wrapper beside one of which more is asked)
    assert await found(Rel(through=[Alternative, by_a])) == ["kate identified, likely"]


@no_type_check
async def test_any_relation_and_mentions_take_them_too(clear_database):
    m = await make(clear_database)
    Event, john = m["Event"], m["john"]
    likely = {
        "type": "Alternative",
        "edge": {"type": "Share", "where": {"percent": {"gte": 60}}},
    }
    found = await Event.search(
        Match(where={"$any": {"is": str(john.id), "through": [likely]}})
    )
    assert labels(found) == ["john likely or jane"]
    found = await Event.search(
        Match(where={"$mentions": {"is": str(john.id), "through": [likely]}})
    )
    assert labels(found) == ["john likely or jane"]
    found = await Event.search(
        Match(
            where={
                "$mentions": {
                    "is": str(john.id),
                    "edge": {"type": "Certainty", "where": {"value": {"gte": 8}}},
                }
            }
        )
    )
    assert labels(found) == ["sure of john"]


@no_type_check
async def test_in_a_not_and_an_any_of(clear_database):
    m = await make(clear_database)
    Event, Certainty, john = m["Event"], m["Certainty"], m["john"]
    sure = Event.Where(
        who=Rel(is_=john, edge=Certainty.Where(value=Compare[int](gte=8)))
    )
    named = Event.Where(label=Text(eq="nobody"))
    assert labels(await Event.search(sure | named)) == ["nobody", "sure of john"]
    found = labels(await Event.search(~sure))
    assert "sure of john" not in found and len(found) == 9


@no_type_check
async def test_what_is_refused(clear_database):
    m = await make(clear_database)
    Event = m["Event"]

    async def refused(condition, saying, field="who"):
        with pytest.raises(PanglossSearchError, match=saying):
            await Event.search(Match(where={field: condition}))

    edge = {"type": "Certainty", "where": {"value": {"gte": 1}}}
    # (not an edge model; not one the relation has; a field it has not; an operator that does not fit)
    await refused({"edge": {"type": "Person"}}, "'Person' is not an edge model")
    await refused({"edge": {"type": "Nope"}}, "'Nope' is not an edge model")
    await refused(
        {"edge": {"type": "Unused", "where": {"weight": {"eq": 1}}}},
        "never a Unused.*Certainty, Share",
    )
    await refused(
        {"edge": {"type": "Certainty", "where": {"nope": {"eq": 1}}}},
        "who.edge.nope: Certainty has no field 'nope'",
    )
    await refused(
        {"edge": {"type": "Certainty", "where": {"value": {"contains": "x"}}}},
        "who.edge.value.contains: not an operator",
    )
    await refused(
        {"edge": {"type": "Certainty", "where": {"value": {"gte": "many"}}}},
        "not a valid int",
    )
    await refused(
        {"edge": {"type": "Certainty", "where": {"label": {"eq": "x"}}}},
        "Certainty has no field 'label'",
    )
    await refused(
        {"edge": {"type": "Certainty", "where": {"$spaces": ["Negative"]}}},
        r"who.edge.\$spaces: not for an edge",
    )
    # (a relation with no edge model, and a field that is no relation)
    await refused(edge and {"edge": edge}, "never a Certainty.*no edge model", "where_")
    await refused({"edge": edge}, "are for relations only", "label")
    # (a wrapper: not one; a field it has not; what it points at; an edge model its relations have not)
    await refused(
        {"through": [{"type": "Person"}]},
        "'Person' is not a semantic space, conjunction or reified relation",
    )
    await refused(
        {"through": [{"type": "Identification", "where": {"nope": {"eq": 1}}}]},
        "who.through.Identification.nope: Identification has no field 'nope'",
    )
    await refused(
        {
            "through": [
                {"type": "Identification", "where": {"target": {"exists": True}}}
            ]
        },
        "who.through.Identification.target",
    )
    await refused(
        {"through": [{"type": "Identification", "edge": edge}]},
        "an edge of a Identification is never a Certainty",
    )
    await refused(
        {"through": [{"type": "Alternative", "edge": edge}]},
        "an edge of a Alternative is never a Certainty.*Share",
    )
    # (a key a step does not have is not read at all)
    with pytest.raises(ValidationError):
        Match(where={"who": {"through": [{"type": "Alternative", "nope": 1}]}})
    # (a variable is of a rule)
    await refused(
        {"edge": {"type": "Certainty", "where": {"value": {"$var": "p"}}}},
        "a variable .* is only in a rule",
    )


@no_type_check
async def test_the_classes_refuse_what_types_can_tell(clear_database):
    m = await make(clear_database)
    Person, Certainty, Identification, Alternative = (
        m["Person"],
        m["Certainty"],
        m["Identification"],
        m["Alternative"],
    )
    # (a pattern of the wrong kind, or of another wrapper: a `ValidationError` is a `ValueError`)
    with pytest.raises(ValidationError, match="EdgeWhere"):
        Through(Alternative, edge=Person.Where())
    with pytest.raises(ValidationError, match="WrapperWhere"):
        Through("Alternative", where=Person.Where())
    with pytest.raises(ValueError, match="the pattern is of a Identification"):
        Through(Alternative, where=Identification.Where())
    with pytest.raises(ValidationError, match="EdgeWhere"):
        Rel(edge=Person.Where())
    with pytest.raises(TypeError, match="given twice"):
        Through(Alternative, type="Alternative")
    # (an edge model and a wrapper have a `Where` of their own values, and nothing to order by)
    assert set(Certainty.Where.model_fields) >= {"value", "note", "on"}
    assert "target" not in Identification.Where.model_fields
    assert not hasattr(Certainty, "Order")
    assert Through(Alternative).to_json() == {"type": "Alternative"}
    assert Through("Alternative", edge=m["Share"].Where()).to_json() == {
        "type": "Alternative",
        "edge": {"type": "Share", "where": {}},
    }


@no_type_check
async def test_over_the_api_and_what_it_answers_when_refused(db_driver, api):  # noqa: F811
    m = await make(None)
    client, users = await api()
    john = m["john"]

    async def search(where):
        return await client.post(
            "/api/search",
            json={"type": "Event", "where": where},
            headers=users["ann"],
        )

    found = await search(
        {
            "who": {
                "is": str(john.id),
                "through": [
                    {
                        "type": "Alternative",
                        "edge": {"type": "Share", "where": {"percent": {"gte": 60}}},
                    }
                ],
            }
        }
    )
    assert found.status_code == 200, found.text
    assert [item["label"] for item in found.json()["results"]] == [
        "john likely or jane"
    ]
    found = await search(
        {
            "who": {
                "is": str(john.id),
                "edge": {"type": "Certainty", "where": {"value": {"gte": 8}}},
            }
        }
    )
    assert [item["label"] for item in found.json()["results"]] == ["sure of john"]
    # (what the models do not have is a 422 that says where)
    refused = await search(
        {"who": {"edge": {"type": "Share", "where": {"nope": {"eq": 1}}}}}
    )
    assert refused.status_code == 422
    assert "who.edge.nope" in refused.text
    refused = await search({"who": {"through": [{"type": "Alternative", "nope": 1}]}})
    assert refused.status_code == 422


@no_type_check
async def test_the_sdk_sends_the_classes_as_the_database_module_takes_them(
    through_the_api,  # noqa: F811
):
    from pangloss_api import create_app
    from pangloss_sdk.databases.api import exposed_functions as sdk

    m = await make(None)
    await through_the_api(create_app())
    Event, Share, Alternative, Certainty = (
        m["Event"],
        m["Share"],
        m["Alternative"],
        m["Certainty"],
    )
    for pattern in (
        Event.Where(
            who=Rel(
                is_=m["jane"],
                through=[
                    Through(Alternative, edge=Share.Where(percent=Compare[int](gte=60)))
                ],
            )
        ),
        Event.Where(
            who=Rel(
                edge=Certainty.Where(
                    value=Compare[int](gte=8),
                    on=Compare[datetime.date](lt=datetime.date(1600, 1, 1)),
                )
            )
        ),
    ):
        directly = labels(await Event.search(pattern))
        assert directly and labels(await sdk.search(Event, pattern)) == directly
