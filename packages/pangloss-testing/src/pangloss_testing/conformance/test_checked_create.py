"""`checked_create` (`pangloss_cypher.write_functions`, among a Cypher backend's operations): what a create does before
it writes, and nothing after. It gives the model for the database, its plan and the entities written in it that exist;
it writes nothing, announces nothing, marks nothing; and it refuses what the create of the same payload refuses, with
the same error."""

from collections.abc import Callable
from typing import Any, no_type_check
from uuid import uuid4, uuid7

import pytest
from pangloss_core import storage_of
from pangloss_cypher.write_plan import (
    InlineEntity,
    PlannedNode,
    ReferenceToExisting,
    WritePlan,
    plan_create,
)
from pangloss_models import (
    Cites,
    Document,
    Entity,
    PanglossWriteRefused,
    WriteEvent,
    before_create,
    hooks,
    initialise,
)
from pangloss_users import current_request_username
from pydantic import AnyHttpUrl

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")

WORK = "checked-create-work"


@pytest.fixture
def events():
    """What is announced (`hooks.after_write`); and every write leaves work pending, so that a mark would be seen"""
    heard: list[WriteEvent] = []
    hooks.after_write.append(heard.append)
    asks = lambda model: [WORK]  # noqa: E731
    hooks.pending_work.append(asks)
    yield heard
    hooks.pending_work.remove(asks)
    hooks.after_write.remove(heard.append)


@no_type_check
def models():
    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)

    class Remark(Document):
        _meta = Document.Meta(create_directly=False)
        text: str = ""

    class Statement(Document):
        _meta = Document.Meta(create_with_id=True)
        text: str
        about: Person
        remarks: list[Remark]

        @before_create
        async def not_refused(self):
            if self.text == "refuse":
                raise PanglossWriteRefused("This statement is refused", field="text")

    class Note(Document):
        pass

    class SameAs(Document):
        evidence: list[Cites[Statement]]  # ty: ignore[invalid-type-form]

    class Will(Document):
        testator: Person
        _meta = Document.Meta(label_template="Will of {testator}")

    initialise()
    return Person, Remark, Statement, Note, SameAs, Will


def checked_create(instance, **options):
    return storage_of().operations.checked_create(instance, **options)


def counts(db_driver) -> tuple[int, int, int]:
    """The nodes, the edges and the marks of pending work in the database"""
    return (
        run(db_driver, "MATCH (n) RETURN count(n) AS c")[0]["c"],
        run(db_driver, "MATCH ()-[e]->() RETURN count(e) AS c")[0]["c"],
        run(db_driver, "MATCH (p:PGPending) RETURN count(p) AS c")[0]["c"],
    )


# (what differs between two makings of the same payload: the ids of the nodes made, and the times)
VARYING = {"id", "head_node_id", "created_when", "updated_when"}


def stable(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        key: stable(value) if isinstance(value, dict) else value
        for key, value in properties.items()
        if key not in VARYING
    }


def shape(plan: WritePlan, existing) -> tuple:
    """A plan as far as two plans of one payload can be compared"""

    def target(node) -> tuple:
        if isinstance(node, PlannedNode):
            return ("node", node.type, node.labels, stable(node.properties), node.urls)
        if isinstance(node, ReferenceToExisting):
            return ("reference", node.value, node.is_url, node.allowed_types)
        assert isinstance(node, InlineEntity)
        return ("entity", node.key, node.type, node.allowed_types)

    return (
        plan.is_update,
        target(plan.head),
        [
            (node.type, relation.edges, relation.edge_properties, first, target(to))
            for node, relation, first in plan.walk(existing)
            for to in [relation.target]
        ],
    )


async def refused_alike(db_driver, events, make: Callable[[], Any], **options):
    """`checked_create` of the payload `make` gives refuses it as its create does, and neither leaves anything.
    Gives the error"""
    before = counts(db_driver)
    with pytest.raises(Exception) as checked:
        await checked_create(make(), **options)
    assert counts(db_driver) == before
    with pytest.raises(Exception) as written:
        await make().save(**options)
    assert counts(db_driver) == before
    assert type(checked.value) is type(written.value)
    assert str(checked.value) == str(written.value)
    assert events == []
    return checked.value


@no_type_check
async def test_a_create_that_would_pass_writes_announces_and_marks_nothing_and_plans_what_the_create_writes(
    db_driver, clear_database, events
):
    Person, _, Statement, *_ = models()
    ann = await Person.Create(label="Ann").save()
    url = AnyHttpUrl("http://example.com/people/bob")
    bob = await Person.Create(id=url, create_new=True, label="Bob").save()
    events.clear()

    given = uuid7()

    def make():
        return Statement.Create(
            id=given,
            create_new=True,
            label="Ann speaks",
            text="said",
            about={"type": "Person", "id": ann.id},
            remarks=[
                {"type": "Remark", "label": "Aside", "text": "one"},
                {"type": "Remark", "label": "Another", "text": "two"},
            ],
        )

    payload = make()
    sent = payload.model_dump()
    before = counts(db_driver)
    db_instance, plan, existing = await checked_create(payload)

    assert counts(db_driver) == before
    assert events == []
    # (the caller's payload is as it was given)
    assert payload.model_dump() == sent
    assert db_instance.id == given and db_instance.label == "Ann speaks"
    assert plan.head.id == str(given) and plan.head.type == "Statement"
    assert existing == {}

    # The same payload written: its plan is the one given, and nothing was taken that it needs
    made = await make().save()
    assert made.id == given
    assert [e.op for e in events] == ["create"]
    assert shape(plan, existing) == shape(plan_create(events[0].payload), existing)
    assert counts(db_driver)[2] > before[2]

    # An entity that the document writes and that exists is given as existing
    inline = Statement.Create(
        label="Of Bob",
        text="said",
        about={"type": "Person", "id": url, "create_new": True, "label": "Bob"},
        remarks=[],
    )
    _, plan, existing = await checked_create(inline)
    assert [found.id for found in existing.values()] == [str(bob.id)]
    assert [
        first
        for _, relation, first in plan.walk(existing)
        if isinstance(relation.target, InlineEntity)
    ] == [True]


@no_type_check
async def test_each_refusal_is_the_refusal_of_the_create(
    db_driver, clear_database, events
):
    Person, Remark, Statement, Note, SameAs, _ = models()
    ann = await Person.Create(label="Ann").save()
    url = AnyHttpUrl("http://example.com/people/ann")
    await Person.Create(id=url, create_new=True, label="Ann again").save()
    taken = uuid7()
    statement = await Statement.Create(
        id=taken,
        create_new=True,
        label="First",
        text="said",
        about={"type": "Person", "id": ann.id},
        remarks=[],
    ).save()
    note = await Note.Create(label="A note").save()
    events.clear()

    def statement_of(**more):
        return lambda: Statement.Create(
            **{
                "label": "S",
                "text": "said",
                "about": {"type": "Person", "id": ann.id},
                "remarks": [],
                **more,
            }
        )

    # A reference to an entity that is not there
    missing = uuid7()
    error = await refused_alike(
        db_driver, events, statement_of(about={"type": "Person", "id": missing})
    )
    assert str(missing) in str(error)
    # An id that is taken
    error = await refused_alike(
        db_driver, events, statement_of(id=taken, create_new=True)
    )
    assert str(taken) in str(error)
    # A URL that is taken
    await refused_alike(
        db_driver,
        events,
        lambda: Person.Create(id=url, create_new=True, label="Ann a third time"),
    )
    # A `@before_create` that refuses
    error = await refused_alike(db_driver, events, statement_of(text="refuse"))
    assert "This statement is refused" in str(error)
    # A citation of what is not there, of what its field does not take, of an entity
    for cited in (
        {"type": "Statement", "id": uuid4()},
        {"type": "Note", "id": note.id},
        {"type": "Statement", "id": ann.id},
    ):
        await refused_alike(
            db_driver,
            events,
            lambda cited=cited: SameAs.Create(label="Same", evidence=[cited]),
        )
    # A document that cannot be made on its own
    await refused_alike(
        db_driver,
        events,
        lambda: Remark.Create(label="Alone", text="x"),
    )
    # A creator that is not a user
    error = await refused_alike(db_driver, events, statement_of(), created_by="no_one")
    assert "no_one" in str(error)
    # A user that is not there
    with current_request_username.set("nobody_by_this_name"):
        await refused_alike(db_driver, events, statement_of())

    # (and what can be cited is cited, when it is checked)
    _, plan, _ = await checked_create(
        SameAs.Create(
            label="Same", evidence=[{"type": "Statement", "id": statement.id}]
        )
    )
    assert plan.head.type == "SameAs"


@no_type_check
async def test_a_templated_label_is_filled_in_the_plan(
    db_driver, clear_database, events
):
    Person, *_, Will = models()
    anne = await Person.Create(label="Anne Hathaway").save()
    events.clear()

    before = counts(db_driver)
    db_instance, plan, _ = await checked_create(
        Will.Create(testator={"type": "Person", "id": anne.id})
    )
    assert counts(db_driver) == before and events == []
    assert db_instance.label == "Will of Anne Hathaway"
    assert plan.head.properties["label"] == "Will of Anne Hathaway"
    assert plan.head.properties["label_auto"] is True


@no_type_check
async def test_the_head_has_what_the_apps_put_on_a_new_head_as_the_options_ask(
    db_driver, clear_database, events
):
    def asked(model):
        status = hooks.requested_review_status.get()
        return {"asked_status": status} if status else {}

    hooks.new_head_properties.append(asked)
    try:
        Person, _, Statement, *_ = models()
        ann = await Person.Create(label="Ann").save()

        def make():
            return Statement.Create(
                label="S",
                text="said",
                about={"type": "Person", "id": ann.id},
                remarks=[],
            )

        _, plan, _ = await checked_create(make(), review_status="published")
        assert plan.head.properties["asked_status"] == "published"
        _, plan, _ = await checked_create(make())
        assert "asked_status" not in plan.head.properties

        made = await make().save(review_status="published")
        assert run(
            db_driver,
            "MATCH (n:Statement {id: $id}) RETURN n.asked_status AS s",
            id=str(made.id),
        ) == [{"s": "published"}]
    finally:
        hooks.new_head_properties.remove(asked)
