# Dates

`pangloss-dates` is an optional package for the dates of history: a day that is only known to the year, a range, "about 1500", a period of office, a mass said "every Sunday". Each is stored with the same few whole numbers, so documents can be found by date and ordered by date whatever kind of date they have.

This guide uses the Julian calendar, as the sources of 1450 to 1530 do. For the design and the reasons see [Dates: implementation plan](../../docs/dates-implementation.md).

## Install and choose a calendar

Add the package (and `pangloss-dates[edtf]` if you want to type EDTF text) and give your models the family for your calendar:

```python
from typing import Annotated

from pangloss_dates.bounds import SortBy
from pangloss_dates.julian import JulianDate, JulianExactDate
from pangloss_dates.models import SortDefault
from pangloss_models import Document, Entity


class Factoid(Document):
    when: JulianDate                      # any kind of Julian date


class Person(Entity):
    born: Annotated[JulianExactDate, SortDefault(SortBy.EARLIEST_FUZZY)]
```

- `pangloss_dates.julian` and `pangloss_dates.gregorian` each have a family: `JulianDate` (take any kind), `JulianExactDate`, `JulianEDTFDate`, `JulianDateRange`, `JulianOngoingDate`, `JulianPeriod`, `JulianRecurrence`. A Julian date cannot be given another calendar.
- `pangloss_dates.models` has the same types with no calendar fixed (`Date`, `ExactDate`, ...): the date says, or the setting `DATES_DEFAULT_CALENDAR` (Gregorian) does.
- A project uses one family. Day numbers are the same in every calendar, so dates of both can be ordered together if you do mix them.

## The kinds of date

| Give | Means |
|---|---|
| `{"type": "JulianExactDate", "year": 1500}` (and `"month"`, `"day"`) | The year, the month or the day, as stated |
| `{"type": "JulianEDTFDate", "edtf": "1500-03~"}` | EDTF text: `?` uncertain, `~` approximate, `15XX`, `[1500,1502]`. Nobody has to write it |
| `{"type": "JulianDateRange", "earliest": {...}, "latest": {...}}` | One date that is somewhere between two exact dates (each can be a year, a month or a day) |
| `{"type": "JulianPeriod", "start": {...}, "end": {...}}` | An office, a residence. The ends are any of the above; the end can be `{"type": "JulianOngoingDate"}` |
| `{"type": "JulianRecurrence", "frequency": "weekly", "weekdays": [0], "excluded_days": [], "start": {...}, "end": {...}}` | A repeated event: weekdays are 0 for Sunday to 6; `frequency` is `weekly`, `monthly` or `yearly`; with `nth` (the third, or -1 for the last), `month`, `month_day`, `interval` |

A date also takes `source_text`, what the source said, kept as written.

## What is stored

Whatever the kind, every date has these, worked out when it is saved (anything you send for them is replaced):

- `earliest_strict` and `latest_strict`: the range as stated. `1500-03` is 1 to 31 March.
- `earliest_fuzzy` and `latest_fuzzy`: the same allowing for doubt. `1500-03~` ("about March 1500") is fuzzy from 1 February to 30 April. *Fuzzy* here means "allowing for doubt", not vague.
- `sort_day` and `end_sort_day`: the day to order by (below).
- `precision`: `year`, `month`, `day`, `range` or `ongoing`.

They are whole numbers: the Julian Day Number, which counts days and does not depend on any calendar's months. `pangloss_dates.calendar` turns them into dates and back (`to_jdn`, `from_jdn`, `convert`, `weekday`).

### How much doubt adds

The fuzzy range adds a year either side of an approximate or uncertain year, a month either side of a month, and a week either side of a day. Change this with the settings below.

## Ordering

Documents are ordered by a date with `order_by` in a search:

```python
found = await Factoid.search(
    Match(order_by=[{"field": "when.sort_day", "direction": "asc"}])
)
```

- `sort_day` is by default the middle of the strict range: 1 July for the year 1500. A period or a recurrence sorts by its **start**; `end_sort_day` is where it ends.
- Choose another day with `sort_by` on the date (`midpoint`, `earliest_strict`, `latest_strict`, `earliest_fuzzy`, `latest_fuzzy`, `midpoint_fuzzy`), or give every date of a field a default with `SortDefault`, as `born` does above. A date's own `sort_by` wins.
- A document with no date comes last, ascending or descending.

## Finding by date

The structured search looks into a date as into a relation (see [Structured search](../../docs/structured-search.md)):

```python
await Factoid.search(Match(where={"when": {"where": {"earliest_strict": {"gte": to_jdn(1500, 1, 1, JULIAN)}}}}))
```

and `pangloss_dates.query.on_day` finds everything dated on one day: the dates whose bounds hold it, and the repeated events that fall on it (a rule is never expanded; the search finds the few that might, and each is checked):

```python
sunday = to_jdn(1510, 3, 4, Calendar.JULIAN)
found = await on_day(Factoid, "when", sunday, Calendar.JULIAN, family="Julian")
```

`fuzzy=False` takes a date to hold the day only if it is stated to.

## Settings

| Setting | Default | |
|---|---|---|
| `DATES_DEFAULT_CALENDAR` | `"gregorian"` | The calendar of a plain `Date` that does not say |
| `DATES_PADDING_YEARS`, `DATES_PADDING_MONTHS`, `DATES_PADDING_DAYS` | `1`, `1`, `7` | What doubt adds either side |
| `DATES_OPEN_END_YEAR` | `1600` | A period or order with no end is taken to stop by the end of this year (so it can be found and ordered) |

Changing a padding does not change what is stored: a date is worked out again when it is next saved.
