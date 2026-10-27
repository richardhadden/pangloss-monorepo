"""EDTF text (Extended Date/Time Format) to bounds, in the Julian or the Gregorian calendar.

EDTF names no calendar, and `python-edtf` works out its own bounds in the Gregorian calendar (1500-02 ends on the 28th),
so it is used **only to parse**. This module reads the parts it finds (year, month, day, the qualifiers) and works out
the bounds with `pangloss_dates.calendar`, in the calendar the date is in. It needs the `edtf` extra
(`pip install pangloss-dates[edtf]`); nothing else in the package does.

What is read:

| EDTF | Means here |
|---|---|
| `1500`, `1500-03`, `1500-03-02` | that year, month or day, as stated (strict = fuzzy) |
| `1500?` `1500~` `1500%` (also on a month or a day) | uncertain, approximate, both: strict is the stated unit, fuzzy adds the padding |
| `2004-?06-11`, `2004-06-~11` (a qualifier on part of a date) | read as the whole date being qualified, at the precision of the date |
| `15XX`, `150X`, `1500-XX`, `1500-03-XX` | the span the unspecified digits leave open (strict = fuzzy) |
| `[1500,1502]`, `{1500,1502}` | from the earliest of the members to the latest |
| `1500-03/1500-05`, `1500/..` | an interval: for `parse_edtf_interval`, a period, not a single date |

Not read (an `EdtfUnsupported` error says so): seasons, significant digits (`1950S2`), long years (`Y170000002`),
times (the date part alone is not taken either: a time is not a day), unspecified digits with a qualifier, an
unspecified month with a day given, open-ended sets (`[..1500]`) and exponential years.
"""

from dataclasses import dataclass
from typing import Any

from pangloss_dates.bounds import (
    Bounds,
    Padding,
    Precision,
    exact_bounds,
    padded_bounds,
    precision_of,
)
from pangloss_dates.calendar import Calendar, InvalidDate, first_and_last_day


class EdtfError(ValueError):
    """The text is not EDTF, or is not a date in this calendar"""


class EdtfUnsupported(EdtfError):
    """Valid EDTF that this package does not read"""


class EdtfNotADate(EdtfError):
    """EDTF that is an interval where a single date was wanted, or the other way about"""


@dataclass(frozen=True)
class EdtfResult:
    bounds: Bounds
    precision: Precision
    uncertain: bool = False
    approximate: bool = False


def _parse(text: str) -> Any:
    try:
        from edtf import parse_edtf
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "reading EDTF needs the edtf package: pip install 'pangloss-dates[edtf]'"
        ) from e
    try:
        return parse_edtf(text.strip())
    except Exception as e:
        raise EdtfError(f"{text!r} is not EDTF: {e}") from e


def _number(part: str | None, what: str) -> int | None:
    if part is None:
        return None
    try:
        return int(part)
    except ValueError as e:
        raise EdtfUnsupported(f"a {what} of {part!r} is not read") from e


def _flags(node: Any) -> tuple[bool, bool]:
    """(uncertain, approximate): `%` is both"""
    both = getattr(node, "is_uncertain_and_approximate", False)
    return (
        bool(node.is_uncertain or both),
        bool(node.is_approximate or both),
    )


def parse_edtf_date(
    text: str, calendar: Calendar, padding: Padding | None = None
) -> EdtfResult:
    """A single date: its bounds in the calendar"""
    node = _parse(text)
    try:
        return _date(node, calendar, padding)
    except InvalidDate as e:
        raise EdtfError(f"{text!r}: {e}") from e


def parse_edtf_interval(
    text: str, calendar: Calendar, padding: Padding | None = None
) -> tuple[EdtfResult | None, EdtfResult | None]:
    """The start and the end of an interval; None where it is open (`1500/..`) or unknown (`1500/`)"""
    node = _parse(text)
    if type(node).__name__ not in ("Interval", "Level1Interval", "Level2Interval"):
        raise EdtfNotADate(f"{text!r} is a date, not an interval")
    try:
        return tuple(  # ty: ignore[invalid-return-type]
            None
            if getattr(side, "is_open", False) or getattr(side, "is_unknown", False)
            else _date(side, calendar, padding)
            for side in (node.lower, node.upper)
        )
    except InvalidDate as e:
        raise EdtfError(f"{text!r}: {e}") from e


def _date(node: Any, calendar: Calendar, padding: Padding | None) -> EdtfResult:
    kind = type(node).__name__
    match kind:
        case "Date":
            if node.significant_digits:
                raise EdtfUnsupported("significant digits (S) are not read")
            year, month, day = _parts(node)
            return EdtfResult(
                exact_bounds(year, month, day, calendar), precision_of(month, day)
            )
        case "UncertainOrApproximate":
            inner = _date(node.date, calendar, padding)
            uncertain, approximate = _flags(node)
            if not (uncertain or approximate):
                return inner
            return _qualified(node.date, calendar, padding, uncertain, approximate)
        case "PartialUncertainOrApproximate":
            if getattr(node, "season", None):
                raise EdtfUnsupported("seasons are not read")
            uncertain, approximate = _flags(node)
            return _qualified(node, calendar, padding, uncertain, approximate)
        case "Unspecified":
            return _unspecified(node, calendar)
        case "OneOfASet" | "MultipleDates":
            return _set(node, calendar, padding)
        case "Interval" | "Level1Interval" | "Level2Interval":
            raise EdtfNotADate("an interval is a period; use parse_edtf_interval")
        case "Season" | "Level2Season":
            raise EdtfUnsupported("seasons are not read")
        case "LongYear":
            raise EdtfUnsupported("long years (Y...) are not read")
        case "DateAndTime":
            raise EdtfUnsupported("a time of day is not read")
        case _:
            raise EdtfUnsupported(f"{kind} is not read")


def _parts(node: Any) -> tuple[int, int | None, int | None]:
    year = _number(node.year, "year")
    if year is None:  # pragma: no cover
        raise EdtfError("no year")
    return year, _number(node.month, "month"), _number(node.day, "day")


def _qualified(
    node: Any,
    calendar: Calendar,
    padding: Padding | None,
    uncertain: bool,
    approximate: bool,
) -> EdtfResult:
    year, month, day = _parts(node)
    return EdtfResult(
        padded_bounds(year, month, day, calendar, padding),
        precision_of(month, day),
        uncertain=uncertain,
        approximate=approximate,
    )


def _unspecified(node: Any, calendar: Calendar) -> EdtfResult:
    uncertain, approximate = _flags(node)
    if uncertain or approximate:
        raise EdtfUnsupported("unspecified digits with a qualifier are not read")
    year_text, month_text, day_text = node.year, node.month, node.day
    if getattr(node, "negative", False):
        raise EdtfUnsupported("unspecified digits in a negative year are not read")
    if "X" in year_text:
        if month_text is not None or day_text is not None:
            raise EdtfUnsupported(
                "unspecified year digits with a month or a day are not read"
            )
        low = int(year_text.replace("X", "0"))
        high = int(year_text.replace("X", "9"))
        first = first_and_last_day(low, None, None, calendar)[0]
        last = first_and_last_day(high, None, None, calendar)[1]
        return EdtfResult(Bounds(first, first, last, last), Precision.RANGE)
    year = int(year_text)
    if month_text == "XX":
        if day_text not in (None, "XX"):
            raise EdtfUnsupported("a day in an unspecified month is not read")
        return EdtfResult(exact_bounds(year, None, None, calendar), Precision.YEAR)
    month = int(month_text)
    return EdtfResult(exact_bounds(year, month, None, calendar), Precision.MONTH)


def _set(node: Any, calendar: Calendar, padding: Padding | None) -> EdtfResult:
    members = []
    for member in node.objects:
        if type(member).__name__ in ("EarlierConsecutives", "LaterConsecutives"):
            raise EdtfUnsupported("an open-ended set is not read")
        members.append(_date(member, calendar, padding))
    if not members:  # pragma: no cover
        raise EdtfError("an empty set")
    bounds = Bounds(
        min(m.bounds.earliest_fuzzy for m in members),
        min(m.bounds.earliest_strict for m in members),
        max(m.bounds.latest_strict for m in members),
        max(m.bounds.latest_fuzzy for m in members),
    )
    return EdtfResult(
        bounds,
        Precision.RANGE,
        uncertain=any(m.uncertain for m in members),
        approximate=any(m.approximate for m in members),
    )
