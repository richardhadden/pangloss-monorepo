"""What other packages add, on real reads: a date's bounds, and a typology's concepts"""

import importlib
from typing import Annotated

import pytest
from pangloss_models import Document, Entity, initialise
from pangloss_rdf import RDFField, convert, item_uri
from pangloss_rdf.export import read
from pangloss_rdf.ontologies.crm import P4_has_time_span
from pangloss_rdf.terms import IRI
from pangloss_rdf.vocabulary import RDF_TYPE, pgo, skos
from pangloss_typology import Typed, Typology, TypologyMeta

pytestmark = pytest.mark.asyncio(loop_scope="session")

P82A = IRI("http://www.cidoc-crm.org/cidoc-crm/P82a_begin_of_the_begin")


def dates():
    """The models of dates declared again, as the registry of the last test was emptied, and the converter on them"""
    from pangloss_dates import models

    # (imported first: its first import, on the old classes, would otherwise register it a second time)
    converter = importlib.import_module("pangloss_dates.rdf")
    fresh = importlib.reload(models)
    importlib.reload(converter)
    return fresh.Date


@pytest.fixture(autouse=True, scope="module")
def registered():
    import pangloss_typology.rdf  # noqa: F401


def objects(quads, subject, predicate):
    return [
        q.object for q in quads if q.subject == subject and q.predicate == predicate
    ]


async def test_a_date_has_its_bounds(clear_database):
    Date = dates()

    class Event(Document):
        when: Annotated[Date, RDFField(parent=P4_has_time_span)]

    initialise()
    made = await Event(
        label="e",
        when={
            "type": "ExactDate",
            "year": 1500,
            "month": 3,
            "day": 1,
            "calendar": "gregorian",
        },
    ).save()
    quads = list(convert(await Event.get(made.id)))
    node = next(q.object for q in quads if q.predicate.value.endswith("Event.when"))
    assert [o.lexical for o in objects(quads, node, pgo("earliest"))] == ["1500-03-01"]
    assert [o.lexical for o in objects(quads, node, P82A)] == ["1500-03-01"]
    event = item_uri(Event, made.id)
    assert objects(quads, event, IRI(P4_has_time_span.uri)) == [node]


async def test_an_open_period_has_no_end(clear_database):
    Date = dates()

    class Event(Document):
        when: Date

    initialise()
    made = await Event(
        label="e",
        when={
            "type": "Period",
            "calendar": "gregorian",
            "start": {"type": "ExactDate", "year": 1500},
            "end": {"type": "OngoingDate"},
        },
    ).save()
    quads = list(convert(await Event.get(made.id)))
    node = next(q.object for q in quads if q.predicate.value.endswith("Event.when"))
    assert objects(quads, node, pgo("earliest"))
    assert not objects(quads, node, pgo("latest"))


async def test_a_type_is_a_concept_under_its_supertype(clear_database):
    class Post(Entity):
        has_type: list[Typed[RoleTypology]]

    class RoleTypology(Typology):
        _typology_meta = TypologyMeta(name="RoleType")

    initialise()
    official = await RoleTypology.create("Official")
    secretary = await RoleTypology.create("Secretary", supertype=official.id)
    model = RoleTypology.__dict__.get("entity") or next(
        m
        for m in __import__("pangloss_models").ModelRegistry._models
        if m.__name__ == "RoleType"
    )
    quads = list(convert(await read(model, secretary.id)))
    uri = item_uri(model, secretary.id)
    assert skos("Concept") in objects(quads, uri, RDF_TYPE)
    assert objects(quads, uri, skos("broader")) == [item_uri(model, official.id)]
