"""Placing dates in a month.

A date is placed by the range it **states** (the strict bounds). If that range is **narrow** (`narrow_days` days or
fewer) the date is drawn on each day of it: `stated` if it is a single day, `possible` if it is a range of days
(the event was on one of them). A **wide** range ("March 1500", "1500") is not drawn on every day, which would put
one entry on thirty or three hundred days and say something false; it goes in the `spanning` list with its range.
Dates that do not reach the month are left out.
"""

from dataclasses import dataclass, field
from typing import Any

DEFAULT_NARROW_DAYS = 7


@dataclass(frozen=True)
class Dated:
    """What the view needs of a date: whatever `ref` the caller wants back, and the stated range (day numbers)"""

    ref: Any
    earliest_strict: int
    latest_strict: int

    @property
    def days(self) -> int:
        return self.latest_strict - self.earliest_strict + 1


@dataclass(frozen=True)
class Placement:
    ref: Any
    mark: str
    """`stated` (a single day) or `possible` (one of the days of a range)"""


@dataclass
class MonthView:
    first: int
    last: int
    days: dict[int, list[Placement]] = field(default_factory=dict)
    spanning: list[Dated] = field(default_factory=list)


def place(
    dated: list[Dated], first: int, last: int, narrow_days: int = DEFAULT_NARROW_DAYS
) -> MonthView:
    """The dates that meet the days `first` to `last`, narrow ones on their days, wide ones apart (nearest start first)"""
    view = MonthView(first, last, {day: [] for day in range(first, last + 1)})
    for item in dated:
        if item.latest_strict < first or item.earliest_strict > last:
            continue
        if item.days > narrow_days:
            view.spanning.append(item)
            continue
        mark = "stated" if item.days == 1 else "possible"
        for day in range(
            max(item.earliest_strict, first), min(item.latest_strict, last) + 1
        ):
            view.days[day].append(Placement(item.ref, mark))
    view.spanning.sort(key=lambda d: (d.earliest_strict, d.latest_strict, str(d.ref)))
    return view
