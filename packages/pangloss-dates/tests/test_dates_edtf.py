"""EDTF read into bounds in the chosen calendar (python-edtf only parses)"""

import pytest

pytest.importorskip("edtf")

from pangloss_dates.bounds import Padding, Precision, exact_bounds
from pangloss_dates.calendar import Calendar, from_jdn, to_jdn
from pangloss_dates.edtf import (
    EdtfError,
    EdtfNotADate,
    EdtfUnsupported,
    parse_edtf_date,
    parse_edtf_interval,
)

J = Calendar.JULIAN
G = Calendar.GREGORIAN


def ymd(jdn, calendar=J):
    return tuple(from_jdn(jdn, calendar))


def span(result, calendar=J):
    b = result.bounds
    return (
        ymd(b.earliest_fuzzy, calendar),
        ymd(b.earliest_strict, calendar),
        ymd(b.latest_strict, calendar),
        ymd(b.latest_fuzzy, calendar),
    )


def test_a_year_a_month_a_day():
    year = parse_edtf_date("1500", J)
    assert year.precision == Precision.YEAR
    assert year.bounds == exact_bounds(1500, None, None, J)
    assert parse_edtf_date("1500-03", J).precision == Precision.MONTH
    day = parse_edtf_date("1500-03-02", J)
    assert day.precision == Precision.DAY
    assert day.bounds.earliest_strict == to_jdn(1500, 3, 2, J)
    assert not day.uncertain and not day.approximate


def test_the_month_ends_in_the_calendar_of_the_date_not_the_gregorian_one():
    """python-edtf says February 1500 ends on the 28th; in the Julian calendar it ends on the 29th"""
    assert ymd(parse_edtf_date("1500-02", J).bounds.latest_strict) == (1500, 2, 29)
    assert ymd(parse_edtf_date("1500-02", G).bounds.latest_strict, G) == (1500, 2, 28)


def test_29_february_1500_exists_only_in_the_julian_calendar():
    parse_edtf_date("1500-02-29", J)
    with pytest.raises(EdtfError):
        parse_edtf_date("1500-02-29", G)


def test_approximate_uncertain_and_both():
    approximate = parse_edtf_date("1500~", J)
    assert approximate.approximate and not approximate.uncertain
    assert span(approximate) == (
        (1499, 1, 1),
        (1500, 1, 1),
        (1500, 12, 31),
        (1501, 12, 31),
    )
    uncertain = parse_edtf_date("1500-03?", J)
    assert uncertain.uncertain and not uncertain.approximate
    assert span(uncertain)[0] == (1500, 2, 1)
    both = parse_edtf_date("1500-03-02%", J)
    assert both.uncertain and both.approximate
    assert span(both) == (
        (1500, 2, 24),
        (1500, 3, 2),
        (1500, 3, 2),
        (1500, 3, 9),
    )


def test_the_padding_is_ours_not_the_library():
    wide = parse_edtf_date("1500~", J, Padding(year=10))
    assert ymd(wide.bounds.earliest_fuzzy) == (1490, 1, 1)


def test_a_qualifier_on_part_of_a_date_qualifies_the_whole_date():
    result = parse_edtf_date("2004-06-~11", J)
    assert result.approximate and result.precision == Precision.DAY
    assert parse_edtf_date("?1500", J).uncertain


def test_unspecified_digits_leave_a_span():
    decade = parse_edtf_date("150X", J)
    assert span(decade)[1:3] == ((1500, 1, 1), (1509, 12, 31))
    assert decade.precision == Precision.RANGE
    century = parse_edtf_date("15XX", J)
    assert span(century)[1:3] == ((1500, 1, 1), (1599, 12, 31))
    assert century.bounds.earliest_fuzzy == century.bounds.earliest_strict
    assert parse_edtf_date("1500-XX", J).bounds == exact_bounds(1500, None, None, J)
    assert parse_edtf_date("1500-XX-XX", J).bounds == exact_bounds(1500, None, None, J)
    assert parse_edtf_date("1500-03-XX", J).bounds == exact_bounds(1500, 3, None, J)


def test_a_set_runs_from_the_earliest_member_to_the_latest():
    one_of = parse_edtf_date("[1500,1502-03]", J)
    assert span(one_of)[1:3] == ((1500, 1, 1), (1502, 3, 31))
    assert parse_edtf_date("{1500,1504}", J).bounds.latest_strict == to_jdn(
        1504, 12, 31, J
    )
    mixed = parse_edtf_date("[1500~,1502]", J)
    assert mixed.approximate
    assert ymd(mixed.bounds.earliest_fuzzy) == (1499, 1, 1)
    assert ymd(mixed.bounds.earliest_strict) == (1500, 1, 1)


def test_an_interval_is_a_period():
    start, end = parse_edtf_interval("1500-03/1500-05", J)
    assert start.bounds == exact_bounds(1500, 3, None, J)
    assert end.bounds == exact_bounds(1500, 5, None, J)
    with pytest.raises(EdtfNotADate):
        parse_edtf_date("1500-03/1500-05", J)
    with pytest.raises(EdtfNotADate):
        parse_edtf_interval("1500", J)


def test_open_and_unknown_ends_of_an_interval_are_none():
    start, end = parse_edtf_interval("1500/..", J)
    assert start is not None and end is None
    start, end = parse_edtf_interval("../1500", J)
    assert start is None and end is not None
    start, end = parse_edtf_interval("1500/", J)
    assert start is not None and end is None


def test_each_end_of_an_interval_has_its_own_qualifier():
    start, end = parse_edtf_interval("1500~/1510?", J)
    assert start.approximate and not start.uncertain
    assert end.uncertain and not end.approximate


@pytest.mark.parametrize(
    "text, error",
    [
        ("1500-21", EdtfUnsupported),
        ("1950S2", EdtfUnsupported),
        ("Y170000002", EdtfUnsupported),
        ("1500-03-02T10:00:00", EdtfUnsupported),
        ("[..1500]", EdtfUnsupported),
        ("1500-03-XX~", EdtfUnsupported),
        ("not a date", EdtfError),
        ("1500-13", EdtfError),
        ("1450-02-30", EdtfError),
        ("", EdtfError),
    ],
)
def test_what_is_not_read_says_so(text, error):
    with pytest.raises(error):
        parse_edtf_date(text, J)
