"""The ground of a head in the RDF export (`pangloss_models.Ground`; implementation_docs/spaces-and-comparison-plan.md,
step 4.5): what the ground says of the graph is in the default graph (`pgo:standing`, and `pgo:accordingTo` for each
entity the ground's `by` reaches); under a head whose ground leaves what it holds neither asserted nor denied,
nothing has its direct triples, as in a space that does not assert."""

from types import SimpleNamespace
from typing import Annotated

import pytest
from pangloss_models import (
    Document,
    Entity,
    Ground,
    ReifiedRelation,
    SemanticSpace,
    initialise,
)
from pangloss_rdf import IRI, RDFField, convert, item_uri, property_uri
from pangloss_rdf.ontologies.crm import (
    E7_Activity,
    E31_Document,
    P14_carried_out_by,
)
from pangloss_rdf.terms import Lit
from pangloss_rdf.vocabulary import RDF_TYPE, pgo

pytestmark = pytest.mark.asyncio(loop_scope="session")

CRM = "http://www.cidoc-crm.org/cidoc-crm/"


def declare():
    class Known[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    class Person(Entity):
        pass

    class Source(Entity):
        pass

    class Place(Entity):
        within: Place | None = None

    class Cited[T](ReifiedRelation[T]):
        page: str = ""

    class Stmt(Document, E7_Activity):
        _meta = Document.Meta(create_directly=False)

        by: Annotated[Person, RDFField(parent=P14_carried_out_by)]

    class Charter(Document):
        _meta = Document.Meta(ground=Ground(by="sources"))
        sources: list[Source | Cited[Source]]
        items: list[Stmt]

    class Rumour(Document, E31_Document):
        _meta = Document.Meta(
            ground=Ground(veridical=0, degree="possible", by="told_by")
        )
        told_by: Person
        hidden_from: Annotated[Person | None, RDFField(exclude=True)] = None
        items: list[Stmt | Known[Stmt]]

    # (whose it is, in a field the export leaves out)
    class Secret(Document):
        _meta = Document.Meta(ground=Ground(by="told_by"))
        told_by: Annotated[Person, RDFField(exclude=True)]

    class Note(Document):
        items: list[Stmt]

    initialise()
    return SimpleNamespace(**locals())


def triples(quads, s=None, p=None, o=None):
    return [
        q
        for q in quads
        if (s is None or q.subject == s)
        and (p is None or q.predicate == p)
        and (o is None or q.object == o)
    ]


def statement(person, label: str) -> dict:
    return {
        "type": "Stmt",
        "label": label,
        "by": {"type": "Person", "id": str(person.id)},
    }


def direct(m, quads, node, person) -> tuple[bool, bool, bool]:
    """Whether a statement has its relation, its outside property and its outside class"""
    subject, who = item_uri(m.Stmt, node.id), item_uri(m.Person, person.id)
    return (
        bool(triples(quads, subject, property_uri(m.Stmt, "by"), who)),
        bool(triples(quads, subject, IRI(P14_carried_out_by.uri), who)),
        bool(triples(quads, subject, RDF_TYPE, IRI(f"{CRM}E7_Activity"))),
    )


def standing(quads, head) -> list[str]:
    found = triples(quads, head, pgo("standing"))
    # (said of the graph: in the default graph, as who made it is)
    assert all(q.graph is None for q in found)
    return [q.object.lexical for q in found if isinstance(q.object, Lit)]


async def test_a_claim_says_its_standing_and_whose_it_is(clear_database):
    m = declare()
    person = await m.Person.Create(label="Max").save()
    annals = await m.Source.Create(label="The annals").save()
    roll = await m.Source.Create(label="The roll").save()
    charter = await m.Charter.Create(
        label="C",
        sources=[
            {"type": "Source", "id": str(annals.id)},
            {
                "type": "Cited",
                "page": "4",
                "target": [{"type": "Source", "id": str(roll.id)}],
            },
        ],
        items=[statement(person, "said")],
    ).save()
    read = await m.Charter.get(charter.id)
    quads = list(convert(read))
    head = item_uri(m.Charter, charter.id)
    assert standing(quads, head) == ["claim"]
    by = triples(quads, head, pgo("accordingTo"))
    # (directly, and through the reified relation to what it is about)
    assert {q.object for q in by} == {
        item_uri(m.Source, annals.id),
        item_uri(m.Source, roll.id),
    }
    assert all(q.graph is None for q in by)
    # (a claim asserts what it holds, as before)
    assert direct(m, quads, read.items[0], person) == (True, True, True)


async def test_the_record_and_a_document_that_says_nothing(clear_database):
    m = declare()
    person = await m.Person.Create(label="Max").save()
    outer = await m.Place.Create(label="Tyrol").save()
    place = await m.Place.Create(
        label="Innsbruck", within={"type": "Place", "id": str(outer.id)}
    ).save()
    quads = list(convert(await m.Place.get(place.id)))
    head = item_uri(m.Place, place.id)
    assert standing(quads, head) == ["record"]
    assert not triples(quads, head, pgo("accordingTo"))
    # (the record has its direct triples as before)
    assert triples(
        quads, head, property_uri(m.Place, "within"), item_uri(m.Place, outer.id)
    )

    note = await m.Note.Create(label="N", items=[statement(person, "noted")]).save()
    read = await m.Note.get(note.id)
    quads = list(convert(read))
    assert standing(quads, item_uri(m.Note, note.id)) == ["claim"]
    assert not triples(quads, item_uri(m.Note, note.id), pgo("accordingTo"))
    assert direct(m, quads, read.items[0], person) == (True, True, True)


async def test_what_a_rumour_holds_is_not_asserted(clear_database):
    m = declare()
    person = await m.Person.Create(label="Max").save()
    rumour = await m.Rumour.Create(
        label="R",
        told_by={"type": "Person", "id": str(person.id)},
        items=[
            statement(person, "rumoured"),
            {"type": "Known", "contents": [statement(person, "known in a rumour")]},
        ],
    ).save()
    read = await m.Rumour.get(rumour.id)
    quads = list(convert(read))
    head = item_uri(m.Rumour, rumour.id)
    assert standing(quads, head) == ["claim"]
    plain, known = read.items[0], read.items[1].contents[0]
    assert direct(m, quads, plain, person) == (False, False, False)
    # (a space that asserts keeps what the ground says: still neither)
    assert direct(m, quads, known, person) == (False, False, False)
    # (not asserted, but not lost: the statement is there, typed, with its edge node)
    subject = item_uri(m.Stmt, plain.id)
    assert triples(quads, subject, pgo("edge"))
    # (and the head's own relation to it has no direct triple either)
    assert not triples(quads, head, property_uri(m.Rumour, "items"), subject)
    # (but that there is a rumour, and whose it is, is not rumoured: its outside class, and the field its ground
    # names, directly and of the graph)
    who = item_uri(m.Person, person.id)
    assert triples(quads, head, RDF_TYPE, IRI(f"{CRM}E31_Document"))
    assert triples(quads, head, property_uri(m.Rumour, "told_by"), who)
    assert [q.object for q in triples(quads, head, pgo("accordingTo"))] == [who]


async def test_whose_it_is_is_not_said_from_a_field_the_export_leaves_out(
    clear_database,
):
    m = declare()
    person = await m.Person.Create(label="Max").save()
    secret = await m.Secret.Create(
        label="S", told_by={"type": "Person", "id": str(person.id)}
    ).save()
    quads = list(convert(await m.Secret.get(secret.id)))
    head = item_uri(m.Secret, secret.id)
    assert standing(quads, head) == ["claim"]
    assert not triples(quads, head, pgo("accordingTo"))
    assert not triples(quads, o=item_uri(m.Person, person.id))
