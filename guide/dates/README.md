# Dates

`pangloss-dates` is an optional package for the dates of history: a day that is only known to the year, a range, "about 1500", a period of office, a mass said "every Sunday". Each is stored with the same few whole numbers, so documents can be found by date and ordered by date whatever kind of date they have.

This guide uses the Julian calendar, as the sources of 1450 to 1530 do. For the design and the reasons see [Dates: implementation plan](../../docs/dates-implementation.md).

## Install and choose a calendar

Add the package (and `pangloss-dates[edtf]` if you want to type EDTF text) and give your models the family for your calendar:

```python
from typing import Annotated

from pangloss_dates import JulianDate, JulianExactDate, SortBy, SortDefault
from pangloss_models import Document, Entity


class Factoid(Document):
    when: JulianDate                      # any kind of Julian date


class Person(Entity):
    born: Annotated[JulianExactDate, SortDefault(SortBy.EARLIEST_FUZZY)]
```

- There is a family for each calendar (all imported from `pangloss_dates`): `JulianDate` (take any kind), `JulianExactDate`, `JulianEDTFDate`, `JulianDateRange`, `JulianOngoingDate`, `JulianPeriod`, `JulianRecurrence`. A Julian date cannot be given another calendar.
- `Date`, `ExactDate` and the rest are the same types with no calendar fixed: the date says, or the setting `DATES_DEFAULT_CALENDAR` (Gregorian) does.
- A project uses one family. Day numbers are the same in every calendar, so dates of both can be ordered together if you do mix them.

## The kinds of date

| Give | Means |
|---|---|
| `{"type": "JulianExactDate", "year": 1500}` (and `"month"`, `"day"`) | The year, the month or the day, as stated |
| `{"type": "JulianEDTFDate", "edtf": "1500-03~"}` | EDTF text: `?` uncertain, `~` approximate, `15XX`, `[1500,1502]`. Nobody has to write it |
| `{"type": "JulianDateRange", "not_before": {...}, "not_after": {...}}` | One date that is somewhere between two exact dates (each can be a year, a month or a day). The names are the TEI's (`notBefore`, `notAfter` in the API). Either end may be `{"type": "JulianUnknownDate"}` ("not before 1490", and nothing said of when it was by), not both: the range then runs to `DATES_OPEN_END_YEAR` (or from `DATES_EARLIEST_YEAR`) and sorts by the end that is known |
| `{"type": "JulianPeriod", "start": {...}, "end": {...}}` | An office, a residence. The ends are any of the above. If one end is not known, `{"type": "JulianUnknownDate"}` (not both); `{"type": "JulianOngoingDate"}` as the end says it was still going |
| `{"type": "JulianRecurrence", "frequency": "weekly", "weekdays": [0], "excluded_days": [], "start": {...}, "end": {...}}` | A repeated event: weekdays are 0 for Sunday to 6; `frequency` is `weekly`, `monthly` or `yearly`; with `nth` (the third, or -1 for the last), `month`, `month_day`, `interval`; yearly only, instead of a month: `easter_offset` (days from Easter, -80 to 250; 49 is Pentecost) or `feast` (a key the calendar package works out) |

### When an end is not known

A period starts one day and ends another, but a source may give only one. Give the end that is known and `JulianUnknownDate` for the other: the period is open from `DATES_EARLIEST_YEAR` (or to `DATES_OPEN_END_YEAR`), so a search for a date it could include still finds it, and it is ordered by the end that is known. Both ends cannot be unknown. Prefer a **reasonable guess** when you can make one: a `JulianDateRange` ("between 1490 and 1500") or EDTF `1495~` says more than "unknown" and is found by the dates it fits. `OngoingDate` is a different statement ("he still held it when this was written") and is kept for projects that need it.

A date also takes `source_text`, what the source said, kept as written.

## What is stored

Whatever the kind, every date has these in the database, worked out when it is saved. They are only in the database: a date you send or read back has none of them (anything you send for them is dropped), but you can search and order by them.

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
| `DATES_OPEN_END_YEAR` | `1600` | A period or order that is ongoing, or whose end is unknown, is taken to stop by the end of this year (so it can be found and ordered) |
| `DATES_EARLIEST_YEAR` | `1` | A start that is not known is taken to be no earlier than the start of this year. Set it near your sources (`1400`) so an unknown start does not reach back to the first century |

Changing a padding does not change what is stored: a date is worked out again when it is next saved.

## Dates in derived rules

With [`pangloss-derived`](../derived/README.md), a rule can compare the dates of two statements: who held office at the
same time, who came before whom, what happened within a year of what:

```python
from pangloss_dates.rules import overlaps

@rule
def contemporaries(a: Var[Person], b: Var[Person], d1: Var[Date], d2: Var[Date]):
    return Contemporaries.Derive(first=a, second=b).when(
        HoldsOffice.Where(person=a, when=d1),
        HoldsOffice.Where(person=b, when=d2),
        overlaps(d1, d2),
    )
```

`overlaps`, `before`, `after`, `during` and `within(d1, d2, days=...)` compare the dates' bounds allowing for doubt
(`strict=True` compares them as stated).

## Dateable documents

A document (or an entity) that happened at some time can have its date from a trait, instead of a field of its own:

```python
from pangloss_dates import Dateable, PeriodDateable, SingleDateable


class Statement(Document, Dateable):           # date: Date (any kind)
    text: str


class Birth(Document, SingleDateable):         # date: an ExactDate, a DateRange, an EDTFDate or an UnknownDate
    child: Person


class Office(Document, PeriodDateable):        # date: a Period or an UnknownDate
    holder: Person
```

- The field is always `date`. A class can narrow it: `date: JulianDate`, or `date: Annotated[Date, SortDefault(SortBy.EARLIEST_FUZZY)]`.
- When one is saved, its date's `sort_day` and `end_sort_day` and a short text of it are copied onto its own node, as `date_sort_day`, `date_end_sort_day` and `date_text`. They are only in the database (worked out, never sent), and they are in its **reference**: a list, and what refers to an entity, carry its date without reading it. `date_text` uses no words, so it needs no translation: `1500`, `1500-03`, `1500–1502`, `≥ 1500`, `≤ 1502`, `?`, `1500–…`, `[1500–1501]–1520`, `↻ 1500–1520` (a recurrence), or an EDTF date as written.
- Order a search by date with `order_by=[{"field": "date_sort_day"}]` (there is an index on `:Dateable(date_sort_day)`).
- The nodes are labelled `:Dateable` (and `:SingleDateable`, `:PeriodDateable`), so a relation can point to "anything dateable".
- In the interface, an entity's page shows what refers to it **by field** or **by date**: by date, in order, with the date and the field on the left and a slider of years on the right; then those whose date is not known, and those of a kind that has no date.

A class that already had a `date: Date` and becomes dateable gets the label and the fields from `makemigrations`; the copies of the documents that exist are filled in by a step you add at the end of that migration:

```python
{"change": "RunPython", "safety": "transforming", "function": "pangloss_dates.dateable:fill_in_dateables", "affects": ["Statement"]}
```

