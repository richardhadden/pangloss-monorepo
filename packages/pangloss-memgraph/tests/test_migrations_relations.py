"""Applying changes to relations: data written with the old models, migrated, and read with the
new. (`signature` compares a migrated graph with one written by the new models.)"""

import json
from types import SimpleNamespace as ns
from typing import Annotated, no_type_check

import pytest
from pangloss_models.exceptions import PanglossMigrationAnswerNeeded
from pangloss_models.field_definitions import FieldSubclassing
from pangloss_models.migrations import PossibleRename
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.trait import Trait

from .helpers import run
from .migration_support import declare, migrate, with_answers

pytestmark = pytest.mark.asyncio(loop_scope="session")


def signature(db_driver, head_id) -> dict:
    """What a document is made of, without ids and times: the labels of its nodes and the
    edges between them (their types, and the names of their properties)"""
    nodes = run(
        db_driver,
        """
        MATCH (n) WHERE n.id = $id OR n.head_node_id = $id
        RETURN labels(n) AS labels, keys(n) AS keys
        """,
        id=str(head_id),
    )
    edges = run(
        db_driver,
        """
        MATCH (a)-[e]->(b)
        WHERE (a.id = $id OR a.head_node_id = $id) AND (b.id = $id OR b.head_node_id = $id
              OR b:Entity)
        RETURN labels(a) AS source, type(e) AS type, keys(e) AS keys, labels(b) AS target
        """,
        id=str(head_id),
    )

    def freeze(rows):
        return sorted(
            json.dumps(
                {k: sorted(v) if isinstance(v, list) else v for k, v in row.items()},
                sort_keys=True,
            )
            for row in rows
        )

    return {"nodes": freeze(nodes), "edges": freeze(edges)}


# ---------------------------------------------------------------------------
# Renaming and removing
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_renamed_relation_keeps_its_edges_and_its_reverse(
    db_driver, clear_database
):
    def v1():
        class Place(Entity):
            pass

        class Statement(Document):
            home: Place

        return ns(Place=Place, Statement=Statement)

    def v2():
        class Place(Entity):
            pass

        class Statement(Document):
            residence: Place

        return ns(Place=Place, Statement=Statement)

    old_models, old = declare(v1)
    place = await old_models.Place.Create(label="Paris").save()
    statement = await old_models.Statement.Create(
        label="S", home={"type": "Place", "id": place.id}
    ).save()
    new_models, new = declare(v2)

    await migrate(
        old,
        new,
        confirmed=[
            PossibleRename(what="field", scope="Statement", old="home", new="residence")
        ],
    )

    read = await new_models.Statement.get(id=statement.id)
    assert read.residence.id == place.id
    # ... and from the entity, under the new reverse name
    entity = await new_models.Place.get(id=place.id)
    assert [s.id for s in entity.residence_reverse] == [statement.id]
    edges = run(
        db_driver,
        "MATCH ()-[e]->() WHERE NOT type(e) STARTS WITH 'is_' AND NOT type(e) = 'created_by' RETURN DISTINCT type(e) AS t ORDER BY t",
    )
    assert [e["t"] for e in edges] == ["residence", "residence_reverse"]


@no_type_check
async def test_the_reverse_name_alone_changes(db_driver, clear_database):
    def v1():
        class Place(Entity):
            pass

        class Statement(Document):
            home: Place

        return ns(Place=Place, Statement=Statement)

    def v2():
        class Place(Entity):
            pass

        class Statement(Document):
            home: Annotated[Place, RelationConfig(reverse_name="lived_in_by")]

        return ns(Place=Place, Statement=Statement)

    old_models, old = declare(v1)
    place = await old_models.Place.Create(label="Paris").save()
    statement = await old_models.Statement.Create(
        label="S", home={"type": "Place", "id": place.id}
    ).save()
    new_models, new = declare(v2)
    await migrate(old, new)

    entity = await new_models.Place.get(id=place.id)
    assert [s.id for s in entity.lived_in_by] == [statement.id]


@no_type_check
async def test_removing_a_relation_to_an_entity_leaves_the_entity(
    db_driver, clear_database
):
    def v1():
        class Place(Entity):
            pass

        class Statement(Document):
            home: Place

        return ns(Place=Place, Statement=Statement)

    def v2():
        class Place(Entity):
            pass

        class Statement(Document):
            pass

        return ns(Place=Place, Statement=Statement)

    old_models, old = declare(v1)
    place = await old_models.Place.Create(label="Paris").save()
    await old_models.Statement.Create(
        label="S", home={"type": "Place", "id": place.id}
    ).save()
    new_models, new = declare(v2)
    await migrate(old, new)

    assert run(db_driver, "MATCH (:Statement)-[e]->(:Place) RETURN count(e) AS n") == [
        {"n": 0}
    ]
    assert run(db_driver, "MATCH (:Place)-[e]->(:Statement) RETURN count(e) AS n") == [
        {"n": 0}
    ]
    assert (await new_models.Place.get(id=place.id)).label == "Paris"


@no_type_check
async def test_removing_a_relation_to_a_document_removes_what_it_held(
    db_driver, clear_database
):
    def v1():
        class Action(Document):
            pass

        class Statement(Document):
            action: Action

        return ns(Statement=Statement)

    def v2():
        class Statement(Document):
            pass

        return ns(Statement=Statement)

    old_models, old = declare(v1)
    await old_models.Statement.Create(
        label="S", action={"type": "Action", "label": "A"}
    ).save()
    new_models, new = declare(v2)
    await migrate(old, new)

    labels = run(db_driver, "MATCH (n:PGIndexableNode) RETURN n.label AS label")
    # the action went with the field (its model is deleted by its own change)
    assert [row["label"] for row in labels] == ["S"]


# ---------------------------------------------------------------------------
# Cardinality, targets, edge properties
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_list_that_becomes_one_value(db_driver, clear_database):
    def v1():
        class Place(Entity):
            pass

        class Statement(Document):
            homes: list[Place]

        return ns(Place=Place, Statement=Statement)

    def v2():
        class Place(Entity):
            pass

        class Statement(Document):
            homes: Place

        return ns(Place=Place, Statement=Statement)

    old_models, old = declare(v1)
    first = await old_models.Place.Create(label="First").save()
    second = await old_models.Place.Create(label="Second").save()
    statement = await old_models.Statement.Create(
        label="S",
        homes=[{"type": "Place", "id": first.id}, {"type": "Place", "id": second.id}],
    ).save()
    one = await old_models.Statement.Create(
        label="One", homes=[{"type": "Place", "id": second.id}]
    ).save()
    new_models, new = declare(v2)

    with pytest.raises(PanglossMigrationAnswerNeeded, match="which to keep"):
        await migrate(old, new)
    await migrate(old, new, answer=with_answers(AlterCardinality={"keep": "first"}))

    read = await new_models.Statement.get(id=statement.id)
    assert read.homes.id == first.id
    assert (await new_models.Statement.get(id=one.id)).homes.id == second.id
    # the other place has lost the reverse edge too
    assert [
        s.label for s in (await new_models.Place.get(id=second.id)).homes_reverse
    ] == ["One"]


@no_type_check
async def test_a_relation_that_can_no_longer_be_to_something(db_driver, clear_database):
    def v1():
        class Person(Entity):
            pass

        class Group(Entity):
            pass

        class Statement(Document):
            about: Person | Group

        return ns(Person=Person, Group=Group, Statement=Statement)

    def v2():
        class Person(Entity):
            pass

        class Group(Entity):
            pass

        class Statement(Document):
            about: Person

        return ns(Person=Person, Group=Group, Statement=Statement)

    old_models, old = declare(v1)
    person = await old_models.Person.Create(label="P").save()
    group = await old_models.Group.Create(label="G").save()
    to_person = await old_models.Statement.Create(
        label="A", about={"type": "Person", "id": person.id}
    ).save()
    await old_models.Statement.Create(
        label="B", about={"type": "Group", "id": group.id}
    ).save()
    new_models, new = declare(v2)

    with pytest.raises(PanglossMigrationAnswerNeeded, match="no longer be to"):
        await migrate(old, new)
    await migrate(
        old, new, answer=with_answers(AlterRelationTarget={"on_narrowing": "remove"})
    )

    assert (await new_models.Statement.get(id=to_person.id)).about.id == person.id
    assert run(
        db_driver, "MATCH (:Statement)-[e:about]->(:Group) RETURN count(e) AS n"
    ) == [{"n": 0}]
    assert run(db_driver, "MATCH (:Group)-[e]->(:Statement) RETURN count(e) AS n") == [
        {"n": 0}
    ]


@no_type_check
async def test_properties_on_the_edges_are_added(db_driver, clear_database):
    def v1():
        class Person(Entity):
            pass

        class Statement(Document):
            about: Person

        return ns(Person=Person, Statement=Statement)

    def v2():
        class Certainty(EdgeModel):
            level: int

        class Person(Entity):
            pass

        class Statement(Document):
            about: ViaEdge[Person, Certainty]

        return ns(Person=Person, Statement=Statement)

    old_models, old = declare(v1)
    person = await old_models.Person.Create(label="P").save()
    statement = await old_models.Statement.Create(
        label="S", about={"type": "Person", "id": person.id}
    ).save()
    new_models, new = declare(v2)

    with pytest.raises(PanglossMigrationAnswerNeeded, match="level"):
        await migrate(old, new)
    await migrate(
        old, new, answer=with_answers(AlterEdgeModel={"defaults": {"level": 3}})
    )

    read = await new_models.Statement.get(id=statement.id)
    assert read.about.edge_properties.level == 3
    reverse = run(db_driver, "MATCH ()-[e:about_reverse]->() RETURN properties(e) AS p")
    assert reverse == [{"p": {"reverse": True, "level": 3}}]


@no_type_check
async def test_narrowing_a_parent_field_writes_the_edges_of_the_parent(
    db_driver, clear_database
):
    def v1():
        class Person(Entity):
            pass

        class Statement(Document):
            involves: list[Person]

        class Action(Statement):
            carried_out_by: Person

        return ns(Person=Person, Action=Action)

    def v2():
        class Person(Entity):
            pass

        class Statement(Document):
            involves: list[Person]

        class Action(Statement):
            carried_out_by: Annotated[
                Person,
                RelationConfig(
                    subclasses_parent_fields=[
                        FieldSubclassing("involves", field_on_model=Statement)
                    ]
                ),
            ]

        return ns(Person=Person, Action=Action)

    old_models, old = declare(v1)
    person = await old_models.Person.Create(label="P").save()
    action = await old_models.Action.Create(
        label="A", carried_out_by={"type": "Person", "id": person.id}, involves=[]
    ).save()
    new_models, new = declare(v2)
    await migrate(old, new)

    types = run(
        db_driver,
        "MATCH (:Action)-[e]->(:Person) RETURN type(e) AS t ORDER BY t",
    )
    assert [row["t"] for row in types] == ["carried_out_by", "involves"]
    reverse = run(
        db_driver,
        "MATCH (:Person)-[e]->(:Action) WHERE e.reverse RETURN type(e) AS t ORDER BY t",
    )
    assert [row["t"] for row in reverse] == [
        "carried_out_by_reverse",
        "involves_reverse",
    ]
    # (as the new models read it: under the narrower name)
    assert (await new_models.Action.get(id=action.id)).carried_out_by.id == person.id


# ---------------------------------------------------------------------------
# Wrapping a relation in a node
# ---------------------------------------------------------------------------


def person_models(wrapped: bool):
    """`Statement.person: Person` or `IdentifiedAs[Person]`, with a subclass that narrows it, a
    document that holds statements, and a person that the relations are to"""

    def declare_models():
        class Agent(Trait):
            pass

        class Person(Entity, Agent):
            pass

        if wrapped:

            class IdentifiedAs[T](ReifiedRelation[T]):
                certainty: int

            class Statement(Document):
                person: IdentifiedAs[Person]

            class Action(Statement):
                carried_out_by: Annotated[
                    IdentifiedAs[Person],
                    RelationConfig(
                        reverse_name="carried_out",
                        subclasses_parent_fields=[
                            FieldSubclassing("person", field_on_model=Statement)
                        ],
                    ),
                ]

        else:

            class Statement(Document):
                person: Person

            class Action(Statement):
                carried_out_by: Annotated[
                    Person,
                    RelationConfig(
                        reverse_name="carried_out",
                        subclasses_parent_fields=[
                            FieldSubclassing("person", field_on_model=Statement)
                        ],
                    ),
                ]

        class Factoid(Document):
            statements: list[Statement | Action]

        return ns(Person=Person, Statement=Statement, Action=Action, Factoid=Factoid)

    return declare_models


def person_payload(person, wrapped: bool, certainty=3):
    reference = {"type": "Person", "id": person.id}
    return (
        {"type": "IdentifiedAs", "certainty": certainty, "target": [reference]}
        if wrapped
        else reference
    )


@no_type_check
async def test_a_relation_is_wrapped_in_a_reified_relation(db_driver, clear_database):
    """`person: Person` becomes `person: IdentifiedAs[Person]`: a node on each edge, for a
    statement that is a head, one that is nested, a subclass that narrows the field, and
    wherever it is. The result is what the new models would have written."""
    old_models, old = declare(person_models(wrapped=False))
    person = await old_models.Person.Create(label="Ann").save()
    plain = await old_models.Statement.Create(
        label="Plain", person=person_payload(person, False)
    ).save()
    factoid = await old_models.Factoid.Create(
        label="F",
        statements=[
            {
                "type": "Statement",
                "label": "Nested",
                "person": person_payload(person, False),
            },
            {
                "type": "Action",
                "label": "Narrowed",
                "person": person_payload(person, False),
                "carried_out_by": person_payload(person, False),
            },
        ],
    ).save()

    new_models, new = declare(person_models(wrapped=True))
    await migrate(
        old, new, answer=with_answers(WrapRelation={"defaults": {"certainty": 5}})
    )

    # a statement that is a head
    head = await new_models.Statement.get(id=plain.id)
    assert head.person.certainty == 5
    assert head.person.target[0].id == person.id

    # nested ones, and the subclass (whose two edge pairs share the one relation node)
    read = await new_models.Factoid.get(id=factoid.id)
    by_label = {s.label: s for s in read.statements}
    assert by_label["Nested"].person.target[0].id == person.id
    assert by_label["Narrowed"].carried_out_by.target[0].id == person.id
    assert by_label["Narrowed"].carried_out_by.certainty == 5

    # the person, read from the other end, through the relation
    await new_models.Person.get(id=person.id)
    wrappers = run(
        db_driver,
        "MATCH (r:IdentifiedAs) RETURN r.head_node_id AS head, r.head_node_type AS type, r.certainty AS c",
    )
    assert len(wrappers) == 3
    assert {row["c"] for row in wrappers} == {5}
    assert {row["type"] for row in wrappers} == {"Statement", "Factoid"}

    # it is what the new models write: the same nodes and the same edges
    native_plain = await new_models.Statement.Create(
        label="Plain", person=person_payload(person, True, 5)
    ).save()
    native_factoid = await new_models.Factoid.Create(
        label="F",
        statements=[
            {
                "type": "Statement",
                "label": "Nested",
                "person": person_payload(person, True, 5),
            },
            {
                "type": "Action",
                "label": "Narrowed",
                "person": person_payload(person, True, 5),
                "carried_out_by": person_payload(person, True, 5),
            },
        ],
    ).save()
    assert signature(db_driver, plain.id) == signature(db_driver, native_plain.id)
    assert signature(db_driver, factoid.id) == signature(db_driver, native_factoid.id)


@no_type_check
async def test_wrapping_is_repeatable_and_needs_the_values_of_the_wrapper(
    db_driver, clear_database
):
    old_models, old = declare(person_models(wrapped=False))
    person = await old_models.Person.Create(label="Ann").save()
    await old_models.Statement.Create(
        label="S", person=person_payload(person, False)
    ).save()
    new_models, new = declare(person_models(wrapped=True))

    with pytest.raises(PanglossMigrationAnswerNeeded, match="certainty"):
        await migrate(old, new)
    assert run(db_driver, "MATCH (r:IdentifiedAs) RETURN count(r) AS n") == [{"n": 0}]

    answer = with_answers(WrapRelation={"defaults": {"certainty": 1}})
    await migrate(old, new, answer=answer)
    # (again: the relations are wrapped already)
    await migrate(old, new, answer=answer)
    assert run(db_driver, "MATCH (r:IdentifiedAs) RETURN count(r) AS n") == [{"n": 1}]


@no_type_check
async def test_a_wrapped_relation_is_unwrapped(db_driver, clear_database):
    old_models, old = declare(person_models(wrapped=True))
    person = await old_models.Person.Create(label="Ann").save()
    statement = await old_models.Statement.Create(
        label="S", person=person_payload(person, True)
    ).save()
    new_models, new = declare(person_models(wrapped=False))

    await migrate(old, new)

    assert run(db_driver, "MATCH (r:IdentifiedAs) RETURN count(r) AS n") == [{"n": 0}]
    read = await new_models.Statement.get(id=statement.id)
    assert read.person.id == person.id
    assert [
        s.label for s in (await new_models.Person.get(id=person.id)).person_reverse
    ] == ["S"]
    native = await new_models.Statement.Create(
        label="S", person=person_payload(person, False)
    ).save()
    assert signature(db_driver, statement.id) == signature(db_driver, native.id)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_trait_added_to_a_model_adds_a_label(db_driver, clear_database):
    def v1():
        class Agent(Trait):
            pass

        class Person(Entity):
            pass

        return ns(Person=Person)

    def v2():
        class Agent(Trait):
            pass

        class Person(Entity, Agent):
            pass

        return ns(Person=Person)

    old_models, old = declare(v1)
    await old_models.Person.Create(label="Ann").save()
    new_models, new = declare(v2)
    await migrate(old, new)

    labels = run(db_driver, "MATCH (p:Person) RETURN labels(p) AS labels")[0]["labels"]
    assert "Agent" in labels


@no_type_check
async def test_a_renamed_model(db_driver, clear_database):
    def v1():
        class Human(Entity):
            name: str

        class Statement(Document):
            about: Human

        return ns(Human=Human, Statement=Statement)

    def v2():
        class Person(Entity):
            name: str

        class Statement(Document):
            about: Person

        return ns(Person=Person, Statement=Statement)

    old_models, old = declare(v1)
    human = await old_models.Human.Create(label="Ann", name="Ann").save()
    statement = await old_models.Statement.Create(
        label="S", about={"type": "Human", "id": human.id}
    ).save()
    new_models, new = declare(v2)

    await migrate(
        old, new, confirmed=[PossibleRename(what="model", old="Human", new="Person")]
    )

    person = await new_models.Person.get(id=human.id)
    assert person.type == "Person"
    assert [s.id for s in person.about_reverse] == [statement.id]
    assert (await new_models.Statement.get(id=statement.id)).about.id == human.id


@no_type_check
async def test_a_deleted_model_takes_its_nodes_and_their_records(
    db_driver, clear_database
):
    def v1():
        class Place(Entity):
            pass

        class Person(Entity):
            pass

        return ns(Place=Place, Person=Person)

    def v2():
        class Person(Entity):
            pass

        return ns(Person=Person)

    old_models, old = declare(v1)
    await old_models.Place.Create(label="Paris").save()
    keep = await old_models.Person.Create(label="Ann").save()
    new_models, new = declare(v2)
    await migrate(old, new, declined=[])

    assert run(db_driver, "MATCH (n:Place) RETURN count(n) AS n") == [{"n": 0}]
    assert run(db_driver, "MATCH (c:PGCreation) RETURN count(c) AS n") == [{"n": 1}]
    assert (await new_models.Person.get(id=keep.id)).label == "Ann"


def contexts(db_driver, head_id) -> list[str]:
    """The semantic spaces and context labels of the relation nodes of a document, without ids"""
    import re

    rows = run(
        db_driver,
        """
        MATCH (r:IdentifiedAs) WHERE r.head_node_id = $id
        RETURN r.meta.semantic_spaces AS spaces, r.meta.context_labels AS labels,
               r.meta.created_by AS created_by
        """,
        id=str(head_id),
    )
    return sorted(
        re.sub(r'"id": "[^"]+"', '"id": "…"', json.dumps(row, sort_keys=True))
        for row in rows
    )


@no_type_check
async def test_a_wrapper_is_in_the_semantic_space_of_what_it_is_on(
    db_driver, clear_database
):
    """The context of the new node is what the models give it: inside a semantic space, and
    the statement that holds it is a part of the context"""
    from pangloss_models.model_bases.semantic_space import SemanticSpace

    def models(wrapped: bool):
        def declare_models():
            class Person(Entity):
                pass

            if wrapped:

                class IdentifiedAs[T](ReifiedRelation[T]):
                    certainty: int

                class Statement(Document):
                    person: IdentifiedAs[Person]

            else:

                class Statement(Document):
                    person: Person

            class Negative[T](SemanticSpace[T]):
                pass

            class Factoid(Document):
                statements: list[Statement | Negative[Statement]]

            return ns(Person=Person, Statement=Statement, Factoid=Factoid)

        return declare_models

    def statements(person, wrapped):
        reference = person_payload(person, wrapped, 5)
        return [
            {"type": "Statement", "label": "Outside", "person": reference},
            {
                "type": "Negative",
                "contents": [
                    {"type": "Statement", "label": "Inside", "person": reference}
                ],
            },
        ]

    old_models, old = declare(models(wrapped=False))
    person = await old_models.Person.Create(label="Ann").save()
    factoid = await old_models.Factoid.Create(
        label="F", statements=statements(person, False)
    ).save()
    new_models, new = declare(models(wrapped=True))
    await migrate(
        old, new, answer=with_answers(WrapRelation={"defaults": {"certainty": 5}})
    )
    native = await new_models.Factoid.Create(
        label="F", statements=statements(person, True)
    ).save()

    migrated, written = contexts(db_driver, factoid.id), contexts(db_driver, native.id)
    assert migrated == written
    # (one is in the space, and one is not, and has the statement in its context)
    assert any('"Negative"' in row for row in migrated)
    assert any("#rootcontext" in row for row in migrated)
