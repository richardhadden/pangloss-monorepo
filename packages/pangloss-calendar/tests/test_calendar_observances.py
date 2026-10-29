"""The observance file, and the day a feast falls on"""

import pytest
from pangloss_calendar.observances import (
    InvalidObservance,
    Observance,
    falls_on,
    feast_keys,
    observances_on,
    parse,
)
from pangloss_dates.calendar import (
    Calendar,
    Weekday,
    from_jdn,
    is_leap_year,
    to_jdn,
    weekday,
)
from pangloss_dates.easter import easter

J = Calendar.JULIAN
G = Calendar.GREGORIAN

EXAMPLE = """
[[observance]]
key = "sarum:st-benedict"
use = "sarum"
name = { en = "Benedict", la = "Benedicti abbatis" }
rank = "major"
fixed = { month = 3, day = 21 }

[[observance]]
key = "sarum:pentecost"
use = "sarum"
easter_offset = 49

[[observance]]
key = "sarum:st-matthias"
use = "sarum"
fixed = { month = 2, day = 24 }
leap_shift = true

[[observance]]
key = "roman:st-benedict"
use = "roman"
fixed = { month = 7, day = 11 }
"""


def test_the_example_file_is_read():
    found = parse(EXAMPLE)
    assert [o.key for o in found] == [
        "sarum:st-benedict",
        "sarum:pentecost",
        "sarum:st-matthias",
        "roman:st-benedict",
    ]
    assert found[0].name == {"en": "Benedict", "la": "Benedicti abbatis"}
    assert found[0].fixed == (3, 21) and found[0].rank == "major"
    assert found[1].easter_offset == 49 and found[1].fixed is None


@pytest.mark.parametrize(
    "body,message",
    [
        ('key = "a"\nuse = "x"\nfixed = { month = 2, day = 30 }', "30"),
        ('key = "a"\nuse = "x"\nfixed = { month = 13, day = 1 }', "month"),
        ('key = "a"\nuse = "x"', "either fixed"),
        (
            'key = "a"\nuse = "x"\nfixed = { month = 3, day = 1 }\neaster_offset = 1',
            "either fixed",
        ),
        ('key = "a"\nuse = "x"\neaster_offset = 300', "easter_offset"),
        (
            'key = "a"\nuse = "x"\nfixed = { month = 3, day = 1 }\nleap_shift = true',
            "leap_shift",
        ),
        (
            'key = "a"\nuse = "x"\nfixed = { month = 3, day = 1 }\ncolour = "red"',
            "unknown",
        ),
        ('key = "a"\nfixed = { month = 3, day = 1 }', "use"),
        ('use = "x"\nfixed = { month = 3, day = 1 }', "key"),
        ('key = "a"\nuse = "x"\nfixed = { month = 3 }', "fixed"),
    ],
)
def test_an_impossible_observance_is_refused(body, message):
    with pytest.raises(InvalidObservance, match=message):
        parse(f"[[observance]]\n{body}\n")


def test_a_key_used_twice_and_bad_toml_are_refused():
    one = '[[observance]]\nkey = "a"\nuse = "x"\nfixed = { month = 3, day = 1 }\n'
    with pytest.raises(InvalidObservance, match="twice"):
        parse(one + one)
    with pytest.raises(InvalidObservance, match="TOML"):
        parse("[[observance")
    with pytest.raises(InvalidObservance, match="top-level"):
        parse("colour = 1")
    assert parse("") == []


def test_a_fixed_feast_is_on_that_date_in_the_calendar_asked():
    benedict = parse(EXAMPLE)[0]
    day = falls_on(benedict, 1500, J)
    assert tuple(from_jdn(day, J)) == (1500, 3, 21)
    assert tuple(from_jdn(falls_on(benedict, 1500, G), G)) == (1500, 3, 21)
    assert falls_on(benedict, 1500, J) != falls_on(benedict, 1500, G)


def test_a_moveable_feast_is_easter_plus_its_offset_in_the_calendar_asked():
    pentecost = parse(EXAMPLE)[1]
    for calendar in (J, G):
        for year in range(1450, 1531):
            day = falls_on(pentecost, year, calendar)
            assert day == easter(year, calendar) + 49
            assert weekday(day) == Weekday.SUNDAY


def test_the_leap_day_moves_a_feast_of_24_to_28_february_only_in_a_leap_year():
    matthias = parse(EXAMPLE)[2]
    assert tuple(from_jdn(falls_on(matthias, 1500, J), J)) == (1500, 2, 25)
    assert tuple(from_jdn(falls_on(matthias, 1501, J), J)) == (1501, 2, 24)
    assert is_leap_year(1500, J) and not is_leap_year(1500, G)
    assert tuple(from_jdn(falls_on(matthias, 1500, G), G)) == (1500, 2, 24)
    plain = Observance("b", "x", fixed=(2, 24))
    assert tuple(from_jdn(falls_on(plain, 1500, J), J)) == (1500, 2, 24)


def test_a_feast_on_29_february_is_absent_in_other_years():
    leap_feast = Observance("leap", "x", fixed=(2, 29))
    assert falls_on(leap_feast, 1500, J) == to_jdn(1500, 2, 29, J)
    assert falls_on(leap_feast, 1501, J) is None
    assert falls_on(leap_feast, 1500, G) is None


def test_what_falls_on_a_day_can_be_limited_to_a_use():
    found = parse(EXAMPLE)
    day = to_jdn(1500, 3, 21, J)
    assert [o.key for o in observances_on(found, day, J)] == ["sarum:st-benedict"]
    assert observances_on(found, day, J, use="roman") == []
    assert observances_on(found, day + 1, J) == []
    assert feast_keys(found, day, J, use="sarum") == ["feast:sarum:st-benedict"]
    # the same day under its Gregorian name is the 31st of March: the feast is not "on 21 March" there
    assert observances_on(found, day, G) == []


def test_every_fixed_feast_is_a_real_day_in_both_calendars():
    for month in range(1, 13):
        for day in range(1, 29):
            o = Observance(f"{month}-{day}", "x", fixed=(month, day))
            for calendar in (J, G):
                for year in (1499, 1500, 1501):
                    assert tuple(from_jdn(falls_on(o, year, calendar), calendar)) == (
                        year,
                        month,
                        day,
                    )
