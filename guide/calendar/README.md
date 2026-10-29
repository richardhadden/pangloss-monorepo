# Calendar

`pangloss-calendar` shows what is dated on a day, in a month or in a year, in the Julian or the Gregorian calendar, with the feasts
that you give it (as entities of your own). It needs [`pangloss-dates`](../dates/README.md) (your models' dates are what it finds). The design and the numbers
are in [docs/calendar-implementation.md](../../docs/calendar-implementation.md).

## Set up

1. Add `"pangloss_calendar"` to `INSTALLED_APPS`, after `pangloss_dates`.
2. Settings:

   | Setting | |
   |---|---|
   | `CALENDAR_FIRST_YEAR`, `CALENDAR_LAST_YEAR` | The span to make days for. No default: `seed` refuses to run without them |
   | `CALENDAR_DEFAULT` | `"julian"` or `"gregorian"`: the calendar a view is read in (default: `DATES_DEFAULT_CALENDAR`) |
   | `CALENDAR_EXTEND_MARGIN_YEARS` | How far beyond the span days are made when a rule or an attachment needs them (default 10; 0 for none) |
   | `CALENDAR_USE` | Only the characterisations of this `use` (default: all) |
   | `CALENDAR_NARROW_DAYS` | A date that states a range of this many days or fewer is drawn on each of its days in a month; a wider one is listed apart (default 7) |
   | `CALENDAR_FIELDS` | `["Letter.sent", ...]`: look only in these date fields (default: every date field of every Document and Entity) |
   | `CALENDAR_AUTO_EXTEND` | Make the days of the graph that are asked for and are not there (default off; the answers do not need them) |

3. `pangloss migrate` (the keys and indexes of the calendar, and the migrations that `pangloss_dates` and `pangloss_calendar` bring for their models; `pangloss makemigrations` then writes only your own), then `pangloss calendar seed` (days, with their months and years in both calendars,
   and the edges from rules). Running it again is harmless.

## Feasts and other characterisations

None are provided: you make them. `DateCharacterisation` is an abstract entity; subclass it for what you need:

```python
from pangloss_calendar.models import DateCharacterisation

class FeastDay(DateCharacterisation):
    saint: list[Saint]       # anything else an entity can have
```

A `FeastDay` has a `label`, a `use` (the liturgical use, or whatever you divide them by), a `rank`, and `when`, the rule it falls by.
`when` is a `Recurrence` from [pangloss-dates](../dates/README.md), in the calendar it is written in:

```python
FeastDay.Create(label="Benedict", use="sarum", rank="major", when={
    "type": "Recurrence", "calendar": "julian", "frequency": "yearly", "weekdays": [], "excluded_days": [],
    "month": 3, "month_day": 21,                                   # 21 March, Julian ...
    "start": {"type": "ExactDate", "calendar": "julian", "year": 1450},   # ... observed from 1450
    "end": {"type": "ExactDate", "calendar": "julian", "year": 1530, "month": 12, "day": 31}})
```

Use `"easter_offset": 49` instead of `month` and `month_day` for a day that moves with Easter (Pentecost; -80 to 250), or `nth` with
one weekday for "the third Sunday of March". A characterisation that has no rule (a term day that is set by hand) has
`when={"type": "NoRule"}`. A repeated event of another model can fall on a feast with `"feast": "<the id of the FeastDay>"` in its rule.
One feast with two days in the year is two entities.

**By hand**, a logged-in user can attach a characterisation to a day, a month, a year or any span of days, and take it away:
`POST /api/calendar/attach` with `{"characterisation": "<id>", "day": "J1500-03-02"}`, or `{"calendar": "julian", "year": 1500, "month": 3}`,
`{"calendar": "julian", "year": 1500}`, or `{"first": "J1500-03-01", "last": "J1500-03-08"}`; `POST /api/calendar/detach` with the same.

**The graph.** `pangloss calendar link` (and `seed`) makes an edge from each day to the characterisations whose rule falls on it, so
you can ask the graph "every day Benedict fell on". Run it again after you change a characterisation: the edges made from a rule are
made again; what was attached by hand is not touched. The day and month views do not need the edges (they work the rules out), so they
are right before `link` is run.

**What is out of reach.** The calendar has the span you set (`CALENDAR_FIRST_YEAR` to `CALENDAR_LAST_YEAR`) and
`CALENDAR_EXTEND_MARGIN_YEARS` (default 10) either side. A rule that starts just before the span, or a day attached just after it, is
within the margin: the days are made. A rule whose lifetime goes further out has only the days inside the reach linked (`link` says how
many rules); one wholly outside, and an attachment outside, are left out (the attachment is refused with a 422). Nothing about the
documents with dates is linked (they are found by their dates), so an author in the project because he wrote a text, born in 384 BC,
is not on the calendar's graph.

A feast on 24 to 28 February may say `"leap_shift": true`: it falls a day later in a leap year (the old Roman leap day was made by repeating the 24th). Not yet: a rule that repeats a span (Lent every year).

## Reading it

Read only, under `/api/calendar` (see [the API](../../docs/api.md)): `day/J1500-03-02` (or `G1500-03-12`, or a day number: the same
day), `month/julian/1500/3`, `year/julian/1500`, `easter/julian/1500`, `characterisations`. A date is **stated** on a day if the date says so,
**possible** if only its allowance for doubt reaches it. Characterisations are listed on their own, with how each comes to be there (`rule`, or attached by hand to the `day`, `month`, `year` or `span`). Nothing deleted, and nothing unpublished for a reader who may not see it, is shown.
