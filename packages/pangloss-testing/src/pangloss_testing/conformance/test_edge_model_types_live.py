"""An edge says which edge model its values are of (`pg_edge_model`): written with the edge, not shown in what is
read, and what a search by an edge model goes by, so that an edge of another edge model with fields of the same names
is not found. And the migrations that keep it: the one the backends ship for the edges that were there before, a
change of a relation's edge model, a renamed edge model."""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_cypher.migrations import apply_changes, apply_changes_in_batches
from pangloss_models import (
    AnyRel,
    Compare,
    Conjunction,
    Document,
    EdgeModel,
    Entity,
    IncomingFrom,
    Match,
    ReifiedRelation,
    Rel,
    RelationConfig,
    ViaEdge,
)
from pangloss_models.migrations import PossibleRename, RecordEdgeModels
from pangloss_testing.under_test.database import current
from typing import Annotated

from .helpers import run
from .migration_support import declare, migrate

pytestmark = pytest.mark.asyncio(loop_scope="session")

KEY = "pg_edge_model"


def ref(item, **edge):
    made = {"type": item.type, "id": item.id}
    if edge:
        made["edge_properties"] = edge
    return made


def labels(found):
    return sorted(item.label for item in found.results)


def edges(db_driver) -> list[tuple]:
    """Every edge that says which edge model it is of, or has a value of one: where it is, and what it says"""
    rows = run(
        db_driver,
        f"""
        MATCH (a)-[e]->(b)
        WHERE e.{KEY} IS NOT NULL OR e.value IS NOT NULL OR e.percent IS NOT NULL
        RETURN a.type AS source, type(e) AS type, b.type AS target, e.{KEY} AS model,
               coalesce(e.value, e.percent) AS value
        """,
    )
    return sorted(
        (r["source"], r["type"], r["target"], r["model"], r["value"]) for r in rows
    )


def court():
    """Edge models with fields of the same names, on edges to different things, and at every place of a way"""

    class Certainty(EdgeModel):
        value: int
        note: str | None = None

    class Likelihood(EdgeModel):
        value: int
        note: str | None = None

    class Strong(Certainty):
        reason: str | None = None

    class Share(EdgeModel):
        percent: int

    class Bare(EdgeModel):
        """(nothing has to be given for it: an edge of it may have no value at all)"""

        comment: str | None = None

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class RoleType(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        role: ViaEdge[RoleType, Likelihood] | None = None

    class Either[T](Conjunction):
        either: list[ViaEdge[T, Share]]

    class Doc(Document):
        # (each thing its own edge model, the two alike)
        who: list[ViaEdge[Person, Certainty] | ViaEdge[Place, Likelihood]]
        strongly: list[ViaEdge[Person, Strong]]
        barely: list[ViaEdge[Person, Bare]]
        plainly: list[Person]
        # (on the edge into a wrapper, and on the edge out of it: of two edge models that are alike)
        roles: list[ViaEdge[InRole[ViaEdge[Person, Certainty]], Likelihood]]
        # (a wrapper that declares the edge model of its own edges, and one inside another)
        shares: list[Either[Person | InRole[ViaEdge[Person, Certainty]]]]

    class Narrower(Doc):
        # (a field that narrows another is written by the edges of both)
        sure: Annotated[
            list[ViaEdge[Person, Certainty]],
            RelationConfig(subclasses_parent_fields=["who"]),
        ]

    return ns(**locals())


FIELDS = ("who", "strongly", "barely", "plainly", "roles", "shares")


def doc(model, label, **fields):
    """A document with what is given, and nothing in its other relations"""
    names = [name for name in (*FIELDS, "sure") if name in model.model_fields]
    return model(label=label, **{name: fields.get(name, []) for name in names})


@no_type_check
async def populated(m):
    people = {
        name: await m.Person.Create(label=name).save()
        for name in ("John", "Jane", "Ann")
    }
    rome = await m.Place.Create(label="Rome").save()
    baker = await m.RoleType.Create(label="baker").save()
    john, jane, ann = people.values()

    def in_role(person, value, into=None, role=None):
        made = {"type": "InRole", "target": [ref(person, value=value)]}
        if role is not None:
            made["role"] = ref(role, value=1)
        if into is not None:
            made["edge_properties"] = {"value": into}
        return made

    docs = [
        await doc(
            m.Doc.Create, "john 2, rome 9", who=[ref(john, value=2), ref(rome, value=9)]
        ).save(),
        await doc(m.Doc.Create, "john 9", who=[ref(john, value=9, note="seen")]).save(),
        await doc(m.Doc.Create, "rome 3", who=[ref(rome, value=3)]).save(),
        await doc(m.Doc.Create, "strongly 9", strongly=[ref(jane, value=9)]).save(),
        await doc(
            m.Doc.Create, "barely", barely=[{**ref(ann), "edge_properties": {}}]
        ).save(),
        await doc(m.Doc.Create, "plainly", plainly=[ref(ann)]).save(),
        await doc(
            m.Doc.Create,
            "role in 9 out 2",
            roles=[in_role(john, 2, into=9, role=baker)],
        ).save(),
        await doc(
            m.Doc.Create, "role in 2 out 9", roles=[in_role(john, 9, into=2)]
        ).save(),
        await doc(
            m.Doc.Create,
            "shares",
            shares=[
                {
                    "type": "Either",
                    "either": [
                        ref(jane, percent=60),
                        {**in_role(ann, 8), "edge_properties": {"percent": 40}},
                    ],
                }
            ],
        ).save(),
        await doc(m.Narrower.Create, "narrower 7", sure=[ref(jane, value=7)]).save(),
    ]
    return ns(**people, rome=rome, baker=baker, docs=docs)


AS_WRITTEN = [
    # (the field's own edges, each by what it is to)
    ("Doc", "who", "Person", "Certainty", 2),
    ("Doc", "who", "Person", "Certainty", 9),
    ("Doc", "who", "Place", "Likelihood", 3),
    ("Doc", "who", "Place", "Likelihood", 9),
    ("Doc", "strongly", "Person", "Strong", 9),
    ("Doc", "barely", "Person", "Bare", None),
    # (into a wrapper, out of it, and the wrapper's own relation)
    ("Doc", "roles", "InRole", "Likelihood", 2),
    ("Doc", "roles", "InRole", "Likelihood", 9),
    ("InRole", "target", "Person", "Certainty", 2),
    ("InRole", "target", "Person", "Certainty", 8),
    ("InRole", "target", "Person", "Certainty", 9),
    ("InRole", "role", "RoleType", "Likelihood", 1),
    # (what the wrapper declares, whatever the edge is to)
    ("Either", "either", "Person", "Share", 60),
    ("Either", "either", "InRole", "Share", 40),
    # (the edges of a field and of the field it narrows)
    ("Narrower", "sure", "Person", "Certainty", 7),
    ("Narrower", "who", "Person", "Certainty", 7),
]


def both_ways(expected: list[tuple]) -> list[tuple]:
    """Each edge and its reverse (`who_reverse`, from what it is to)"""
    return sorted(
        expected
        + [
            (target, f"{field}_reverse", source, model, value)
            for source, field, target, model, value in expected
        ]
    )


# --- written, and not shown --------------------------------------------------------------------------------------------


@no_type_check
async def test_both_edges_of_a_relation_say_which_edge_model_their_values_are_of(
    db_driver, clear_database
):
    m, _ = declare(court)
    await populated(m)

    assert edges(db_driver) == both_ways(AS_WRITTEN)
    # (an edge with no edge model says nothing)
    assert run(
        db_driver,
        f"MATCH (:Doc)-[e:plainly]->() RETURN e.{KEY} AS model",
    ) == [{"model": None}]


@no_type_check
async def test_what_is_read_does_not_show_it(db_driver, clear_database):
    m, _ = declare(court)
    data = await populated(m)

    def shown(value) -> set[str]:
        return set(value.edge_properties.model_dump())

    by_label = {d.label: d for d in data.docs}
    read = await m.Doc.get(by_label["john 9"].id)
    assert shown(read.who[0]) == {"value", "note"}
    assert type(read.who[0].edge_properties).__name__ == "Certainty"
    read = await m.Doc.get(by_label["john 2, rome 9"].id)
    assert [type(w.edge_properties).__name__ for w in read.who] == [
        "Certainty",
        "Likelihood",
    ]
    read = await m.Doc.get(by_label["role in 9 out 2"].id)
    role = read.roles[0]
    assert (role.edge_properties.value, role.target[0].edge_properties.value) == (9, 2)
    assert shown(role) == shown(role.target[0]) == {"value", "note"}
    # (nor in what the entity it reaches reads back, at either place of the way)
    back = (await m.Person.get(data.John.id)).model_dump()
    assert KEY not in str(back)
    wrapped = [d for d in back["roles_reverse"] if d["label"] == "role in 9 out 2"]
    assert wrapped and "pg_position" not in str(back)
    # (saved again as it was read, it is the same)
    before = edges(db_driver)
    again = await m.Doc.get(by_label["role in 9 out 2"].id)
    payload = again.model_dump(exclude={"meta"})
    await m.Doc.Update(**payload).save()
    assert edges(db_driver) == before


@no_type_check
async def test_a_value_of_an_edge_model_below_the_one_declared_is_an_edge_of_the_one_declared(
    db_driver, clear_database
):
    m, _ = declare(court)
    john = await m.Person.Create(label="John").save()
    # (an instance of `Strong` given where the field declares `Certainty`)
    given = doc(m.Doc.Create, "x", who=[ref(john, value=5)])
    given.who[0].edge_properties = m.Strong(value=5, reason="said so")
    await given.save()

    assert run(db_driver, f"MATCH (:Doc)-[e:who]->() RETURN e.{KEY} AS model") == [
        {"model": "Certainty"}
    ]


# --- searched ----------------------------------------------------------------------------------------------------------


@no_type_check
async def test_an_edge_of_another_edge_model_with_the_same_fields_is_not_found(
    clear_database,
):
    m, _ = declare(court)
    data = await populated(m)

    async def found(where):
        return labels(await m.Doc.search(Match(where=where)))

    sure = {"type": "Certainty", "where": {"value": {"gte": 8}}}
    likely = {"type": "Likelihood", "where": {"value": {"gte": 8}}}
    # (Rome's edge of 9 is a `Likelihood`)
    assert await found({"who": {"edge": sure}}) == ["john 9"]
    assert await found({"who": {"edge": likely}}) == ["john 2, rome 9"]
    assert await found({"who": {"via": [sure]}}) == ["john 9"]
    assert await found({"who": {"via": [likely]}}) == ["john 2, rome 9"]
    assert await found({"who": {"is": str(data.rome.id), "edge": sure}}) == []
    assert await found({"who": {"type": "Place", "edge": likely}}) == ["john 2, rome 9"]
    # (in any relation of the document: every `Certainty` edge of 8 or more, at whatever place, and no other)
    assert await found({"$mentions": {"edge": sure}}) == [
        "john 9",
        "role in 2 out 9",
        "shares",
        "strongly 9",
    ]
    assert await found({"$mentions": {"via": [sure]}}) == [
        "john 9",
        "role in 2 out 9",
        "shares",
        "strongly 9",
    ]
    assert await found({"$mentions": {"via": [likely]}}) == [
        "john 2, rome 9",
        "role in 9 out 2",
    ]
    assert await found({"$any": {"edge": likely}}) == ["john 2, rome 9"]

    # (typed, and what refers to an entity)
    typed = m.Certainty.Where(value=Compare[int](gte=8))
    assert labels(await m.Doc.search(m.Doc.Where(who=Rel(edge=typed)))) == ["john 9"]
    assert labels(await m.Doc.search(m.Doc.Where(mentions_=AnyRel(via=[typed])))) == [
        "john 9",
        "role in 2 out 9",
        "shares",
        "strongly 9",
    ]
    places = await m.Place.search(
        m.Place.Where(
            incoming_=[
                IncomingFrom(
                    where=m.Doc.Where(),
                    field="who",
                    via=[m.Likelihood.Where(value=Compare[int](gte=8))],
                )
            ]
        )
    )
    assert labels(places) == ["Rome"]


@no_type_check
async def test_each_place_of_a_way_by_its_own_edge_model(clear_database):
    m, _ = declare(court)
    await populated(m)

    async def found(where):
        return labels(await m.Doc.search(Match(where=where)))

    def nine(model):
        return {"type": model, "where": {"value": {"eq": 9}}}

    # (the edge into the wrapper is a `Likelihood`, the edge out of it a `Certainty`: said by the edge model alone,
    # with no order needed)
    assert await found({"roles": {"via": [nine("Likelihood")]}}) == ["role in 9 out 2"]
    assert await found({"roles": {"via": [nine("Certainty")]}}) == ["role in 2 out 9"]
    assert await found({"roles": {"edge": nine("Certainty")}}) == ["role in 2 out 9"]
    step = {"type": "InRole", "edge": nine("Certainty")}
    assert await found({"roles": {"through": [step]}}) == ["role in 2 out 9"]
    # (what a wrapper declares for its own edges)
    half = {"type": "Share", "where": {"percent": {"gte": 50}}}
    assert await found({"shares": {"via": [half]}}) == ["shares"]
    assert await found({"shares": {"through": [{"type": "Either", "edge": half}]}}) == [
        "shares"
    ]


@no_type_check
async def test_what_an_edge_is_not_is_asked_of_the_edges_of_that_edge_model_alone(
    clear_database,
):
    m, _ = declare(court)
    await populated(m)

    async def found(where):
        return labels(await m.Doc.search(Match(where=where)))

    def certainty(**where):
        return {"type": "Certainty", "where": where}

    # (a `Certainty` with no note: not an edge of another edge model, which has none either, nor one with no edge
    # model at all)
    no_note = certainty(note={"exists": False})
    assert await found({"who": {"edge": no_note}}) == [
        "john 2, rome 9",
        "narrower 7",
    ]
    assert await found({"$mentions": {"edge": no_note}}) == [
        "john 2, rome 9",
        "narrower 7",
        "role in 2 out 9",
        "role in 9 out 2",
        "shares",
        "strongly 9",
    ]
    assert await found({"who": {"edge": certainty(value={"ne": 9})}}) == [
        "john 2, rome 9",
        "narrower 7",
    ]
    not_nine = certainty(**{"$not": {"value": {"eq": 9}}})
    assert await found({"who": {"via": [not_nine]}}) == [
        "john 2, rome 9",
        "narrower 7",
    ]


@no_type_check
async def test_an_edge_model_with_nothing_asked_is_an_edge_of_that_edge_model(
    clear_database,
):
    m, _ = declare(court)
    await populated(m)

    async def found(where):
        return labels(await m.Doc.search(Match(where=where)))

    assert await found({"who": {"via": [{"type": "Likelihood"}]}}) == [
        "john 2, rome 9",
        "rome 3",
    ]
    assert await found({"who": {"edge": {"type": "Likelihood", "where": {}}}}) == [
        "john 2, rome 9",
        "rome 3",
    ]
    assert await found({"who": {"via": [{"type": "Certainty"}], "exists": False}}) == [
        "barely",
        "plainly",
        "role in 2 out 9",
        "role in 9 out 2",
        "rome 3",
        "shares",
        "strongly 9",
    ]
    # (an edge with none of the values of its edge model is still an edge of it; one with no edge model is of none)
    assert await found({"$mentions": {"via": [{"type": "Bare"}]}}) == ["barely"]
    # (typed: the class alone)
    assert labels(
        await m.Doc.search(
            m.Doc.Where(roles=Rel(via=[m.Likelihood, m.InRole, m.Certainty]))
        )
    ) == ["role in 2 out 9", "role in 9 out 2"]
    assert (
        labels(
            await m.Doc.search(
                m.Doc.Where(roles=Rel(via=[m.Certainty, m.InRole, m.Likelihood]))
            )
        )
        == []
    )


@no_type_check
async def test_an_edge_model_below_another_is_found_by_the_one_above_it(
    clear_database,
):
    m, _ = declare(court)
    await populated(m)

    async def found(where):
        return labels(await m.Doc.search(Match(where=where)))

    nine = {"value": {"eq": 9}}
    # (`Strong` is a `Certainty`; a `Certainty` is not a `Strong`)
    assert await found(
        {"$mentions": {"via": [{"type": "Certainty", "where": nine}]}}
    ) == [
        "john 9",
        "role in 2 out 9",
        "strongly 9",
    ]
    assert await found({"$mentions": {"via": [{"type": "Strong", "where": nine}]}}) == [
        "strongly 9"
    ]
    assert await found(
        {"strongly": {"edge": {"type": "Certainty", "where": nine}}}
    ) == ["strongly 9"]


@no_type_check
async def test_an_entity_merged_into_another_keeps_the_edge_models_of_what_refers_to_it(
    db_driver, clear_database
):
    m, _ = declare(court)
    data = await populated(m)

    await m.Person.merge(absorb=data.John.id, into=data.Jane.id)

    moved = run(
        db_driver,
        f"""
        MATCH (d:Doc)-[e:who]->(p:Person {{id: $id}})
        RETURN d.label AS label, e.{KEY} AS model ORDER BY label
        """,
        id=str(data.Jane.id),
    )
    assert moved == [
        {"label": "john 2, rome 9", "model": "Certainty"},
        {"label": "john 9", "model": "Certainty"},
        {"label": "narrower 7", "model": "Certainty"},
    ]
    sure = {"type": "Certainty", "where": {"value": {"gte": 8}}}
    found = await m.Doc.search(
        Match(where={"who": {"is": str(data.Jane.id), "edge": sure}})
    )
    assert labels(found) == ["john 9"]


# --- the edges that were there before -----------------------------------------------------------------------------------


def forget(db_driver) -> None:
    run(db_driver, f"MATCH ()-[e]->() WHERE e.{KEY} IS NOT NULL SET e.{KEY} = null")


@pytest.mark.parametrize("batch_size", [None, 3])
@no_type_check
async def test_the_edges_that_were_there_are_given_the_edge_model_the_models_say(
    db_driver, clear_database, batch_size
):
    """(`RecordEdgeModels`, which the backends ship: a database written before edges said which edge model they are
    of is made as one written now)"""
    m, snapshot = declare(court)
    await populated(m)
    written = edges(db_driver)
    forget(db_driver)
    assert all(model is None for *_, model, _ in edges(db_driver))
    # (and one that says it wrongly, or says it of an edge with no edge model)
    run(db_driver, f"MATCH (:Doc)-[e:who]->(:Place) SET e.{KEY} = 'Certainty'")
    run(db_driver, f"MATCH (:Doc)-[e:plainly]->() SET e.{KEY} = 'Certainty'")

    if batch_size:
        await apply_changes_in_batches(
            current(), snapshot, [RecordEdgeModels()], batch_size
        )
    else:
        await apply_changes(current(), snapshot, [RecordEdgeModels()])

    assert edges(db_driver) == written == both_ways(AS_WRITTEN)
    # (again, there is nothing to do)
    await apply_changes(current(), snapshot, [RecordEdgeModels()])
    assert edges(db_driver) == written

    found = await m.Doc.search(
        Match(where={"who": {"edge": {"type": "Likelihood", "where": {}}}})
    )
    assert labels(found) == ["john 2, rome 9", "rome 3"]


# --- changes of the models ---------------------------------------------------------------------------------------------


@no_type_check
async def test_a_renamed_edge_model_is_renamed_on_its_edges(db_driver, clear_database):
    def v1():
        class Certainty(EdgeModel):
            value: int

        class Person(Entity):
            pass

        class Doc(Document):
            who: list[ViaEdge[Person, Certainty]]

        return ns(**locals())

    def v2():
        class Confidence(EdgeModel):
            value: int

        class Person(Entity):
            pass

        class Doc(Document):
            who: list[ViaEdge[Person, Confidence]]

        return ns(**locals())

    old_models, old = declare(v1)
    john = await old_models.Person.Create(label="John").save()
    await old_models.Doc.Create(label="d", who=[ref(john, value=9)]).save()
    new_models, new = declare(v2)

    await migrate(
        old,
        new,
        confirmed=[PossibleRename(what="model", old="Certainty", new="Confidence")],
    )

    assert edges(db_driver) == both_ways([("Doc", "who", "Person", "Confidence", 9)])
    found = await new_models.Doc.search(
        Match(where={"who": {"via": [{"type": "Confidence"}]}})
    )
    assert labels(found) == ["d"]


@no_type_check
async def test_a_relation_given_another_edge_model_or_none_says_so_on_its_edges(
    db_driver, clear_database
):
    def models(edge: str | None, inner: str | None = "Certainty"):
        def declare_them():
            class Certainty(EdgeModel):
                value: int | None = None

            class Likelihood(EdgeModel):
                value: int | None = None

            class Person(Entity):
                pass

            class InRole[T](ReifiedRelation[T]):
                pass

            by_name = {"Certainty": Certainty, "Likelihood": Likelihood}

            class Doc(Document):
                who: list[ViaEdge[Person, by_name[edge]] if edge else Person]
                roles: list[
                    InRole[ViaEdge[Person, by_name[inner]] if inner else Person]
                ]

            return ns(**locals())

        return declare_them

    old_models, old = declare(models("Certainty"))
    john = await old_models.Person.Create(label="John").save()
    await old_models.Doc.Create(
        label="d",
        who=[ref(john, value=9)],
        roles=[{"type": "InRole", "target": [ref(john, value=4)]}],
    ).save()
    assert edges(db_driver) == both_ways(
        [
            ("Doc", "who", "Person", "Certainty", 9),
            ("InRole", "target", "Person", "Certainty", 4),
        ]
    )

    # (another edge model with the same fields, on the field's own edge and on the edge inside a wrapper: the values
    # stay, and the edges say the new one)
    new_models, new = declare(models("Likelihood", "Likelihood"))
    await migrate(old, new)
    assert edges(db_driver) == both_ways(
        [
            ("Doc", "who", "Person", "Likelihood", 9),
            ("InRole", "target", "Person", "Likelihood", 4),
        ]
    )
    found = await new_models.Doc.search(
        Match(where={"who": {"via": [{"type": "Likelihood"}]}})
    )
    assert labels(found) == ["d"]

    # (and none at all)
    _, none = declare(models(None, None))
    await migrate(new, none)
    # (the values of the field's own edges are taken off with their edge model; those of an edge inside a wrapper
    # are left, as before, and say no edge model)
    assert edges(db_driver) == both_ways([("InRole", "target", "Person", None, 4)])
    assert run(db_driver, "MATCH (:Doc)-[e:who]->() RETURN count(e) AS n") == [{"n": 1}]

    # (and given one again: the edges that exist are of it)
    _, again = declare(models("Certainty", "Certainty"))
    await migrate(none, again)
    assert edges(db_driver) == both_ways(
        [
            ("Doc", "who", "Person", "Certainty", None),
            ("InRole", "target", "Person", "Certainty", 4),
        ]
    )
