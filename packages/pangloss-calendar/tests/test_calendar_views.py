"""Narrow dates on their days, wide ones apart"""

from pangloss_calendar.views import Dated, place
from pangloss_dates.calendar import Calendar, to_jdn

J = Calendar.JULIAN
FIRST = to_jdn(1500, 3, 1, J)
LAST = to_jdn(1500, 3, 31, J)


def dated(ref, first_day, last_day=None, month=3):
    return Dated(
        ref,
        to_jdn(1500, month, first_day, J),
        to_jdn(1500, month, last_day or first_day, J),
    )


def test_an_exact_day_is_stated_on_that_day():
    view = place([dated("a", 2)], FIRST, LAST)
    assert [p.mark for p in view.days[to_jdn(1500, 3, 2, J)]] == ["stated"]
    assert sum(len(v) for v in view.days.values()) == 1
    assert view.spanning == []


def test_a_period_of_2_to_4_march_is_stated_on_each_of_three_days():
    view = place([dated("a", 2, 4)], FIRST, LAST)
    for d in (2, 3, 4):
        assert [p.mark for p in view.days[to_jdn(1500, 3, d, J)]] == ["stated"]
    assert sum(len(v) for v in view.days.values()) == 3


def test_a_single_date_known_within_the_month_is_between_its_days_and_not_on_them():
    view = place(
        [Dated("a", to_jdn(1500, 3, 2, J), to_jdn(1500, 3, 4, J), single=True)],
        FIRST,
        LAST,
    )
    assert sum(len(v) for v in view.days.values()) == 0
    assert (
        [d.ref for d in view.between] == ["a"]
        and view.roughly == []
        and view.spanning == []
    )


def test_a_single_date_known_only_beyond_the_month_is_listed_roughly():
    born = Dated("born", to_jdn(1500, 1, 1, J), to_jdn(1500, 12, 31, J), single=True)
    sometime = Dated(
        "sometime", to_jdn(1500, 3, 20, J), to_jdn(1500, 4, 2, J), single=True
    )
    view = place([born, sometime], FIRST, LAST)
    assert [d.ref for d in view.roughly] == ["born", "sometime"]
    assert view.between == [] and view.spanning == []
    assert sum(len(v) for v in view.days.values()) == 0
    # (a single day is still on its day, whatever its kind)
    one = place(
        [Dated("one", to_jdn(1500, 3, 2, J), to_jdn(1500, 3, 2, J), single=True)],
        FIRST,
        LAST,
    )
    assert [p.mark for p in one.days[to_jdn(1500, 3, 2, J)]] == ["stated"]


def test_a_range_of_exactly_the_limit_is_narrow_and_one_more_is_wide():
    seven = place([dated("a", 1, 7)], FIRST, LAST)
    assert len(seven.spanning) == 0 and sum(len(v) for v in seven.days.values()) == 7
    eight = place([dated("a", 1, 8)], FIRST, LAST)
    assert [d.ref for d in eight.spanning] == ["a"] and sum(
        len(v) for v in eight.days.values()
    ) == 0


def test_the_limit_is_a_setting_of_the_call():
    assert place([dated("a", 2, 4)], FIRST, LAST, narrow_days=1).spanning
    assert not place([dated("a", 2)], FIRST, LAST, narrow_days=1).spanning


def test_a_whole_month_or_year_is_in_the_spanning_list_in_order():
    year = Dated("year", to_jdn(1500, 1, 1, J), to_jdn(1500, 12, 31, J))
    month = Dated("month", FIRST, LAST)
    view = place([month, year], FIRST, LAST)
    assert [d.ref for d in view.spanning] == ["year", "month"]


def test_dates_that_do_not_reach_the_month_are_left_out():
    view = place(
        [dated("feb", 27, 28, month=2), dated("apr", 1, 1, month=4)], FIRST, LAST
    )
    assert sum(len(v) for v in view.days.values()) == 0 and view.spanning == []


def test_a_narrow_range_across_the_edge_of_the_month_is_placed_on_the_days_in_it():
    across = Dated("x", to_jdn(1500, 2, 28, J), to_jdn(1500, 3, 2, J))
    view = place([across], FIRST, LAST)
    assert [d - FIRST for d, v in view.days.items() if v] == [0, 1]


def test_a_wide_range_that_only_touches_the_month_is_still_listed():
    wide = Dated("x", to_jdn(1499, 1, 1, J), FIRST)
    assert [d.ref for d in place([wide], FIRST, LAST).spanning] == ["x"]


def test_dates_are_counted_in_every_year_they_reach():
    from types import SimpleNamespace

    from pangloss_calendar.service import count_by_year
    from pangloss_dates.calendar import Calendar, to_jdn

    J = Calendar.JULIAN
    ref = lambda n: SimpleNamespace(id=n, field="when")  # noqa: E731
    dated = [
        Dated(ref(1), to_jdn(1500, 3, 2, J), to_jdn(1500, 3, 2, J)),
        # (a range over the turn of the year is in both years)
        Dated(ref(2), to_jdn(1500, 12, 30, J), to_jdn(1501, 1, 2, J)),
        # (a long period: in every year it reaches, cut at the span)
        Dated(ref(3), to_jdn(1400, 1, 1, J), to_jdn(1600, 1, 1, J)),
        # (the same date in the same field twice is one; before the span: not counted)
        Dated(ref(1), to_jdn(1500, 3, 2, J), to_jdn(1500, 3, 2, J)),
        Dated(ref(4), to_jdn(1498, 1, 1, J), to_jdn(1498, 12, 31, J)),
    ]
    assert count_by_year(dated, J, 1499, 1502) == [1, 3, 2, 1]
