"""A date as text in a label (`Formatter("pangloss_dates:date")`, implementation_docs/label-templates.md): the same words as
`formatDate` of the interface module (`interface/src/format.ts`), in English. The cases of `tests/test_labels.py` are
run by both"""

from collections.abc import Mapping
from typing import Any

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
WEEKDAYS = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]
NTH = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", -1: "last"}


def _num(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _month(value: Any) -> str | None:
    month = _num(value)
    if month is None:
        return None
    return MONTHS[month - 1] if 1 <= month <= 12 else str(month)


def _exact(date: Mapping[str, Any]) -> str:
    day, month, year = (
        _num(date.get("day")),
        _month(date.get("month")),
        _num(date.get("year")),
    )
    if day is not None and month is not None and year is not None:
        return f"{day} {month} {year}"
    if month is not None and year is not None:
        return f"{month} {year}"
    return " ".join(str(part) for part in (day, month, year) if part is not None)


def _recurrence(date: Mapping[str, Any]) -> str:
    weekdays = [
        WEEKDAYS[w] if isinstance(w, int) and 0 <= w < 7 else str(w)
        for w in (date.get("weekdays") or [])
    ]
    month = _month(date.get("month"))
    nth = NTH.get(_num(date.get("nth")) or 0)
    month_day = _num(date.get("monthDay"))
    easter = _num(date.get("easterOffset"))
    frequency = date.get("frequency") or ""
    n = _num(date.get("interval")) or 1
    unit = (
        ("week", "weeks")
        if frequency == "weekly"
        else ("month", "months")
        if frequency == "monthly"
        else ("year", "years")
    )
    on: str | None = None
    if easter is not None:
        on = (
            "Easter"
            if easter == 0
            else f"Easter {'+' if easter > 0 else '−'} {abs(easter)} days"
        )
    elif nth is not None and weekdays:
        on = (
            f"the {nth} {weekdays[0]} of {month}"
            if month is not None
            else f"the {nth} {weekdays[0]}"
        )
    elif month is not None and month_day is not None:
        on = f"{month_day} {month}"
    elif month is not None:
        on = month
    elif month_day is not None:
        on = f"the {month_day}."
    elif weekdays:
        on = ", ".join(weekdays)
    every = f"every {n} {unit[1]}" if n != 1 else f"every {unit[0]}"
    return every if on is None else f"{every} on {on}"


def _is_unknown(end: Any) -> bool:
    return isinstance(end, Mapping) and end.get("type") == "UnknownDate"


def _say(date: Any, outer: bool) -> str | None:
    if not isinstance(date, Mapping):
        return None

    def inner(part: Any) -> str:
        return str(_say(part, False))

    match date.get("type"):
        case "ExactDate":
            text = _exact(date)
        case "EDTFDate":
            text = date["edtf"] if isinstance(date.get("edtf"), str) else None
        case "DateRange":
            if _is_unknown(date.get("notAfter")):
                text = f"not before {inner(date.get('notBefore'))}"
            elif _is_unknown(date.get("notBefore")):
                text = f"not after {inner(date.get('notAfter'))}"
            else:
                text = (
                    f"{inner(date.get('notBefore'))} to {inner(date.get('notAfter'))}"
                )
        case "OngoingDate":
            text = "ongoing"
        case "UnknownDate":
            text = "unknown"
        case "Period":
            text = f"{inner(date.get('start'))} – {inner(date.get('end'))}"
        case "Recurrence":
            text = f"{_recurrence(date)}, {inner(date.get('start'))} – {inner(date.get('end'))}"
        case _:
            return None
    if text is None:
        return None
    calendar = date.get("calendar")
    if outer and isinstance(calendar, str) and calendar != "gregorian":
        text += f" ({calendar})"
    if outer and isinstance(source := date.get("sourceText"), str) and source:
        text += f" “{source}”"
    return text


def format_date(date: Mapping[str, Any]) -> str | None:
    """A date as a person would say it, from the JSON of any of the date models (None for what is not one)"""
    return _say(date, True)
