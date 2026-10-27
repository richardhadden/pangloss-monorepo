"""The date types as models: the bounds are worked out when a document is written"""

import pytest
from pangloss_dates.bounds import Precision
from pangloss_dates.calendar import Calendar, Weekday, from_jdn, to_jdn
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pydantic import ValidationError

J, G = Calendar.JULIAN, Calendar.GREGORIAN


def ymd(jdn, calendar=J):
    return tuple(from_jdn(jdn, calendar))


@pytest.fixture
def models():
    # (the registry is emptied before each test, so the modules make their classes again)
    import importlib

    from pangloss_dates import gregorian, julian, models

    for module in (models, julian, gregorian):
        importlib.reload(module)

    class Event(Document):
        when: models.Date

    class JulianEvent(Document):
        when: julian.JulianDate

    class GregorianEvent(Document):
        when: gregorian.GregorianDate

    initialise()
    return Event, JulianEvent, GregorianEvent


def make(model, when, **extra):
    return model.Create(label="x", when=when, **extra).when


def test_an_exact_date_has_its_bounds_and_sort_day(models):
    _, JulianEvent, _ = models
    when = make(JulianEvent, {"type": "JulianExactDate", "year": 1500, "month": 3})
    assert when.calendar == J and when.precision == Precision.MONTH
    assert ymd(when.earliest_strict) == (1500, 3, 1)
    assert ymd(when.latest_strict) == (1500, 3, 31)
    assert when.earliest_fuzzy == when.earliest_strict
    assert when.sort_day == (when.earliest_strict + when.latest_strict) // 2


def test_what_a_client_sends_for_the_worked_out_fields_is_overwritten(models):
    _, JulianEvent, _ = models
    when = make(
        JulianEvent,
        {
            "type": "JulianExactDate",
            "year": 1500,
            "month": 3,
            "day": 2,
            "sort_day": 5,
            "earliest_strict": 1,
        },
    )
    assert when.sort_day == when.earliest_strict == to_jdn(1500, 3, 2, J)


def test_a_day_that_does_not_exist_is_refused(models):
    _, JulianEvent, _ = models
    JulianEvent.Create(
        label="x", when={"type": "JulianExactDate", "year": 1500, "month": 2, "day": 29}
    )
    with pytest.raises(ValidationError, match="does not exist"):
        JulianEvent.Create(
            label="x",
            when={"type": "JulianExactDate", "year": 1501, "month": 2, "day": 29},
        )


def test_sort_by_chooses_the_day_to_order_by(models):
    _, JulianEvent, _ = models
    when = make(
        JulianEvent,
        {"type": "JulianExactDate", "year": 1500, "sort_by": "earliest_strict"},
    )
    assert ymd(when.sort_day) == (1500, 1, 1)
    when = make(
        JulianEvent,
        {"type": "JulianExactDate", "year": 1500, "sort_by": "latest_strict"},
    )
    assert ymd(when.sort_day) == (1500, 12, 31)


def test_a_range_embeds_two_exact_dates(models):
    _, JulianEvent, _ = models
    when = make(
        JulianEvent,
        {
            "type": "JulianDateRange",
            "earliest": {"type": "JulianExactDate", "year": 1500},
            "latest": {"type": "JulianExactDate", "year": 1502, "month": 3},
        },
    )
    assert when.precision == Precision.RANGE
    assert ymd(when.earliest_strict) == (1500, 1, 1)
    assert ymd(when.latest_strict) == (1502, 3, 31)
    assert when.earliest.sort_day  # the ends are filled in too


def test_a_range_cannot_end_before_it_starts(models):
    _, JulianEvent, _ = models
    with pytest.raises(ValidationError, match="empty"):
        make(
            JulianEvent,
            {
                "type": "JulianDateRange",
                "earliest": {"type": "JulianExactDate", "year": 1502},
                "latest": {"type": "JulianExactDate", "year": 1500},
            },
        )


def test_edtf_dates_use_the_calendar_of_the_date(models):
    _, JulianEvent, GregorianEvent = models
    julian = make(JulianEvent, {"type": "JulianEDTFDate", "edtf": "1500-02"})
    assert ymd(julian.latest_strict) == (1500, 2, 29)
    gregorian = make(GregorianEvent, {"type": "GregorianEDTFDate", "edtf": "1500-02"})
    assert ymd(gregorian.latest_strict, G) == (1500, 2, 28)
    approximate = make(JulianEvent, {"type": "JulianEDTFDate", "edtf": "1500~"})
    assert approximate.earliest_fuzzy < approximate.earliest_strict
    with pytest.raises(ValidationError, match="not EDTF"):
        make(JulianEvent, {"type": "JulianEDTFDate", "edtf": "nonsense"})


def test_a_period_sorts_by_its_start_and_an_open_end_stops_at_the_horizon(models):
    _, JulianEvent, _ = models
    when = make(
        JulianEvent,
        {
            "type": "JulianPeriod",
            "start": {"type": "JulianExactDate", "year": 1500, "month": 3, "day": 2},
            "end": {"type": "JulianOngoingDate"},
        },
    )
    assert when.sort_day == to_jdn(1500, 3, 2, J)
    assert ymd(when.latest_strict) == (1600, 12, 31)
    assert when.end_sort_day == when.latest_strict
    closed = make(
        JulianEvent,
        {
            "type": "JulianPeriod",
            "start": {"type": "JulianExactDate", "year": 1500},
            "end": {
                "type": "JulianDateRange",
                "earliest": {"type": "JulianExactDate", "year": 1510},
                "latest": {"type": "JulianExactDate", "year": 1512},
            },
        },
    )
    assert ymd(closed.latest_strict) == (1512, 12, 31)
    assert closed.end_sort_day < closed.latest_strict


def test_a_period_cannot_start_ongoing(models):
    _, JulianEvent, _ = models
    with pytest.raises(ValidationError):
        make(
            JulianEvent,
            {
                "type": "JulianPeriod",
                "start": {"type": "JulianOngoingDate"},
                "end": {"type": "JulianExactDate", "year": 1500},
            },
        )


def test_a_recurrence_has_its_pattern_keys_and_a_lifetime(models):
    _, JulianEvent, _ = models
    when = make(
        JulianEvent,
        {
            "type": "JulianRecurrence",
            "frequency": "weekly",
            "weekdays": [Weekday.SUNDAY],
            "excluded_days": [],
            "start": {"type": "JulianExactDate", "year": 1505, "month": 3, "day": 2},
            "end": {"type": "JulianOngoingDate"},
        },
    )
    assert not hasattr(when, "pattern_keys")  # (written to the database only)
    db = JulianEvent.CreateDB.model_validate(
        JulianEvent.Create(label="x", when=when).model_dump(by_alias=False)
    )
    assert db.when.pattern_keys == ["weekday:0"]
    assert when.interval == 1
    assert when.sort_day == to_jdn(1505, 3, 2, J)
    assert ymd(when.earliest_strict) == (1505, 3, 2)


def test_a_rule_that_says_no_day_is_refused(models):
    _, JulianEvent, _ = models
    with pytest.raises(ValidationError, match="weekday"):
        make(
            JulianEvent,
            {
                "type": "JulianRecurrence",
                "frequency": "weekly",
                "weekdays": [],
                "excluded_days": [],
                "start": {"type": "JulianExactDate", "year": 1505},
                "end": {"type": "JulianOngoingDate"},
            },
        )


def test_a_julian_date_cannot_be_given_the_other_calendar(models):
    _, JulianEvent, _ = models
    with pytest.raises(ValidationError, match="julian calendar"):
        make(
            JulianEvent,
            {"type": "JulianExactDate", "year": 1500, "calendar": "gregorian"},
        )


def test_the_plain_types_take_the_calendar_they_say_or_the_projects_default(models):
    Event, _, _ = models
    plain = make(Event, {"type": "ExactDate", "year": 1500, "month": 2})
    assert plain.calendar == G  # (the default)
    said = make(
        Event, {"type": "ExactDate", "year": 1500, "month": 2, "calendar": "julian"}
    )
    assert said.calendar == J and ymd(said.latest_strict) == (1500, 2, 29)


def test_the_base_class_is_not_a_date_to_use_on_its_own(models):
    Event, _, _ = models
    with pytest.raises(ValidationError):
        make(Event, {"type": "Date"})


def test_a_range_cannot_mix_calendars(models):
    Event, _, _ = models
    with pytest.raises(ValidationError, match="calendar"):
        make(
            Event,
            {
                "type": "DateRange",
                "calendar": "julian",
                "earliest": {"type": "ExactDate", "year": 1500},
                "latest": {"type": "ExactDate", "year": 1502, "calendar": "gregorian"},
            },
        )


def test_a_field_can_say_what_its_dates_sort_by():
    import importlib
    from typing import Annotated

    from pangloss_dates import julian, models
    from pangloss_dates.bounds import SortBy
    from pangloss_dates.models import SortDefault

    for module in (models, julian):
        importlib.reload(module)
    Default = models.SortDefault

    class Person(Document):
        born: Annotated[julian.JulianExactDate, Default(SortBy.EARLIEST_FUZZY)]
        died: julian.JulianExactDate

    initialise()
    person = Person.Create(
        label="x",
        born={"type": "JulianExactDate", "year": 1500},
        died={"type": "JulianExactDate", "year": 1500},
    )
    assert ymd(person.born.sort_day) == (1500, 1, 1)
    assert ymd(person.died.sort_day) == (1500, 7, 1)
    # the date's own say wins
    person = Person.Create(
        label="x",
        born={"type": "JulianExactDate", "year": 1500, "sort_by": "latest_strict"},
        died={"type": "JulianExactDate", "year": 1500},
    )
    assert ymd(person.born.sort_day) == (1500, 12, 31)
    assert SortDefault  # (the class is the one from the module)
