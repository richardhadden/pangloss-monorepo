"""Placing dates in a month.

A date is placed by the range it **states** (the strict bounds), and by what kind of thing it is. A **single** date (an
exact date, a range, an EDTF date) is one day, known as roughly as the date says: a single day is drawn on that day;
one known only within a range is "between these days", drawn across them if the whole range is in the month (`between`),
and only listed (`roughly`) if it reaches beyond the month, so that a birth "in 735" is not drawn on every day of 735. A
**period** (a span of days) is on each of its days: a **narrow** one (`narrow_days` days or fewer) is drawn on each
of them; a wider one is a bar across them (`spanning`). A repeated event is placed on each day it falls on. Dates that
do not reach the month are left out.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

DEFAULT_NARROW_DAYS = 7


@dataclass(frozen=True)
class Dated:
    """What the view needs of a date: whatever `ref` the caller wants back, and the stated range (day numbers)"""

    ref: Any
    earliest_strict: int
    latest_strict: int
    single: bool = False
    """One day somewhere in the range (an exact date, a range, an EDTF date), as against a period over all of it"""

    @property
    def days(self) -> int:
        return self.latest_strict - self.earliest_strict + 1


@dataclass(frozen=True)
class Placement:
    ref: Any
    mark: Literal["stated", "possible"]
    """`stated`: the date says it was on this day (a single day; a day of a period)"""


@dataclass
class MonthView:
    first: int
    last: int
    days: dict[int, list[Placement]] = field(default_factory=dict)
    spanning: list[Dated] = field(default_factory=list)
    """Periods wider than `narrow_days`: a bar across their days"""
    between: list[Dated] = field(default_factory=list)
    """Single dates known only within a range that lies in the month (between these days)"""
    roughly: list[Dated] = field(default_factory=list)
    """Single dates known only within a range that reaches beyond the month: listed, not drawn"""


def _in_order(items: list[Dated]) -> None:
    items.sort(key=lambda d: (d.earliest_strict, d.latest_strict, str(d.ref)))


def place(
    dated: list[Dated], first: int, last: int, narrow_days: int = DEFAULT_NARROW_DAYS
) -> MonthView:
    """The dates that meet the days `first` to `last`: single days and narrow periods on their days, wide periods as
    `spanning`, single dates known within a range as `between` (in the month) or `roughly` (beyond it), nearest start
    first"""
    view = MonthView(first, last, {day: [] for day in range(first, last + 1)})
    for item in dated:
        if item.latest_strict < first or item.earliest_strict > last:
            continue
        if item.single and item.days > 1:
            if item.earliest_strict >= first and item.latest_strict <= last:
                view.between.append(item)
            else:
                view.roughly.append(item)
            continue
        if item.days > narrow_days:
            view.spanning.append(item)
            continue
        for day in range(
            max(item.earliest_strict, first), min(item.latest_strict, last) + 1
        ):
            view.days[day].append(Placement(item.ref, "stated"))
    for items in (view.spanning, view.between, view.roughly):
        _in_order(items)
    return view
