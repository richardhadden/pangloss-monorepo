"""What packages add: the hook, dates' bounds and typology's concepts"""

import sys
from uuid import uuid4

from pangloss_models import Entity, initialise
from pangloss_rdf import IRI, Lit, register_rdf_converter
from pangloss_rdf.context import Context
from pangloss_rdf.terms import xsd
from pangloss_rdf.vocabulary import pgo


def test_a_converter_adds_and_one_with_replace_writes_instead(monkeypatch):
    from pangloss_rdf.convert import convert as run

    monkeypatch.setattr(sys.modules["pangloss_rdf.convert"], "_converters", [])

    class Thing(Entity):
        note: str

    initialise()

    def adds(value, uri, context):
        yield context.quad(uri, pgo("added"), Lit("x", xsd("string")))

    register_rdf_converter(Thing, adds)
    view = Thing.HeadView.model_construct(
        id=uuid4(), type="Thing", label="t", note="n", meta=None
    )
    predicates = {q.predicate.value for q in run(view)}
    assert pgo("added").value in predicates
    assert any(p.endswith("Thing.note") for p in predicates)

    register_rdf_converter(Thing, adds, replace=True)
    predicates = {q.predicate.value for q in run(view)}
    assert not any(p.endswith("Thing.note") for p in predicates)


def test_a_date_as_xsd_is_gregorian_and_says_its_era():
    from pangloss_dates.calendar import Calendar, to_jdn
    from pangloss_dates.rdf import as_xsd_date

    assert as_xsd_date(to_jdn(1500, 3, 1, Calendar.GREGORIAN)).lexical == "1500-03-01"
    # (the same day in the two calendars)
    assert as_xsd_date(to_jdn(1500, 3, 1, Calendar.JULIAN)).lexical == "1500-03-11"
    assert as_xsd_date(to_jdn(-43, 3, 15, Calendar.GREGORIAN)).lexical == "-0043-03-15"


def test_a_date_inside_a_space_keeps_its_bounds_but_not_its_crm_type():
    from pangloss_dates.calendar import Calendar
    from pangloss_dates.rdf import convert_date
    from pangloss_dates import ExactDate

    view = type("V", (), {})()
    view._owner = ExactDate
    view.year, view.month, view.day, view.calendar = 1500, 3, 1, Calendar.GREGORIAN
    graph = IRI("https://example.org/g")
    uri = IRI("https://example.org/d")
    asserted = list(convert_date(view, uri, Context(graph)))
    hidden = list(
        convert_date(view, uri, Context(graph, (IRI("https://example.org/s"),)))
    )
    assert any("P82a" in q.predicate.value for q in asserted)
    assert any(q.predicate == pgo("earliest") for q in hidden)
    assert not any(
        "cidoc" in str(q.object) or "cidoc" in q.predicate.value for q in hidden
    )
