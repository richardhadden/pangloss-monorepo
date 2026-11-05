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
    """The date as it is written to the database (the worked-out fields are only there)"""
    return model.Create(label="x", when=when, **extra)._to_db_model().when


def test_an_exact_date_has_its_bounds_and_sort_day(models):
    _, JulianEvent, _ = models
    when = make(JulianEvent, {"type": "JulianExactDate", "year": 1500, "month": 3})
    assert when.calendar == J and when.precision == Precision.MONTH
    assert ymd(when.earliest_strict) == (1500, 3, 1)
    assert ymd(when.latest_strict) == (1500, 3, 31)
    assert when.earliest_fuzzy == when.earliest_strict
    assert when.sort_day == (when.earliest_strict + when.latest_strict) // 2


def test_what_a_client_sends_for_the_worked_out_fields_is_not_taken(models):
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


def test_the_worked_out_fields_are_only_on_the_models_written_to_the_database(models):
    from pangloss_dates import julian

    worked_out = {
        "precision",
        "earliest_fuzzy",
        "earliest_strict",
        "latest_strict",
        "latest_fuzzy",
        "sort_day",
        "end_sort_day",
    }
    for date in (julian.JulianExactDate, julian.JulianPeriod, julian.JulianRecurrence):
        for kind in ("Create", "Update", "View"):
            assert not worked_out & set(getattr(date, kind).model_fields), (date, kind)
        for kind in ("CreateDB", "UpdateDB"):
            assert worked_out <= set(getattr(date, kind).model_fields), (date, kind)


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
            "not_before": {"type": "JulianExactDate", "year": 1500},
            "not_after": {"type": "JulianExactDate", "year": 1502, "month": 3},
        },
    )
    assert when.precision == Precision.RANGE
    assert ymd(when.earliest_strict) == (1500, 1, 1)
    assert ymd(when.latest_strict) == (1502, 3, 31)
    assert when.not_before.sort_day  # the ends are filled in too


def test_a_range_cannot_end_before_it_starts(models):
    _, JulianEvent, _ = models
    with pytest.raises(ValidationError, match="empty"):
        make(
            JulianEvent,
            {
                "type": "JulianDateRange",
                "not_before": {"type": "JulianExactDate", "year": 1502},
                "not_after": {"type": "JulianExactDate", "year": 1500},
            },
        )


def test_a_range_may_say_only_not_before(models):
    _, JulianEvent, _ = models
    when = make(
        JulianEvent,
        {
            "type": "JulianDateRange",
            "not_before": {"type": "JulianExactDate", "year": 1500, "month": 3},
            "not_after": {"type": "JulianUnknownDate"},
        },
    )
    assert when.precision == Precision.RANGE
    assert ymd(when.earliest_strict) == (1500, 3, 1)
    assert ymd(when.latest_strict) == (1600, 12, 31)  # the horizon
    # (it sorts by what is known of it, not by the middle of 1500 to the horizon)
    assert when.sort_day == to_jdn(1500, 3, 16, J)


def test_a_range_may_say_only_not_after(models):
    _, JulianEvent, _ = models
    when = make(
        JulianEvent,
        {
            "type": "JulianDateRange",
            "not_before": {"type": "JulianUnknownDate"},
            "not_after": {"type": "JulianExactDate", "year": 1502},
        },
    )
    assert ymd(when.latest_strict) == (1502, 12, 31)
    assert when.earliest_strict < to_jdn(1000, 1, 1, J)  # the floor
    assert ymd(when.sort_day) == (1502, 7, 2)
    # (what it says wins)
    said = make(
        JulianEvent,
        {
            "type": "JulianDateRange",
            "sort_by": "latest_strict",
            "not_before": {"type": "JulianUnknownDate"},
            "not_after": {"type": "JulianExactDate", "year": 1502},
        },
    )
    assert ymd(said.sort_day) == (1502, 12, 31)


def test_a_range_cannot_be_unknown_at_both_ends(models):
    _, JulianEvent, _ = models
    with pytest.raises(ValidationError, match="both be unknown"):
        make(
            JulianEvent,
            {
                "type": "JulianDateRange",
                "not_before": {"type": "JulianUnknownDate"},
                "not_after": {"type": "JulianUnknownDate"},
            },
        )


def test_the_ends_of_a_range_are_called_as_in_tei(models):
    Event, _, _ = models
    fields = Event.Create.model_validate(
        {
            "label": "x",
            "when": {
                "type": "DateRange",
                "notBefore": {"type": "ExactDate", "year": 1500},
                "notAfter": {"type": "ExactDate", "year": 1502},
            },
        }
    ).model_dump(by_alias=True)["when"]
    assert set(fields) >= {"notBefore", "notAfter"}
    assert "earliest" not in fields and "latest" not in fields


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
                "not_before": {"type": "JulianExactDate", "year": 1510},
                "not_after": {"type": "JulianExactDate", "year": 1512},
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
    given = {
        "type": "JulianRecurrence",
        "frequency": "weekly",
        "weekdays": [Weekday.SUNDAY],
        "excluded_days": [],
        "start": {"type": "JulianExactDate", "year": 1505, "month": 3, "day": 2},
        "end": {"type": "JulianOngoingDate"},
    }
    # (written to the database only)
    assert not hasattr(JulianEvent.Create(label="x", when=given).when, "pattern_keys")
    when = make(JulianEvent, given)
    assert when.pattern_keys == ["weekday:0"]
    assert when.interval == 1
    assert when.sort_day == to_jdn(1505, 3, 2, J)
    assert ymd(when.earliest_strict) == (1505, 3, 2)


def test_a_recurrence_on_easter_or_a_feast_has_its_key(models):
    _, JulianEvent, _ = models
    for extra, key in (
        ({"easter_offset": 49}, "easter:+49"),
        (
            {"feast": "01a18688-4cf0-73dd-9d9c-a1c659bef751"},
            "feast:01a18688-4cf0-73dd-9d9c-a1c659bef751",
        ),
    ):
        when = make(
            JulianEvent,
            {
                "type": "JulianRecurrence",
                "frequency": "yearly",
                "weekdays": [],
                "excluded_days": [],
                "start": {
                    "type": "JulianExactDate",
                    "year": 1505,
                    "month": 3,
                    "day": 2,
                },
                "end": {"type": "JulianOngoingDate"},
                **extra,
            },
        )
        assert when.pattern_keys == [key]


def test_a_recurrence_with_easter_and_a_month_is_refused(models):
    _, JulianEvent, _ = models
    with pytest.raises(ValidationError, match="Easter"):
        make(
            JulianEvent,
            {
                "type": "JulianRecurrence",
                "frequency": "yearly",
                "weekdays": [],
                "excluded_days": [],
                "month": 3,
                "easter_offset": 1,
                "start": {"type": "JulianExactDate", "year": 1505},
                "end": {"type": "JulianOngoingDate"},
            },
        )


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
                "not_before": {"type": "ExactDate", "year": 1500},
                "not_after": {
                    "type": "ExactDate",
                    "year": 1502,
                    "calendar": "gregorian",
                },
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
    )._to_db_model()
    assert ymd(person.born.sort_day) == (1500, 1, 1)
    assert ymd(person.died.sort_day) == (1500, 7, 1)
    # the date's own say wins
    person = Person.Create(
        label="x",
        born={"type": "JulianExactDate", "year": 1500, "sort_by": "latest_strict"},
        died={"type": "JulianExactDate", "year": 1500},
    )._to_db_model()
    assert ymd(person.born.sort_day) == (1500, 12, 31)
    assert SortDefault  # (the class is the one from the module)
    # the interface is told, to show it as chosen
    from pangloss_models.export import export_models

    fields = {f["name"]: f for f in export_models()["models"]["Person"]["fields"]}
    assert fields["born"]["markers"] == [
        {"name": "SortDefault", "sortBy": "earliest_fuzzy"}
    ]
    assert fields["died"]["markers"] == []


def exact(year, month=None, day=None):
    return {"type": "JulianExactDate", "year": year, "month": month, "day": day}


def lifetime(start, end):
    return {"type": "JulianPeriod", "start": start, "end": end}


UNKNOWN = {"type": "JulianUnknownDate"}


def test_a_period_whose_start_is_not_known_is_open_to_the_floor_and_sorts_by_its_end(
    models,
):
    _, JulianEvent, _ = models
    when = make(JulianEvent, lifetime(UNKNOWN, exact(1510, 3)))
    assert when.precision == Precision.RANGE
    assert ymd(when.earliest_strict) == (1, 1, 1)
    assert ymd(when.latest_strict) == (1510, 3, 31)
    assert when.sort_day == when.end_sort_day
    assert ymd(when.sort_day) == (1510, 3, 16)


def test_a_period_whose_end_is_not_known_is_open_to_the_horizon_and_ends_where_it_starts(
    models,
):
    _, JulianEvent, _ = models
    when = make(JulianEvent, lifetime(exact(1503, 6, 1), UNKNOWN))
    assert ymd(when.earliest_strict) == (1503, 6, 1)
    assert ymd(when.latest_strict) == (1600, 12, 31)
    assert when.sort_day == when.end_sort_day == to_jdn(1503, 6, 1, J)


def test_both_ends_of_a_period_cannot_be_unknown(models):
    _, JulianEvent, _ = models
    with pytest.raises(ValidationError, match="cannot both be unknown"):
        make(JulianEvent, lifetime(UNKNOWN, UNKNOWN))


def test_unknown_is_not_ongoing_and_ongoing_is_still_allowed(models):
    _, JulianEvent, _ = models
    ongoing = make(JulianEvent, lifetime(exact(1503), {"type": "JulianOngoingDate"}))
    unknown = make(JulianEvent, lifetime(exact(1503), UNKNOWN))
    assert ongoing.end.precision == Precision.ONGOING
    assert unknown.end.precision == Precision.UNKNOWN
    with pytest.raises(ValidationError):
        make(JulianEvent, lifetime({"type": "JulianOngoingDate"}, exact(1503)))


def test_a_recurrence_may_start_unknown_but_not_have_no_lifetime(models):
    _, JulianEvent, _ = models
    rule = {
        "type": "JulianRecurrence",
        "frequency": "weekly",
        "weekdays": [0],
        "excluded_days": [],
    }
    when = make(JulianEvent, {**rule, "start": UNKNOWN, "end": exact(1520)})
    assert ymd(when.latest_strict) == (1520, 12, 31)
    with pytest.raises(ValidationError, match="cannot both be unknown"):
        make(JulianEvent, {**rule, "start": UNKNOWN, "end": UNKNOWN})


def test_a_rule_on_a_feast_needs_the_calendar_package_and_the_id_of_a_characterisation(
    models, monkeypatch
):
    import importlib.util

    _, JulianEvent, _ = models

    def feast(value):
        return make(
            JulianEvent,
            {
                "type": "JulianRecurrence",
                "frequency": "yearly",
                "weekdays": [],
                "excluded_days": [],
                "feast": value,
                "start": {"type": "JulianExactDate", "year": 1505},
                "end": {"type": "JulianOngoingDate"},
            },
        )

    assert feast("01a18688-4cf0-73dd-9d9c-a1c659bef751").feast
    with pytest.raises(ValidationError, match="id of a characterisation"):
        feast("sarum:st-benedict")
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a: None if name == "pangloss_calendar" else real(name, *a),
    )
    with pytest.raises(ValidationError, match="needs pangloss-calendar"):
        feast("01a18688-4cf0-73dd-9d9c-a1c659bef751")
