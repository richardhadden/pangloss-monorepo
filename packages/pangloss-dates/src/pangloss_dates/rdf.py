"""What `pangloss_rdf` writes for a date, beyond its fields: its bounds as dates. Found by name; only imported by that package.

The bounds are day numbers, given here in the proleptic Gregorian calendar, as `xsd:date` is, whatever calendar the date
is in (its fields say that, and what the source said). A date with no known end has none."""

from collections.abc import Iterator
from typing import Any

from pangloss_rdf import IRI, Lit, Quad, register_rdf_converter
from pangloss_rdf.context import Context
from pangloss_rdf.ontologies.crm import (
    E52_Time_Span,
    P82a_begin_of_the_begin,
    P82b_end_of_the_end,
)
from pangloss_rdf.terms import xsd
from pangloss_rdf.vocabulary import RDF_TYPE, pgo

from pangloss_dates.calendar import Calendar, from_jdn
from pangloss_dates.models import Date, OngoingDate, Period, Recurrence, UnknownDate


def as_xsd_date(day: int) -> Lit:
    year, month, date = from_jdn(day, Calendar.GREGORIAN)
    sign = "-" if year < 0 else ""
    return Lit(f"{sign}{abs(year):04d}-{month:02d}-{date:02d}", xsd("date"))


def _end_is_known(value: Any) -> bool:
    end = getattr(value, "end", None)
    return end is None or not issubclass(end._owner, OngoingDate)


def convert_date(value: Any, uri: IRI, context: Context) -> Iterator[Quad]:
    owner = value._owner
    if issubclass(owner, (UnknownDate, OngoingDate, Recurrence)):
        return
    # (a view has not the bounds kept in the database: the date says them again)
    bounds, _ = owner.work_out(value)
    known_end = not issubclass(owner, Period) or _end_is_known(value)
    yield context.quad(uri, pgo("earliest"), as_xsd_date(bounds.earliest_fuzzy))
    yield context.quad(uri, pgo("earliestStrict"), as_xsd_date(bounds.earliest_strict))
    if known_end:
        yield context.quad(uri, pgo("latestStrict"), as_xsd_date(bounds.latest_strict))
        yield context.quad(uri, pgo("latest"), as_xsd_date(bounds.latest_fuzzy))
    if context.asserted:
        yield context.quad(uri, RDF_TYPE, IRI(E52_Time_Span._rdf_uri))
        yield context.quad(
            uri, IRI(P82a_begin_of_the_begin.uri), as_xsd_date(bounds.earliest_fuzzy)
        )
        if known_end:
            yield context.quad(
                uri, IRI(P82b_end_of_the_end.uri), as_xsd_date(bounds.latest_fuzzy)
            )


register_rdf_converter(Date, convert_date)
