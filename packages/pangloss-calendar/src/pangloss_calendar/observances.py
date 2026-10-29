"""Observances (feasts): the file format, checking it, and working out the day a feast falls on.

An observance is data that a project provides; none is shipped. The file is TOML, one `[[observance]]` table for each:

    [[observance]]
    key = "sarum:st-benedict"        # unique; the prefix is the liturgical use
    use = "sarum"
    name = { en = "Benedict", la = "Benedicti abbatis" }
    rank = "major"                   # the project's own scale
    fixed = { month = 3, day = 21 }  # a fixed feast ...
    # easter_offset = 49             # ... or a moveable one: days from Easter (Pentecost)
    leap_shift = false

A fixed feast on 24 to 28 February may say `leap_shift = true`: in the old Roman reckoning the leap day was made by
repeating 24 February, so in a leap year such a feast falls one day later (St Matthias is 24 February, and 25 in a
leap year). Nothing else is shifted: March, the other months and the feasts before the 24th keep their dates.

Everything here is pure: `falls_on` and `observances_on` need no database. A feast is worked out in the calendar
asked for, so the Julian Easter and the Julian 21 March are the Julian ones.
"""

import tomllib
from dataclasses import dataclass, field
from typing import Any

from pangloss_dates.calendar import (
    Calendar,
    InvalidDate,
    check_date,
    from_jdn,
    is_leap_year,
    to_jdn,
)
from pangloss_dates.easter import easter
from pangloss_dates.recurrence import EASTER_OFFSETS


class InvalidObservance(ValueError):
    """The file, or an observance in it, is not valid"""


@dataclass(frozen=True)
class Observance:
    key: str
    use: str
    name: dict[str, str] = field(default_factory=dict)
    rank: str | None = None
    fixed: tuple[int, int] | None = None
    """(month, day)"""
    easter_offset: int | None = None
    leap_shift: bool = False

    def __post_init__(self):
        if not self.key.strip():
            raise InvalidObservance("an observance needs a key")
        if (self.fixed is None) == (self.easter_offset is None):
            raise InvalidObservance(
                f"{self.key}: give either fixed (month and day) or easter_offset, not both and not neither"
            )
        if self.fixed is not None:
            month, day = self.fixed
            for calendar in Calendar:
                try:  # (a leap year, so that 29 February is allowed)
                    check_date(2000, month, day, calendar)
                except InvalidDate as error:
                    raise InvalidObservance(f"{self.key}: {error}") from error
        if self.easter_offset is not None and self.easter_offset not in EASTER_OFFSETS:
            raise InvalidObservance(
                f"{self.key}: easter_offset {self.easter_offset} is not from "
                f"{EASTER_OFFSETS.start} to {EASTER_OFFSETS.stop - 1}"
            )
        if self.leap_shift and not (
            self.fixed is not None and self.fixed[0] == 2 and 24 <= self.fixed[1] <= 28
        ):
            raise InvalidObservance(
                f"{self.key}: leap_shift is for a fixed feast from 24 to 28 February"
            )

    @property
    def feast_key(self) -> str:
        """The key a day has when the observance falls on it (`feast:` + key), as `pangloss_dates` uses"""
        return f"feast:{self.key}"


def parse(text: str) -> list[Observance]:
    """The observances of a file (TOML); raises `InvalidObservance` naming what is wrong"""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise InvalidObservance(f"not valid TOML: {error}") from error
    unknown = set(data) - {"observance"}
    if unknown:
        raise InvalidObservance(f"unknown top-level keys: {sorted(unknown)}")
    found = [_one(entry) for entry in data.get("observance", [])]
    seen: set[str] = set()
    for observance in found:
        if observance.key in seen:
            raise InvalidObservance(f"{observance.key}: the key is used twice")
        seen.add(observance.key)
    return found


_FIELDS = {"key", "use", "name", "rank", "fixed", "easter_offset", "leap_shift"}


def _one(entry: dict[str, Any]) -> Observance:
    unknown = set(entry) - _FIELDS
    if unknown:
        raise InvalidObservance(
            f"{entry.get('key', '?')}: unknown fields {sorted(unknown)}"
        )
    for required in ("key", "use"):
        if not isinstance(entry.get(required), str):
            raise InvalidObservance(
                f"{entry.get('key', '?')}: {required} is needed, as text"
            )
    fixed = entry.get("fixed")
    if fixed is not None:
        if set(fixed) != {"month", "day"}:
            raise InvalidObservance(f"{entry['key']}: fixed is {{ month = , day = }}")
        fixed = (fixed["month"], fixed["day"])
    return Observance(
        key=entry["key"],
        use=entry["use"],
        name=dict(entry.get("name", {})),
        rank=entry.get("rank"),
        fixed=fixed,
        easter_offset=entry.get("easter_offset"),
        leap_shift=entry.get("leap_shift", False),
    )


def falls_on(observance: Observance, year: int, calendar: Calendar) -> int | None:
    """The day number of the observance in the year of the calendar, or None (a feast on 29 February in a year
    with none)"""
    if observance.easter_offset is not None:
        return easter(year, calendar) + observance.easter_offset
    month, day = observance.fixed  # ty: ignore[not-iterable]
    if month == 2 and day == 29 and not is_leap_year(year, calendar):
        return None
    jdn = to_jdn(year, month, day, calendar)
    if observance.leap_shift and is_leap_year(year, calendar):
        jdn += 1
    return jdn


def observances_on(
    observances: list[Observance],
    jdn: int,
    calendar: Calendar,
    use: str | None = None,
) -> list[Observance]:
    """The observances (of the `use`, if given) that fall on the day, in the calendar asked for"""
    year = from_jdn(jdn, calendar).year
    return [
        o
        for o in observances
        if (use is None or o.use == use) and falls_on(o, year, calendar) == jdn
    ]


def feast_keys(
    observances: list[Observance], jdn: int, calendar: Calendar, use: str | None = None
) -> list[str]:
    """The `extra_keys` for `pangloss_dates.query.on_day`: the feasts of the day"""
    return [o.feast_key for o in observances_on(observances, jdn, calendar, use)]
