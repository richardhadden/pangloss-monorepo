"""A migration made in batches does what the same migration made whole does: the same graph, down
to the context of every node. Each case is run both ways, from nothing, and the graphs compared."""

import json
import re
from collections.abc import Awaitable, Callable
from types import SimpleNamespace as ns
from typing import Annotated, no_type_check

import pytest
from pangloss_models.field_definitions import FieldSubclassing
from pangloss_models.meta_kit.migrations import PossibleRename
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.model_bases.semantic_space import SemanticSpace

from .helpers import run
from .migration_support import declare, migrate, with_answers
from .test_migrations_enums import V1, shade, write_one
from .test_migrations_enums import models as enum_models
from .test_migrations_relations import person_models, person_payload
from .test_migrations_structure import (
    date_models,
    new_embedded_models,
    space_models,
    space_payload,
    wrapper_models,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

BATCH = 2  # (smaller than the number of things in each case, so that there are several batches)


def dump(db_driver) -> dict:
    """What is in the database, without ids and times: the nodes (labels, properties, context) and
    the edges (labels at both ends, type, properties), each as text, sorted"""

    def clean(value) -> str:
        text = json.dumps(value, sort_keys=True, default=str)
        return re.sub(r'"id": "[^"]+"', '"id": "…"', text)

    nodes = run(
        db_driver,
        "MATCH (n) WHERE NOT n:PGUser AND NOT n:PGMigration AND NOT n:PGMigrationLock "
        "RETURN labels(n) AS labels, properties(n) AS props",
    )
    shown = []
    for node in nodes:
        props = {
            key: value
            for key, value in node["props"].items()
            if key not in ("id", "head_node_id", "created_when", "updated_when")
        }
        meta = props.get("meta")
        if isinstance(meta, dict):
            props["meta"] = {
                k: v
                for k, v in meta.items()
                if k not in ("created_when", "updated_when")
            }
        shown.append(clean({"labels": sorted(node["labels"]), "props": props}))
    edges = run(
        db_driver,
        "MATCH (a)-[e]->(b) WHERE NOT a:PGUser AND NOT b:PGUser AND NOT a:PGMigration "
        "RETURN labels(a) AS a, type(e) AS type, properties(e) AS props, labels(b) AS b",
    )
    return {
        "nodes": sorted(shown),
        "edges": sorted(
            clean(
                {
                    "a": sorted(e["a"]),
                    "type": e["type"],
                    "props": e["props"],
                    "b": sorted(e["b"]),
                }
            )
            for e in edges
        ),
    }


def wipe(db_driver) -> None:
    run(db_driver, "MATCH (n) WHERE NOT n:PGUser DETACH DELETE n")


Case = Callable[[int | None], Awaitable[None]]


async def both_ways(db_driver, case: Case) -> dict:
    """Run the case whole, then in batches, from an empty database each time: the graphs are the same
    (and the batches were several: it is not that it fell back to doing it whole)"""
    from pangloss_memgraph.databases.memgraph.migrations import runner

    calls = []
    original = runner.apply_edges

    async def counted(*args, **kwargs):
        calls.append(1)
        return await original(*args, **kwargs)

    wipe(db_driver)
    await case(None)
    whole = dump(db_driver)
    assert not calls
    wipe(db_driver)
    runner.apply_edges = counted
    try:
        await case(BATCH)
    finally:
        runner.apply_edges = original
    assert len(calls) >= 3, f"made in {len(calls)} batches"
    batched = dump(db_driver)
    wipe(db_driver)
    assert batched["nodes"] == whole["nodes"]
    assert batched["edges"] == whole["edges"]

    # and one that stops part way (the second batch fails), and is run again from the start: what
    # was done is not there to do again, so the end is the same
    from . import migration_support

    original_apply = migration_support.apply_changes_in_batches

    async def stopping_and_again(*args, **kwargs):
        stops = []

        async def stops_on_the_second(*a, **k):
            stops.append(1)
            if len(stops) == 2:
                raise RuntimeError("stopped part way")
            return await original(*a, **k)

        runner.apply_edges = stops_on_the_second
        try:
            with pytest.raises(RuntimeError, match="stopped part way"):
                await original_apply(*args, **kwargs)
        finally:
            runner.apply_edges = original
        return await original_apply(*args, **kwargs)

    migration_support.apply_changes_in_batches = stopping_and_again
    try:
        await case(BATCH)
    finally:
        migration_support.apply_changes_in_batches = original_apply
    stopped = dump(db_driver)
    wipe(db_driver)
    assert stopped["nodes"] == whole["nodes"]
    assert stopped["edges"] == whole["edges"]
    return whole


# ---------------------------------------------------------------------------
# The cases
# ---------------------------------------------------------------------------


@no_type_check
async def test_unwrapping_a_reified_relation(db_driver, clear_database):
    async def case(batch):
        old_models, old = declare(person_models(wrapped=True))
        person = await old_models.Person.Create(label="Ann").save()
        for n in range(5):
            await old_models.Statement.Create(
                label=f"S{n}", person=person_payload(person, True, n)
            ).save()
        await old_models.Factoid.Create(
            label="F",
            statements=[
                {
                    "type": "Statement",
                    "label": "Nested",
                    "person": person_payload(person, True, 9),
                },
                {
                    "type": "Action",
                    "label": "Narrowed",
                    "person": person_payload(person, True, 8),
                    "carried_out_by": person_payload(person, True, 7),
                },
            ],
        ).save()
        _, new = declare(person_models(wrapped=False))
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, case)
    assert not any("IdentifiedAs" in node for node in graph["nodes"])


@no_type_check
async def test_wrapping_in_a_semantic_space(db_driver, clear_database):
    def only_negative():
        class Action(Document):
            pass

        class Statement(Document):
            action: Action

        class Negative[T](SemanticSpace[T]):
            pass

        class Factoid(Document):
            statements: list[Negative[Statement]]

        return ns(Action=Action, Statement=Statement, Factoid=Factoid)

    async def case(batch):
        old_models, old = declare(space_models(wrapped=False))
        for n in range(4):
            await old_models.Factoid.Create(
                label=f"F{n}", statements=space_payload(False)
            ).save()
        _, new = declare(only_negative)
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, case)
    assert (
        sum(
            '"Negative"' in node and '"SemanticSpace"' in node
            for node in graph["nodes"]
        )
        == 8
    )


@no_type_check
async def test_unwrapping_a_semantic_space(db_driver, clear_database):
    def wrapped():
        class Action(Document):
            pass

        class Statement(Document):
            action: Action

        class Negative[T](SemanticSpace[T]):
            pass

        class Factoid(Document):
            statements: list[Negative[Statement]]

        return ns(Action=Action, Statement=Statement, Factoid=Factoid)

    def plain():
        class Action(Document):
            pass

        class Statement(Document):
            action: Action

        class Factoid(Document):
            statements: list[Statement]

        return ns(Action=Action, Statement=Statement, Factoid=Factoid)

    async def case(batch):
        old_models, old = declare(wrapped)
        for n in range(4):
            await old_models.Factoid.Create(
                label=f"F{n}", statements=space_payload(True)
            ).save()
        _, new = declare(plain)
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, case)
    assert not any('"Negative"' in node for node in graph["nodes"])


@no_type_check
async def test_one_wrapper_for_another(db_driver, clear_database):
    async def case(batch):
        old_models, old = declare(wrapper_models(second=False))
        person = await old_models.Person.Create(label="Ann").save()
        for n in range(5):
            await old_models.Statement.Create(
                label=f"S{n}",
                person={
                    "type": "IdentifiedAs",
                    "certainty": n,
                    "old_note": "x",
                    "target": [{"type": "Person", "id": person.id}],
                },
            ).save()
        _, new = declare(wrapper_models(second=True))
        await migrate(
            old,
            new,
            batch_size=batch,
            declined=[PossibleRename(what="model", old="IdentifiedAs", new="ProxyFor")],
        )

    graph = await both_ways(db_driver, case)
    assert sum('"ProxyFor"' in node for node in graph["nodes"]) == 5


@no_type_check
async def test_literals_to_an_embedded_object_and_back(db_driver, clear_database):
    async def forward(batch):
        old_models, old = declare(date_models(embedded=False))
        for n in range(5):
            await old_models.Statement.Create(
                label=f"S{n}", when=str(n), precision=n, text="T"
            ).save()
        _, new = declare(date_models(embedded=True))
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, forward)
    assert sum("Date" in node for node in graph["nodes"]) == 5

    async def back(batch):
        old_models, old = declare(date_models(embedded=True))
        for n in range(5):
            await old_models.Statement.Create(
                label=f"S{n}", date={"when": str(n), "precision": n}, text="T"
            ).save()
        _, new = declare(date_models(embedded=False))
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, back)
    assert not any("Date" in node for node in graph["nodes"])


@no_type_check
async def test_a_model_renamed(db_driver, clear_database):
    def v1():
        class Action(Document):
            pass

        class Statement(Document):
            action: Action

        class Factoid(Document):
            statements: list[Statement]

        return ns(Action=Action, Statement=Statement, Factoid=Factoid)

    def v2():
        class Action(Document):
            pass

        class Claim(Document):
            action: Action

        class Factoid(Document):
            statements: list[Claim]

        return ns(Action=Action, Claim=Claim, Factoid=Factoid)

    async def case(batch):
        old_models, old = declare(v1)
        for n in range(4):
            await old_models.Factoid.Create(
                label=f"F{n}",
                statements=[
                    {
                        "type": "Statement",
                        "label": f"S{n}{m}",
                        "action": {"type": "Action", "label": "A"},
                    }
                    for m in range(2)
                ],
            ).save()
        _, new = declare(v2)
        await migrate(
            old,
            new,
            batch_size=batch,
            confirmed=[PossibleRename(what="model", old="Statement", new="Claim")],
        )

    graph = await both_ways(db_driver, case)
    assert not any('"Statement"' in node for node in graph["nodes"])
    assert sum('"Claim"' in node for node in graph["nodes"]) >= 8


@no_type_check
async def test_models_deleted_heads_and_nested(db_driver, clear_database):
    def v1():
        class Place(Entity):
            pass

        class Action(Document):
            pass

        class Statement(Document):
            action: Action

        return ns(Place=Place, Action=Action, Statement=Statement)

    def v2():
        class Statement(Document):
            pass

        return ns(Statement=Statement)

    async def case(batch):
        old_models, old = declare(v1)
        for n in range(5):
            await old_models.Place.Create(label=f"P{n}").save()
            await old_models.Statement.Create(
                label=f"S{n}", action={"type": "Action", "label": f"A{n}"}
            ).save()
        _, new = declare(v2)
        await migrate(old, new, batch_size=batch, declined=[])

    graph = await both_ways(db_driver, case)
    assert not any('"Place"' in node or '"Action"' in node for node in graph["nodes"])
    assert sum('"Statement"' in node for node in graph["nodes"]) == 5


@no_type_check
async def test_a_reverse_name_changed(db_driver, clear_database):
    def named(reverse: str):
        def declare_models():
            class Place(Entity):
                pass

            class Statement(Document):
                home: Annotated[Place, RelationConfig(reverse_name=reverse)]

            return ns(Place=Place, Statement=Statement)

        return declare_models

    async def case(batch):
        old_models, old = declare(named("residents"))
        place = await old_models.Place.Create(label="Paris").save()
        for n in range(5):
            await old_models.Statement.Create(
                label=f"S{n}", home={"type": "Place", "id": place.id}
            ).save()
        _, new = declare(named("lived_here"))
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, case)
    assert not any("residents" in edge for edge in graph["edges"])
    assert sum("lived_here" in edge for edge in graph["edges"]) == 5


@no_type_check
async def test_enum_values_changed_and_removed(db_driver, clear_database):
    async def changed(batch):
        old_enum, new_enum = shade(**V1), shade(**{**V1, "GREEN": "verde"})
        old_models, old = declare(enum_models(old_enum))
        for n in range(5):
            await write_one(old_models, f"S{n}", old_enum.GREEN, old_enum.BLUE)
        _, new = declare(enum_models(new_enum))
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, changed)
    assert not any('"favourite": "green"' in node for node in graph["nodes"])
    assert sum('"favourite": "verde"' in node for node in graph["nodes"]) == 5

    async def removed(batch):
        old_enum, new_enum = shade(**V1), shade(RED="red", BLUE="blue")
        old_models, old = declare(enum_models(old_enum))
        for n in range(5):
            await write_one(old_models, f"S{n}", old_enum.GREEN, old_enum.BLUE)
        _, new = declare(enum_models(new_enum))
        await migrate(
            old,
            new,
            batch_size=batch,
            answer=with_answers(RemoveEnumMember={"replacement": "RED"}),
        )

    graph = await both_ways(db_driver, removed)
    assert not any('"favourite": "green"' in node for node in graph["nodes"])


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

    async def case(batch):
        old_models, old = declare(v1)
        places = [await old_models.Place.Create(label=f"P{n}").save() for n in range(3)]
        for n in range(9):
            await old_models.Statement.Create(
                label=f"S{n}",
                homes=[
                    {"type": "Place", "id": place.id} for place in places[: 1 + n % 3]
                ],
            ).save()
        _, new = declare(v2)
        await migrate(
            old,
            new,
            batch_size=batch,
            answer=with_answers(AlterCardinality={"keep": "first"}),
        )

    graph = await both_ways(db_driver, case)
    assert (
        sum('"homes"' in edge and '"reverse"' not in edge for edge in graph["edges"])
        == 9
    )


@no_type_check
async def test_a_relation_narrowed_so_that_edges_are_removed(db_driver, clear_database):
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

    async def case(batch):
        old_models, old = declare(v1)
        person = await old_models.Person.Create(label="P").save()
        group = await old_models.Group.Create(label="G").save()
        for n in range(6):
            target = (
                {"type": "Group", "id": group.id}
                if n % 3
                else {"type": "Person", "id": person.id}
            )
            await old_models.Statement.Create(label=f"S{n}", about=target).save()
        _, new = declare(v2)
        await migrate(
            old,
            new,
            batch_size=batch,
            answer=with_answers(AlterRelationTarget={"on_narrowing": "remove"}),
        )

    graph = await both_ways(db_driver, case)
    assert not any('"Group"' in edge and '"about' in edge for edge in graph["edges"])


@no_type_check
async def test_properties_given_to_edges(db_driver, clear_database):
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

    async def case(batch):
        old_models, old = declare(v1)
        person = await old_models.Person.Create(label="P").save()
        for n in range(5):
            await old_models.Statement.Create(
                label=f"S{n}", about={"type": "Person", "id": person.id}
            ).save()
        _, new = declare(v2)
        await migrate(
            old,
            new,
            batch_size=batch,
            answer=with_answers(AlterEdgeModel={"defaults": {"level": 3}}),
        )

    graph = await both_ways(db_driver, case)
    assert sum('"level": 3' in edge for edge in graph["edges"]) == 10

    # ... and taken off again
    async def off(batch):
        old_models, old = declare(v2)
        person = await old_models.Person.Create(label="P").save()
        for n in range(5):
            await old_models.Statement.Create(
                label=f"S{n}",
                about={
                    "type": "Person",
                    "id": person.id,
                    "edge_properties": {"level": n},
                },
            ).save()
        _, new = declare(v1)
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, off)
    assert not any('"level"' in edge for edge in graph["edges"])


@no_type_check
async def test_a_field_that_narrows_a_parent_field_and_stops(db_driver, clear_database):
    def plain():
        class Person(Entity):
            pass

        class Statement(Document):
            involves: list[Person]

        class Action(Statement):
            carried_out_by: Person

        return ns(Person=Person, Action=Action)

    def narrowing():
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

    async def forward(batch):
        old_models, old = declare(plain)
        person = await old_models.Person.Create(label="P").save()
        for n in range(5):
            await old_models.Action.Create(
                label=f"A{n}",
                carried_out_by={"type": "Person", "id": person.id},
                involves=[],
            ).save()
        _, new = declare(narrowing)
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, forward)
    assert sum('"involves"' in edge for edge in graph["edges"]) == 5
    assert sum('"involves_reverse"' in edge for edge in graph["edges"]) == 5

    async def back(batch):
        old_models, old = declare(narrowing)
        person = await old_models.Person.Create(label="P").save()
        for n in range(5):
            await old_models.Action.Create(
                label=f"A{n}",
                carried_out_by={"type": "Person", "id": person.id},
                involves=[],
            ).save()
        _, new = declare(plain)
        await migrate(old, new, batch_size=batch)

    graph = await both_ways(db_driver, back)
    assert not any('"involves' in edge for edge in graph["edges"])


@no_type_check
async def test_a_semantic_space_renamed(db_driver, clear_database):
    def named(space: str):
        def declare_models():
            class Action(Document):
                pass

            class Statement(Document):
                action: Action

            if space == "Negative":

                class Negative[T](SemanticSpace[T]):
                    pass

                class Factoid(Document):
                    statements: list[Negative[Statement]]

            else:

                class Doubtful[T](SemanticSpace[T]):
                    pass

                class Factoid(Document):
                    statements: list[Doubtful[Statement]]

            return ns(Action=Action, Statement=Statement, Factoid=Factoid)

        return declare_models

    async def case(batch):
        old_models, old = declare(named("Negative"))
        for n in range(5):
            await old_models.Factoid.Create(
                label=f"F{n}", statements=space_payload(True)
            ).save()
        _, new = declare(named("Doubtful"))
        await migrate(
            old,
            new,
            batch_size=batch,
            confirmed=[PossibleRename(what="model", old="Negative", new="Doubtful")],
        )

    graph = await both_ways(db_driver, case)
    assert not any('"Negative"' in node for node in graph["nodes"])
    assert any(
        '"Doubtful"' in node and '"semantic_spaces"' in node for node in graph["nodes"]
    )


@no_type_check
async def test_a_new_embedded_object(db_driver, clear_database):
    async def case(batch):
        old_models, old = declare(new_embedded_models(embedded=False))
        for n in range(5):
            await old_models.Statement.Create(label=f"S{n}", text="T").save()
        _, new = declare(new_embedded_models(embedded=True))
        await migrate(
            old,
            new,
            batch_size=batch,
            answer=with_answers(
                AddField={"default": {"when": "unknown", "precision": 0}}
            ),
        )

    graph = await both_ways(db_driver, case)
    assert sum('"Date"' in node for node in graph["nodes"]) == 5
