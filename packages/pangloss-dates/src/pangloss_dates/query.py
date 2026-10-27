"""Finding what is dated on a day: "everything on this date".

Occurrences of a repeated event are never stored, so a day is looked up the other way round (see
docs/dates.md, "Not expanding, but inverting"): the search asks for the rules whose lifetime holds the day and
whose `pattern_keys` has one of the day's keys (a few candidates), and each is then checked with the exact rule.
Dates that are not repeated are found by their bounds alone.

    refs = await on_day(Factoid, "when", day, Calendar.JULIAN, family="Julian")
"""

from typing import Any

from pangloss_models.search import Match

from pangloss_dates.calendar import Calendar
from pangloss_dates.recurrence import day_keys, occurs_on

PAGE_SIZE = 100
SINGLE_KINDS = ("ExactDate", "EDTFDate", "DateRange", "Period")


def bounds_where(day: int, fuzzy: bool) -> dict[str, Any]:
    which = "fuzzy" if fuzzy else "strict"
    return {
        f"earliest_{which}": {"lte": day},
        f"latest_{which}": {"gte": day},
    }


def dated_where(
    field: str, day: int, family: str = "", fuzzy: bool = True
) -> dict[str, Any]:
    """The pattern for the documents with a date that holds the day, other than a repeated event (`family` is
    `""`, `"Julian"` or `"Gregorian"`)"""
    return {
        "$any_of": [
            {field: {"type": f"{family}{kind}", "where": bounds_where(day, fuzzy)}}
            for kind in SINGLE_KINDS
        ]
    }


def recurring_where(
    field: str, day: int, calendar: Calendar, family: str = "", fuzzy: bool = True
) -> dict[str, Any]:
    """The pattern for the documents with a repeated event that might fall on the day (to be checked)"""
    return {
        field: {
            "type": f"{family}Recurrence",
            "where": {
                **bounds_where(day, fuzzy),
                "pattern_keys": {"contains_any": day_keys(day, calendar)},
            },
        }
    }


async def pages(model, where: dict[str, Any], limit: int):
    """The references the search finds, page after page, up to `limit`"""
    found = 0
    page = 1
    while True:
        result = await model.search(
            Match(where=where), page_number=page, page_size=PAGE_SIZE
        )
        for item in result.results:
            yield item
            found += 1
            if found >= limit:
                return
        if result.next_page is None:
            return
        page = result.next_page


async def on_day(
    model,
    field: str,
    day: int,
    calendar: Calendar,
    family: str = "",
    fuzzy: bool = True,
    limit: int = 1000,
) -> list:
    """The head documents of `model` with a date in `field` that holds the day (day number), or a repeated
    event in it that falls on it, as references, in the order of their labels. `fuzzy` takes a date to hold the
    day if it might (the fuzzy bounds); otherwise only if it is stated to (the strict bounds)."""
    found = {
        item.id: item
        async for item in pages(model, dated_where(field, day, family, fuzzy), limit)
    }
    candidates = [
        item
        async for item in pages(
            model, recurring_where(field, day, calendar, family, fuzzy), limit
        )
    ]
    for item in candidates:
        document = await model.get(item.id)
        date = getattr(document, field)
        recurrence_class = type(date)._owner
        rule = recurrence_class.rule_of(date)
        anchor = date.start.earliest_strict
        if occurs_on(rule, day, calendar, anchor):
            found[item.id] = item
    return sorted(found.values(), key=lambda item: (item.label.lower(), str(item.id)))
