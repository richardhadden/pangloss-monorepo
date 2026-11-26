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


def test_a_context_is_asserted_from_the_ground_of_its_head():
    from pangloss_models import Document, Ground, SemanticSpace
    from pangloss_models.spaces import registered_grounds, registered_spaces

    class Surely[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    class Charter(Document):
        pass

    class Rumour(Document):
        _meta = Document.Meta(ground=Ground(veridical=0, degree="possible"))

    initialise()
    known, grounds = registered_spaces(), registered_grounds()
    graph = IRI("https://example.org/g")
    space = IRI("https://example.org/s")

    def under(head, *spaces):
        path = (
            {"kind": "document", "type": head, "id": "h", "field": "statements"},
            *({"kind": "space", "type": s, "id": "x", "field": "contents"} for s in spaces),
        )  # fmt: skip
        return Context(graph, (space,) * len(spaces), path, known, grounds).asserted

    assert under("Charter") and under("Charter", "Surely")
    # (a rumour asserts nothing it holds, in a space that asserts or in none)
    assert not under("Rumour") and not under("Rumour", "Surely")
    # (the head itself is asserted whatever its ground; what it holds in a field, by its class's ground)
    charter = Context(graph, known=known, grounds=grounds, head_type="Charter")
    rumour = Context(graph, known=known, grounds=grounds, head_type="Rumour")
    assert charter.asserted and charter.holds("statements")
    assert rumour.asserted and not rumour.holds("statements")
    # (below the head, a node holds as it is)
    below = ({"kind": "document", "type": "Rumour", "id": "h", "field": "statements"},)
    assert not Context(graph, (), below, known, grounds, "Rumour").holds("by")
    # (made by hand with no grounds, as a converter's test may: every head asserts)
    assert Context(graph, known=known, head_type="Rumour").holds("statements")
    path = ({"kind": "document", "type": "Rumour", "id": "h", "field": "statements"},)
    assert Context(graph, (), path, known).asserted


def test_a_context_is_asserted_where_the_walk_over_its_path_says_so():
    from pangloss_models import SemanticSpace
    from pangloss_models.spaces import registered_spaces

    class Sure[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    class Never[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Told[T](SemanticSpace[T]):
        pass

    initialise()
    known = registered_spaces()
    graph = IRI("https://example.org/g")
    space = IRI("https://example.org/s")

    def entry(kind, type):
        return {"kind": kind, "type": type, "id": "x", "field": "contents"}

    def asserted(*path):
        spaces = tuple(space for e in path if e["kind"] == "space")
        return Context(graph, spaces, path, known).asserted

    head = entry("document", "Fact")
    assert Context(graph).asserted
    assert asserted(head)
    assert asserted(head, entry("space", "Sure"))
    assert asserted(head, entry("space", "Never"), entry("space", "Never"))
    assert not asserted(head, entry("space", "Never"))
    assert not asserted(head, entry("space", "Told"))
    assert not asserted(head, entry("space", "Never"), entry("document", "Service"))
    # (made by hand with spaces and no path, as a converter's test may: not asserted, as before the walk)
    assert not Context(graph, (space,)).asserted
