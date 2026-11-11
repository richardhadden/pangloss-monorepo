"""A date in a label (`pangloss_dates.labels.format_date`): the same words as the interface module's `formatDate`, whose
English cases (`interface/src/format.test.ts`) these are"""

import pytest
from pangloss_dates.labels import format_date


def exact(year, month=None, day=None):
    return {
        "type": "ExactDate",
        "calendar": "julian",
        "year": year,
        "month": month,
        "day": day,
    }


def yearly(**rule):
    return {
        "type": "Recurrence",
        "calendar": "gregorian",
        "frequency": "yearly",
        "weekdays": [],
        "start": exact(1450),
        "end": exact(1530),
        **rule,
    }


@pytest.mark.parametrize(
    "date, said",
    [
        (
            {
                "type": "ExactDate",
                "calendar": "gregorian",
                "year": 800,
                "month": 12,
                "day": 25,
            },
            "25 December 800",
        ),
        (
            {
                "type": "ExactDate",
                "calendar": "gregorian",
                "year": 800,
                "month": 12,
                "day": None,
            },
            "December 800",
        ),
        ({"type": "ExactDate", "calendar": "gregorian", "year": 800}, "800"),
        (exact(1500, 3, 2), "2 March 1500 (julian)"),
        (
            {
                "type": "DateRange",
                "calendar": "julian",
                "notBefore": exact(1500),
                "notAfter": exact(1502),
            },
            "1500 to 1502 (julian)",
        ),
        (
            {
                "type": "Period",
                "calendar": "gregorian",
                "start": exact(1500),
                "end": {"type": "OngoingDate"},
            },
            "1500 – ongoing",
        ),
        (
            {
                "type": "Period",
                "calendar": "gregorian",
                "start": exact(1500),
                "end": {"type": "UnknownDate"},
            },
            "1500 – unknown",
        ),
        (
            {
                "type": "EDTFDate",
                "calendar": "gregorian",
                "edtf": "075X",
                "sourceText": "8th century",
            },
            "075X “8th century”",
        ),
        (
            {
                "type": "Recurrence",
                "calendar": "gregorian",
                "frequency": "weekly",
                "weekdays": [0],
                "start": exact(1500),
                "end": {"type": "OngoingDate"},
            },
            "every week on Sunday, 1500 – ongoing",
        ),
        (yearly(month=3, monthDay=21), "every year on 21 March, 1450 – 1530"),
        (
            yearly(month=3, nth=3, weekdays=[0]),
            "every year on the third Sunday of March, 1450 – 1530",
        ),
        (
            yearly(month=3, nth=-1, weekdays=[5], interval=2),
            "every 2 years on the last Friday of March, 1450 – 1530",
        ),
        (yearly(easterOffset=49), "every year on Easter + 49 days, 1450 – 1530"),
        (yearly(easterOffset=0), "every year on Easter, 1450 – 1530"),
        (
            yearly(frequency="monthly", monthDay=21),
            "every month on the 21., 1450 – 1530",
        ),
        (
            {
                "type": "DateRange",
                "calendar": "gregorian",
                "notBefore": exact(1500),
                "notAfter": {"type": "UnknownDate"},
            },
            "not before 1500",
        ),
        ({"type": "Person"}, None),
        (None, None),
    ],
)
def test_a_date_is_said_as_the_interface_says_it(date, said):
    assert format_date(date) == said
