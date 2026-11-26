"""The walk over what is stored (`pangloss_models.spaces`; implementation_docs/spaces-and-comparison-plan.md, step
3.2): the signature of a node from the path a query reads of it, and from the path a view has, with nothing else
read of the database."""

from types import SimpleNamespace as ns
from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Degree,
    DegreeStep,
    Document,
    Entity,
    Ground,
    Modal,
    SemanticSpace,
)
from pangloss_models.spaces import registered_grounds, registered_spaces, signature

from .helpers import run
from .migration_support import declare

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models():
    class P(Document):
        pass

    class Service(Document):
        parts: list[P]

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Might[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))

    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command"), fit="prescribes", degree="expected"
        )
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    class Order(Document):
        thing: Ordered[P | Not[P]]

    class Factoid(Document):
        statements: list[P | Service | Order | Not[P | Service | Not[P] | Might[P]]]

    return ns(Factoid=Factoid, P=P)


def doc(type: str, label: str, **fields) -> dict:
    return {"type": type, "label": label, **fields}


def space(type: str, *contents, **fields) -> dict:
    return {"type": type, "contents": list(contents), **fields}


def statements() -> list[dict]:
    return [
        doc("P", "plain"),
        doc("Service", "service", parts=[doc("P", "part")]),
        space("Not", doc("P", "denied")),
        space("Not", space("Not", doc("P", "twice"))),
        space("Not", doc("Service", "no service", parts=[doc("P", "no part")])),
        space("Not", space("Might", doc("P", "cannot"))),
        doc("Order", "order", thing=space("Ordered", doc("P", "ordered"))),
        doc(
            "Order",
            "order not to",
            thing=space(
                "Ordered", space("Not", doc("P", "forbidden")), how_likely="unlikely"
            ),
        ),
    ]


# (veridical, lean, degree, fit, force) of each labelled document
EXPECTED = {
    "plain": (1, None, None, "describes", None),
    "service": (1, None, None, "describes", None),
    "part": (1, None, None, "describes", None),
    "denied": (-1, None, None, "describes", None),
    "twice": (1, None, None, "describes", None),
    "no service": (-1, None, None, "describes", None),
    # (the flat list of spaces, ["Not"], would say it was denied)
    "no part": (0, "neither", None, "describes", None),
    # (no necessity of this flavour is declared, so "cannot have been" commits to nothing)
    "cannot": (0, "against", None, "describes", "necessity"),
    "order": (1, None, None, "describes", None),
    "ordered": (0, "for", "expected", "prescribes", "necessity"),
    "order not to": (1, None, None, "describes", None),
    "forbidden": (0, "against", "unlikely", "prescribes", "necessity"),
}


def told(path) -> tuple:
    given = signature(path, registered_spaces())
    return (given.veridical, given.lean, given.degree, given.fit, given.force)


def labelled(node, found: dict | None = None) -> dict:
    """Every document of a view, by its label"""
    found = {} if found is None else found
    if getattr(node, "label", None):
        found[node.label] = node
    for name in ("statements", "parts", "contents", "thing"):
        held = getattr(node, name, None)
        for item in held if isinstance(held, list) else [held]:
            if item is not None:
                labelled(item, found)
    return found


@no_type_check
async def test_the_signature_of_each_node_from_the_path_that_is_stored(
    db_driver, clear_database
):
    made, _ = declare(models)
    factoid = await made.Factoid.Create(label="F", statements=statements()).save()
    rows = run(
        db_driver,
        "MATCH (n) WHERE n.head_node_id = $id AND n.label IS NOT NULL RETURN n.label AS label, n.meta.path AS path",
        id=str(factoid.id),
    )
    assert {row["label"]: told(row["path"]) for row in rows} == EXPECTED


@no_type_check
async def test_the_signature_of_each_node_of_a_view(db_driver, clear_database):
    made, _ = declare(models)
    factoid = await made.Factoid.Create(label="F", statements=statements()).save()
    read = await made.Factoid.get(factoid.id)
    assert told(read.meta.path) == (1, None, None, "describes", None)
    nodes = labelled(read)
    del nodes["F"]
    assert {label: told(node.meta.path) for label, node in nodes.items()} == EXPECTED
    # (the statement that prescribes is the order, by its id)
    by = signature(nodes["forbidden"].meta.path).prescribed_by
    assert by == str(nodes["order not to"].id)


@no_type_check
async def test_the_signature_of_a_nested_document_read_alone_or_listed(
    db_driver, clear_database
):
    made, _ = declare(models)
    factoid = await made.Factoid.Create(label="F", statements=statements()).save()
    nodes = labelled(await made.Factoid.get(factoid.id))
    alone = await made.P.get(nodes["forbidden"].id)
    assert told(alone.meta.path) == EXPECTED["forbidden"]
    listed = {item.label: item for item in (await made.P.list()).results}
    assert {label: told(item.meta.path) for label, item in listed.items()} == {
        label: EXPECTED[label] for label in listed
    }
    assert len(listed) >= 8


@no_type_check
async def test_an_update_that_changes_the_degree_changes_the_signature(
    db_driver, clear_database
):
    made, _ = declare(models)
    factoid = await made.Factoid.Create(label="F", statements=statements()).save()
    again = statements()
    del again[-1]["thing"]["how_likely"]
    await made.Factoid.Update(id=factoid.id, label="F", statements=again).save()
    nodes = labelled(await made.Factoid.get(factoid.id))
    # (nothing entered: the class's default)
    assert told(nodes["forbidden"].meta.path) == (
        0,
        "against",
        "expected",
        "prescribes",
        "necessity",
    )


# --- the ground of the head (step 3.5): the stored path begins with the head, whose class says where the walk starts


@no_type_check
def grounded_models():
    class Source(Entity):
        pass

    class P(Document):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Charter(Document):
        _meta = Document.Meta(ground=Ground(by="issued_by"))
        issued_by: Source
        statements: list[P | Not[P]]

    class Rumour(Document):
        _meta = Document.Meta(ground=Ground(veridical=0, degree="possible"))
        statements: list[P | Not[P]]

    return ns(Source=Source, Charter=Charter, Rumour=Rumour, P=P)


@no_type_check
async def test_the_signature_starts_from_the_ground_of_the_head_that_is_stored(
    db_driver, clear_database
):
    made, _ = declare(grounded_models)
    source = await made.Source.Create(label="The chancery").save()
    held = [doc("P", "said"), space("Not", doc("P", "denied"))]
    charter = await made.Charter.Create(
        label="C", issued_by={"type": "Source", "id": source.id}, statements=held
    ).save()
    rumour = await made.Rumour.Create(label="R", statements=held).save()
    spaces, grounds = registered_spaces(), registered_grounds()

    def of(head_id) -> dict:
        rows = run(
            db_driver,
            "MATCH (n) WHERE n.head_node_id = $id AND n.label IS NOT NULL "
            "RETURN n.label AS label, n.meta.path AS path",
            id=str(head_id),
        )
        return {row["label"]: signature(row["path"], spaces, grounds) for row in rows}

    in_charter, in_rumour = of(charter.id), of(rumour.id)
    assert {k: (v.veridical, v.lean, v.degree) for k, v in in_charter.items()} == {
        "said": (1, None, None),
        "denied": (-1, None, None),
    }
    assert {k: (v.veridical, v.lean, v.degree) for k, v in in_rumour.items()} == {
        "said": (0, "for", "possible"),
        "denied": (0, "against", "possible"),
    }
    assert {v.standing for v in (*in_charter.values(), *in_rumour.values())} == {
        "claim"
    }
    assert all(v.grounded_by is None for v in in_rumour.values())

    # (whose a statement of the charter is: the field the ground names, read of the head the signature names)
    read = await made.Charter.get(charter.id)
    nodes = labelled(read)
    by = signature(nodes["denied"].meta.path, spaces, grounds).grounded_by
    assert by.head == str(charter.id) and by.field == "issued_by"
    assert getattr(await made.Charter.get(by.head), by.field).id == source.id

    # (the head itself has no path: its class is the caller's to name)
    assert read.meta.path == []
    itself = signature(read.meta.path, spaces, grounds, head=read.type)
    assert (itself.standing, itself.grounded_by.field, itself.grounded_by.head) == (
        "claim",
        "issued_by",
        None,
    )
    entity = await made.Source.get(source.id)
    assert (
        signature(entity.meta.path, spaces, grounds, head="Source").standing == "record"
    )
