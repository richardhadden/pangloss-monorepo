# pangloss-calendar

Optional. Days, months, years and spans in the Julian or the Gregorian calendar, and `DateCharacterisation` entities (feasts and
the like: by a rule that repeats, on one day or over one span, or attached by hand), built on `pangloss-dates`: what is dated on
a day, in a month, in a year, and when Easter falls.
Routes under `/api/calendar`, commands `pangloss calendar …`, and, with `pangloss_interface`, pages of its own (`interface/`:
the years, a month as a calendar page, a day; **Calendar** in the navigation bar).

Add `"pangloss_calendar"` to `INSTALLED_APPS`. Runs on Memgraph and Neo4j.

Guide: [guide/calendar](../../guide/calendar/README.md). Reference: [docs/calendar-implementation.md](../../docs/calendar-implementation.md).
