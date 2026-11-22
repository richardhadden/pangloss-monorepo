"""What the tests of the time part on the planted world share (`pangloss_testing.planted`, `dated=True`): the
bounds of a planted date, and how well vectors find an event's other reports"""

from typing import Any

import numpy as np
from pangloss_dates.bounds import exact_bounds
from pangloss_dates.calendar import Calendar
from pangloss_dates_vectors import maths


def bounds_of(date: dict[str, Any]) -> maths.Bounds:
    """The bounds of a planted date (an `ExactDate`, or a `DateRange` of two), as `pangloss_dates` works them out"""
    if date["type"] == "DateRange":
        return (
            *bounds_of(date["not_before"])[:2],
            *bounds_of(date["not_after"])[2:],
        )
    found = exact_bounds(
        date["year"], date.get("month"), date.get("day"), Calendar.GREGORIAN
    )
    return (
        found.earliest_fuzzy,
        found.earliest_strict,
        found.latest_strict,
        found.latest_fuzzy,
    )


def time_vectors(world, labels: list[str], ring: maths.Ring) -> np.ndarray:
    """The time vector of each of the factoids, by its label: a row for each"""
    return maths.vectors([bounds_of(world.dates[label]) for label in labels], ring)


def series_of(world) -> dict[str, str]:
    """The series of each report of something that happened year after year, by the report's label"""
    return {
        label: name
        for name, events in world.series.items()
        for event in events
        for label in world.events[event]
    }


def other_reports(world) -> dict[str, list[str]]:
    """For each factoid that reports an event another reports too: the labels of the others"""
    return {
        label: [other for other in labels if other != label]
        for labels in world.events.values()
        for label in labels
    }


def found_among(
    world, labels: list[str], scores, most: int, only: set[str] | None = None
) -> float:
    """The share of the other reports of an event that are among the `most` nearest of a report, by `scores` (a
    function of a range of rows that gives their likeness to every row: `labels` name the rows). Of the reports
    `only`, if given. Those as near as the other report are counted before it (the worst case)"""
    row = {label: n for n, label in enumerate(labels)}
    others = other_reports(world)
    asked = [label for label in others if only is None or label in only]
    hits = wanted = 0
    for start in range(0, len(asked), 500):
        chunk = asked[start : start + 500]
        likeness = np.array(scores([row[label] for label in chunk]))
        for n, label in enumerate(chunk):
            likeness[n, row[label]] = -np.inf
            for other in others[label]:
                right = likeness[n, row[other]]
                wanted += 1
                hits += int((likeness[n] >= right - 1e-6).sum()) <= most
    return hits / wanted
