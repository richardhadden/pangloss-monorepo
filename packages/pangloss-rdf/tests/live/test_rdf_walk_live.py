"""What is inside semantic spaces, by the walk over each node's path (`pangloss_models.spaces.signature`;
implementation_docs/spaces-and-comparison-plan.md, step 4.4): what the path asserts (`Known[...]`, `Not[Not[...]]`)
has its direct triples as if it were in no space, and still its `pgo:inSpace`; what it denies or neither asserts
nor denies (`Not[...]`, a space with no options, a part of a service that was not) has none, as before."""

from types import SimpleNamespace
from typing import Annotated

import pytest
import pytest_asyncio
from pangloss_models import Document, Embedded, Entity, SemanticSpace, initialise
from pangloss_rdf import IRI, RDFField, class_uri, convert, item_uri, property_uri
from pangloss_rdf.ontologies.crm import E7_Activity, P14_carried_out_by
from pangloss_rdf.uris import value_uri, property_name
from pangloss_rdf.vocabulary import RDF_TYPE, pgo

pytestmark = pytest.mark.asyncio(loop_scope="session")

CRM = "http://www.cidoc-crm.org/cidoc-crm/"


def declare():
    class Known[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Reported[T](SemanticSpace[T]):
        pass

    class Person(Entity):
        pass

    class Span(Embedded):
        year: int

    class Stmt(Document, E7_Activity):
        _meta = Document.Meta(create_directly=False)

        by: Annotated[Person, RDFField(parent=P14_carried_out_by)]
        when: Span

    class Service(Document):
        _meta = Document.Meta(create_directly=False)

        parts: list[Stmt]

    class Fact(Document):
        items: list[
            Stmt | Known[Stmt] | Not[Stmt | Not[Stmt] | Service] | Reported[Stmt]
        ]

    initialise()
    return SimpleNamespace(**locals())


def statement(person_id, label: str) -> dict:
    return {
        "type": "Stmt",
        "label": label,
        "by": {"type": "Person", "id": str(person_id)},
        "when": {"type": "Span", "year": 1500},
    }


def inside(space: str, *contents: dict) -> dict:
    return {"type": space, "contents": list(contents)}


@pytest_asyncio.fixture(loop_scope="session")
async def world(clear_database):
    m = declare()
    person = await m.Person.Create(label="Max").save()
    fact = await m.Fact.Create(
        label="F",
        items=[
            statement(person.id, "plain"),
            inside("Known", statement(person.id, "known")),
            inside("Not", statement(person.id, "not")),
            inside("Not", inside("Not", statement(person.id, "not not"))),
            inside(
                "Not",
                {
                    "type": "Service",
                    "label": "service",
                    "parts": [statement(person.id, "part")],
                },
            ),
            inside("Reported", statement(person.id, "reported")),
        ],
    ).save()
    read = await m.Fact.get(fact.id)
    quads = list(convert(read))
    found = {}

    def walk(node, spaces):
        if getattr(node, "type", None) == "Stmt":
            found[node.label] = (node, spaces)
        for name in ("items", "contents", "parts"):
            for child in getattr(node, name, None) or ():
                kind = child.__metatype__
                walk(
                    child,
                    [*spaces, item_uri(child._owner, child.id)]
                    if kind == "SemanticSpace"
                    else spaces,
                )

    walk(read, [])
    return SimpleNamespace(m=m, person=person, quads=quads, statements=found)


def triples(quads, s=None, p=None, o=None):
    return [
        q
        for q in quads
        if (s is None or q.subject == s)
        and (p is None or q.predicate == p)
        and (o is None or q.object == o)
    ]


def said(world, label: str) -> dict[str, bool | int]:
    """What is written of the statement of this label: its direct triples (the relation, the outside property and
    class, the embedded date), and whether each space around it is named"""
    m = world.m
    node, spaces = world.statements[label]
    subject = item_uri(m.Stmt, node.id)
    person = item_uri(m.Person, world.person.id)
    quads = world.quads
    span = value_uri(subject, property_name(m.Stmt, "when"))
    return {
        "by": bool(triples(quads, subject, property_uri(m.Stmt, "by"), person)),
        "P14": bool(triples(quads, subject, IRI(P14_carried_out_by.uri), person)),
        "E7": bool(triples(quads, subject, RDF_TYPE, IRI(f"{CRM}E7_Activity"))),
        "when": bool(triples(quads, subject, property_uri(m.Stmt, "when"), span)),
        "in_spaces": all(
            triples(quads, subject, pgo("inSpace"), space) for space in spaces
        ),
        "typed": bool(triples(quads, subject, RDF_TYPE, class_uri(m.Stmt))),
        "spaces": len(spaces),
    }


ASSERTED = {"by": True, "P14": True, "E7": True, "when": True}
NOT_ASSERTED = {"by": False, "P14": False, "E7": False, "when": False}


def direct(found: dict) -> dict:
    return {key: found[key] for key in ASSERTED}


async def test_a_statement_in_no_space_is_asserted(world):
    found = said(world, "plain")
    assert direct(found) == ASSERTED and found["spaces"] == 0


async def test_what_a_known_space_holds_is_asserted_and_still_in_its_space(world):
    found = said(world, "known")
    assert direct(found) == ASSERTED
    assert found["spaces"] == 1 and found["in_spaces"] and found["typed"]


async def test_what_a_not_holds_is_not_asserted(world):
    found = said(world, "not")
    assert direct(found) == NOT_ASSERTED
    assert found["spaces"] == 1 and found["in_spaces"] and found["typed"]
    # (the edge node is there: not asserted, but not lost)
    node, _ = world.statements["not"]
    assert triples(world.quads, item_uri(world.m.Stmt, node.id), pgo("edge"))


async def test_two_nots_assert_what_they_hold(world):
    found = said(world, "not not")
    assert direct(found) == ASSERTED
    assert found["spaces"] == 2 and found["in_spaces"]


async def test_a_part_of_a_service_that_was_not_is_not_asserted(world):
    found = said(world, "part")
    assert direct(found) == NOT_ASSERTED
    assert found["spaces"] == 1 and found["in_spaces"]


async def test_a_space_with_no_options_is_as_before(world):
    found = said(world, "reported")
    assert direct(found) == NOT_ASSERTED
    assert found["spaces"] == 1 and found["in_spaces"] and found["typed"]
