"""The models and the helpers of the tests of merging entities (`test_merge_*.py`): a model with every kind of relation
to an entity that Pangloss has, so that a merge is seen to move each kind and an undo to put each back"""

from typing import Annotated, Any

from annotated_types import MaxLen, MinLen
from pangloss_models import (
    Conjunction,
    Document,
    EdgeModel,
    Embedded,
    Entity,
    FieldSubclassing,
    KeepOnMerge,
    MergeRules,
    ReifiedRelation,
    RelationConfig,
    SemanticSpace,
    ViaEdge,
    initialise,
)

from .helpers import run


class Models:
    """The classes `declare` made, by name (`m.Person`)"""

    def __init__(self, classes: dict[str, Any]):
        self.__dict__.update(classes)


def declare() -> Any:
    class Certainty(EdgeModel):
        certainty: int

    class Person(Entity):
        _meta = Entity.Meta(
            create_with_id=True,
            create_inline=True,
            accept_url_as_id=True,
            merge=MergeRules(label_into="aliases"),
        )
        aliases: list[str] = []
        born: int | None = None
        died: int | None = None
        knows: list[Person]

    class Poet(Person):
        works: list[str] = []

    class Soldier(Person):
        rank: str | None = None

    class PoetSoldier(Poet, Soldier):
        pass

    class Group(Entity):
        members: list[Person]

    class Negative[T](SemanticSpace[T]):
        pass

    class Identification[T](ReifiedRelation[T]):
        note: str | None = None

    class Both[A, B](Conjunction):
        first: A
        second: B

    class Residence(Embedded):
        place: str | None = None
        host: Person | None = None

    # A plain relation, and a list of them
    class Mention(Document):
        of: Person
        others: list[Person]

    # Edge properties, and the order of a list
    class Rated(Document):
        rated: list[ViaEdge[Person, Certainty]]

    # Through a reified relation, a semantic space, a conjunction, and an embedded object
    class Wrapped(Document):
        identified: list[Identification[Person]]
        denied: list[Negative[Person]]
        paired: list[Both[Person, Person]]
        stayed: Residence | None = None

    # A field that narrows another: stored under both names
    class Statement(Document):
        concerns: list[Person]

    class Order(Statement):
        given_by: Annotated[
            Person,
            RelationConfig(
                subclasses_parent_fields=[
                    FieldSubclassing(field_name="concerns", field_on_model=Statement)
                ]
            ),
        ]

    # Documents nested in a document
    class Factoid(Document):
        statements: list[Statement | Order | Negative[Statement | Order]]

    # Two different fields; a list that must hold two; a relation that only takes a subclass
    class Marriage(Document):
        husband: Person
        wife: Person

    class Witnessed(Document):
        witnesses: Annotated[list[Person], MinLen(2)]

    class Poem(Document):
        by: Poet

    # A relation a merge leaves where it is
    class SameAs(Document):
        entities: Annotated[list[Person], MinLen(2), MaxLen(2), KeepOnMerge()]
        argument: str | None = None

    initialise()
    return Models(
        {
            "Entity": Entity,
            **{
                name: value
                for name, value in locals().items()
                if isinstance(value, type)
            },
        }
    )


def ref(entity: Any, type_name: str = "Person") -> dict[str, Any]:
    return {"type": type_name, "id": entity.id}


def filled(model: Any, fields: dict[str, Any]) -> dict[str, Any]:
    """`fields`, with an empty list for each list of relations of the class that is not given (a `Create` wants every
    one)"""
    lists = {
        name: []
        for name, definition in model._meta.fields.relation_fields.items()
        if definition.wrapper is not None and name in model.Create.model_fields
    }
    return {**lists, **fields}


async def make(model: Any, label: str, **fields: Any) -> Any:
    """A new document or entity of the class"""
    return await model.Create(label=label, **filled(model, fields)).save()


def part(model: Any, label: str | None = None, **fields: Any) -> dict[str, Any]:
    """A document nested in another, as a payload"""
    return {
        "type": model.__name__,
        **({"label": label} if label else {}),
        **filled(model, fields),
    }


async def person(m: Any, label: str, **fields: Any) -> Any:
    return await make(m.Person, label, **fields)


def edges_to(db_driver, id: Any) -> list[tuple[str, str, int | None]]:
    """The forward edges of fields into a node: (the type of the node each is from, the field, its place in its
    list), in order"""
    rows = run(
        db_driver,
        """
        MATCH (n:PGIndexableNode {id: $id})<-[e]-(s:PGIndexableNode)
        WHERE NOT coalesce(e.reverse, false)
        RETURN s.type AS source, type(e) AS field, e.pg_position AS position
        """,
        id=str(id),
    )
    return sorted((r["source"], r["field"], r["position"]) for r in rows)


def reverse_edges_from(db_driver, id: Any) -> list[tuple[str, str]]:
    """The reverse edges out of a node: (the type of the node each goes to, its name)"""
    rows = run(
        db_driver,
        """
        MATCH (n:PGIndexableNode {id: $id})-[e]->(s:PGIndexableNode)
        WHERE coalesce(e.reverse, false)
        RETURN s.type AS target, type(e) AS field
        """,
        id=str(id),
    )
    return sorted((r["target"], r["field"]) for r in rows)


def merged_into(db_driver, id: Any) -> str | None:
    return run(
        db_driver,
        "MATCH (n:PGIndexableNode {id: $id}) RETURN n.merged_into AS into",
        id=str(id),
    )[0]["into"]


def version_of(db_driver, id: Any) -> int:
    return run(
        db_driver,
        """
        MATCH (n:HeadNode {id: $id})
        RETURN size([(n)<-[:is_update_of]-(u:PGUpdate) | u]) + 1 AS version
        """,
        id=str(id),
    )[0]["version"]


def moves_of(db_driver, merge_id: Any) -> list[dict[str, Any]]:
    return run(
        db_driver,
        """
        MATCH (m:PGMergeMove {pg_merge: $id})
        RETURN m.pg_source_type AS source, m.pg_field AS field, m.pg_reverse AS reverse,
               m.pg_dropped AS dropped, m.pg_late AS late, m.pg_holder AS holder, properties(m) AS all
        ORDER BY source, field
        """,
        id=str(merge_id),
    )


async def every_kind(m: Any, who: Any, other: Any) -> dict[str, Any]:
    """Documents and entities that refer to `who` by every kind of relation the models have (and, beside it, to
    `other`, so that the places in the lists matter)"""
    made: dict[str, Any] = {}
    made["mention"] = await make(
        m.Mention, "A mention", of=ref(who), others=[ref(other), ref(who)]
    )
    made["rated"] = await make(
        m.Rated,
        "A rating",
        rated=[
            {**ref(other), "edge_properties": {"certainty": 3}},
            {**ref(who), "edge_properties": {"certainty": 7}},
        ],
    )
    made["wrapped"] = await make(
        m.Wrapped,
        "Wrapped",
        identified=[
            {"type": "Identification", "target": [ref(who)], "note": "probably"}
        ],
        denied=[{"type": "Negative", "contents": [ref(who)]}],
        paired=[{"type": "Both", "first": ref(who), "second": ref(who)}],
        stayed={"type": "Residence", "place": "an inn", "host": ref(who)},
    )
    made["order"] = await make(m.Order, "An order", given_by=ref(who))
    made["factoid"] = await make(
        m.Factoid,
        "A factoid",
        statements=[
            part(m.Statement, "Concerns two", concerns=[ref(other), ref(who)]),
            {
                "type": "Negative",
                "contents": [part(m.Order, "Not ordered", given_by=ref(who))],
            },
        ],
    )
    made["group"] = await make(m.Group, "A group", members=[ref(other), ref(who)])
    await m.Person.Update(id=other.id, label=other.label, knows=[ref(who)]).save()
    return made
