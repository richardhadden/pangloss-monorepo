# Calendar: an implementation plan for `pangloss-calendar` ⏳

**Status: a plan, nothing built (2026-10-28).** It narrows the calendar half of [dates.md](dates.md) to what can be built now that
`pangloss-dates` exists ([dates-implementation.md](dates-implementation.md): day numbers, four bounds, `sort_day`, periods,
recurrence with `pattern_keys`, `on_day`, both calendars, 113+ tests). *To check* marks a fact about code or a source not yet
verified. The decisions I need from you are at the end.

## What it is for

`pangloss-dates` answers "when is this?" for one document. The calendar answers the questions from the other side:

1. **What is on this day?** (a day page: the documents dated on it, the repeated events that fall on it, the feasts)
2. **What is in this month or year?** (a month view, with uncertain dates shown for what they are)
3. **When is this feast, in this year?** (Easter and everything that moves with it; the saints' days of a liturgical use)
4. **Browsing and tagging**: step from day to day; start a new document "about" a day or a feast, with its date filled in.

It is optional, and requires `pangloss-dates` (and so `pangloss-models`, `pangloss-core`). It is the only thing that needs a
database of its own shape: the rest of Pangloss and of `pangloss-dates` work without it.

## The central choice: the calendar does not need to own the dates

`dates.md` planned `OCCURS_ON` edges from every date to the calendar, written by a background worker. That needs two things the
core does not have (a `:PGExternal` marker so that updating a document does not delete the days it points at, and a
"pending derivation" mechanism), and a probability mass per day, which is not built either.

`pangloss-dates` has since made it unnecessary for a first version: each date has **indexed integer bounds**, and
`on_day` already finds "everything on a day" from them (and from `pattern_keys` for repeated events), with no calendar nodes.
So:

- **Version 1 (phases 0 to 4): no edges from dates to the calendar.** Day pages and month views are *queries over the bounds*; the
  calendar graph holds only what dates cannot: **days, months, years and observances**, which are what you navigate and what feasts
  attach to. No change to the core. Nothing a document writes depends on the calendar being installed or seeded.
- **Version 2 (phase 5, only if measured to be needed): derived `OCCURS_ON` edges**, as `dates.md` describes, for when a month
  view over very many dates is too slow, or when probabilities per day are wanted.

This is a change from `dates.md`, which put the edges first. The reason is that version 1 is useful without them and needs no core
work; the cost is that a month view is computed at request time (below, with a way to measure it).

## How it sits on `pangloss-dates`

| `pangloss-dates` has | The calendar uses it for |
|---|---|
| `Calendar` (`julian`, `gregorian`), `to_jdn`, `from_jdn`, `convert`, `month_length`, `is_leap_year`, `weekday`, `nth_weekday`, `first_and_last_day` | **All day arithmetic.** The calendar package writes none of its own: a day is a JDN, its Julian and Gregorian names come from `from_jdn` |
| `Date` and its families (`JulianExactDate`, ...), with `earliest_fuzzy`, `earliest_strict`, `latest_strict`, `latest_fuzzy`, `sort_day`, indexed | The day and month queries: "holds the day" is `earliest_* <= D <= latest_*`; strict says the source states it, fuzzy that it might |
| `RecurrenceRule`, `occurs_on`, `pattern_keys`, `day_keys`, `Recurrence.pattern_keys` | "On this day" for repeated events (`query.on_day`), unchanged |
| `config.default_calendar()` and the `DATES_*` settings | The calendar a view opens in, and the span of years (`DATES_EARLIEST_YEAR`, `DATES_OPEN_END_YEAR`) |

**What `pangloss-dates` lacks and the calendar needs** (small, and they belong in dates, because a `Recurrence` should be able to say them
whether or not the calendar is installed):

1. **Easter**: `pangloss_dates.easter.easter(year, calendar) -> jdn`, pure. Julian by the Julian computus, Gregorian by the Gregorian one.
2. **Two more rule fields** in `RecurrenceRule`: `easter_offset: int | None` ("Easter + 14", yearly) and `feast: str | None` (yearly on a
   feast, a key from the observances). With their `pattern_keys` (`easter:+14`, `feast:sarum:st-benedict`) and, for a day, `day_keys`
   gives `easter:<offset from that year's Easter>`. `feast:` keys cannot be worked out without the observances, so `day_keys` and
   `on_day` take an **`extra_keys`** argument that the calendar fills in. Without the calendar installed, a rule with a `feast` is a
   validation error (it could never be answered).
3. A helper **`describe(jdn) -> {julian: (y,m,d), gregorian: (y,m,d), weekday}`**, so every caller names a day in both calendars the
   same way.

Everything else the calendar adds is in `pangloss_calendar`.

## Julian, and both

The motivating project is Julian (1450 to 1530); a Gregorian project, or one that crosses 1582, must work too. The rules:

- **A day is a JDN, and has no calendar.** One `:CalendarDay {jdn}` node per day, whichever calendar names it. Its properties
  hold both names (`julian_year`, `julian_month`, `julian_day`, `gregorian_year`, ...) and the weekday, so a day page can say
  "2 March 1500 (Julian) = 12 March 1500 (Gregorian), Sunday" without calculation, and a month can be found by range.
- **Months and years belong to a calendar.** `:CalendarMonth {calendar, year, month, first_jdn, last_jdn}` and
  `:CalendarYear {calendar, year, ...}`; a day has one Julian month and one Gregorian month (`CONTAINS` from each). A Julian month is
  found by its two JDNs, so *the containers are for navigation and for things to attach to, not needed to find the days*.
- **Julian leap years are the 1500 case.** 1500 is a leap year in the Julian calendar and not in the Gregorian: Julian 29 February 1500
  exists (and is Gregorian 10 March 1500), and Julian 2 March is Gregorian 12 March. These pairs are the first tests.
- **Easter is computed in the calendar of the question** (Julian for a Julian project; the Julian Easter of 2000 was 17 April Julian,
  which is 30 April Gregorian, against the Western 23 April: a second test anchor).
- **Observances are defined by month and day and worked out in the calendar asked about.** Before a country adopted the Gregorian
  calendar everything is Julian; this package has **no cutover logic** (as dates has none): a project says which calendar it browses in
  (`CALENDAR_DEFAULT`, falling back to `DATES_DEFAULT_CALENDAR`), and each date says which it was written in.
- **Year style** (a year that began on 25 March) is *not* the calendar's business: dates are normalised to 1 January before they are
  stored, as `dates.md` says. The calendar shows normalised years only.
- **Leap-day feasts.** In the old Roman calendar the leap day was inserted by doubling 24 February, so feasts on or after the 24th
  (St Matthias) fall one day later in a leap year. An observance may say `leap_shift: true`. *To check against the liturgical sources
  the project uses, which decide whether it matters for 1450 to 1530.*

## The graph

Calendar nodes are not head nodes and not Entities (as `dates.md` says): no model, no creation record, no route of the usual kind. The
package makes and reads them with its own Cypher, kept in **one module** (`graph.py`) so that the Cypher is in one place.

| Node | Key | Notes |
|---|---|---|
| `:CalendarDay` | `jdn` (unique) | both names, weekday; `NEXT` to the following day |
| `:CalendarMonth` | `(calendar, year, month)` (unique) | `first_jdn`, `last_jdn`; `CONTAINS` days; `NEXT` |
| `:CalendarYear` | `(calendar, year)` (unique) | `CONTAINS` months |
| `:CalendarObservance` | `key`, e.g. `sarum:st-benedict` (unique) | a feast **definition**, below |

- **Structure by migration, nodes by command or on demand.** The package's own migration makes the constraints and indexes
  (`CalendarDay(jdn)`, the month and year keys, `CalendarObservance(key)`), and nothing else: a migration cannot know the project's years, and
  a seed of 30,000 days written by a migration is hard to repeat or extend. The nodes are made by
  `pangloss calendar seed --from 1400 --to 1600` (idempotent: `MERGE`, in batches with `UNWIND`) and, so that nothing breaks outside a
  seeded span, by `ensure_range(first_jdn, last_jdn)` which the API calls for the days it shows (a month is always made whole).
  *Changed from `dates.md`, which seeded by migration.*
- Indexed lookups: a day by `jdn`, a month by its key, a range of days by `jdn` between two numbers.
- Size: 1450 to 1530 is about 29,000 days, 960 months, 80 years (per calendar the months and years are doubled if both are used): small.

## Observances

An observance is **data**, not structure; it is loaded and corrected without a migration.

```yaml
- key: sarum:st-benedict          # unique; the prefix is the liturgical use
  use: sarum                      # Sarum, Roman, a diocese, ...
  name: {en: Benedict, la: Benedicti abbatis}
  rank: major                     # the project's own scale
  fixed: {month: 3, day: 21}      # a fixed feast ...
  # easter_offset: 49             # ... or a moveable one (Pentecost)
  leap_shift: false
```

- **Evaluation is pure** (`observances.falls_on(obs, year, calendar) -> jdn`, `observances_on(jdn, use)`), tested without a database.
  A fixed feast is `to_jdn(year, month, day, calendar)`; a moveable one is `easter(year, calendar) + offset`.
- **The graph copy** is for listing and for tagging: `pangloss calendar load-observances FILE` does `MERGE` by `key` (so a correction is
  a second run), and makes `(obs)-[:FALLS_ON {year}]->(day)` for the seeded years, so "the days St Benedict fell on between 1450 and
  1530" is one traversal, and a document can be related to a feast in a year.
- **No observance data is shipped** (decided 2026-10-29: users provide it). The loader and the file format are the deliverable, with one
  worked example (an Easter cycle and a few fixed feasts, to show the fields, in a documentation file and not in the package's data).
- Names are translations in `models.jsonc`-style slots, not code (see [translations.md](translations.md)).

## The queries and the API

All under `/api/calendar` (the package's `api.py` `router`, which `INSTALLED_APPS` picks up as for the interface and Zotero). All reads are
public in the way the lists are (unpublished documents are hidden by the same rule, because the queries go through `Model.search`, not
around it).

| Route | Gives |
|---|---|
| `GET /api/calendar/day/{ref}` | `ref` is `J1500-03-02`, `G1500-03-12` or a JDN. Both names, weekday, the observances (`?use=`), the documents dated on it, the repeated events that fall on it |
| `GET /api/calendar/month/{calendar}/{year}/{month}` | the days with their observances and the narrow dates on each (below), and the wide ones apart |
| `GET /api/calendar/year/{calendar}/{year}` | months, with counts, and the moveable feasts of the year |
| `GET /api/calendar/easter/{calendar}/{year}` | the day, and the dates that move with it |
| `GET /api/calendar/observances?use=&q=` and `/{key}/days?from=&to=` | the feasts, and where each falls |

- **Which fields hold dates** is found from the models: every field typed with a `Date` family class (or a union of them) of every
  Document and Entity class. `calendar_fields()` reads `ModelRegistry` once and caches it. A project can narrow it
  (`CALENDAR_FIELDS = ["Letter.sent", ...]`) so a calendar shows letters and not every birth date.
- **A day** is `pangloss_dates.query.on_day` over those fields, with `extra_keys` for the feasts of the day. A hit is marked **stated**
  (strict bounds hold the day) or **possible** (only the fuzzy bounds do), the two things dates already keeps apart.
- **A month** is the honest version of the uncertain-date problem: a date is placed *on* a day only if its strict range is **narrow**
  (`CALENDAR_NARROW_DAYS`, default 7); a wider range is listed in a **spanning** lane with its range. Placing a three-year range on every
  day would drown the page and say something false. The documents are found with one search per field for dates whose fuzzy bounds
  meet the month, then sorted into days in Python.
- **Speed**: the searches are by the indexed bounds but from the document (an `EXISTS` inside the search, which [dates-implementation.md](dates-implementation.md)
  notes does not use the `:Date` indexes). If a month with 100,000 dates is too slow, the fix is a query that **starts from the dates**
  (`MATCH (d:Date) WHERE d.earliest_fuzzy <= $last AND d.latest_fuzzy >= $first`, then up to the document by `head_node_id`, which every
  nested node carries) in `graph.py`, with the visibility rules of the lists reused rather than copied. Measure first, and put the
  number in this document (phase 4's exit test).

## Version 2: derived edges (a gate, not a promise)

Build only if phase 4's measurement fails, or probabilities per day are wanted (which also needs the probability maths of
`dates.md`, not built). Then, as `dates.md` says: `(date)-[:OCCURS_ON {p}]->(day | month | year)`, hierarchical for a whole month or
year, a sparse set of at most about 30 edges per date, written by a worker under a lease with compare-and-set on a hash of the
description. This needs in the **core**: (1) `:PGExternal` in `TREE_TRAVERSAL` (`build_update_query.py`), so updating a document does
not delete the days (and the delete, soft-delete, history and read paths checked for the same traversal); (2) the pending-derivation
mechanism ("derived nodes written later", in [TODO.md](../TODO.md)). The worker is a `BackgroundTask`
(`pangloss_api.background`), which exists. A `derived_hash` `DBField` on `pangloss_dates.Date` is the marker (*to check* that a
`DBField` on an Embedded is filled on write).

## Package layout

```
packages/pangloss-calendar/
  pyproject.toml          depends on pangloss-dates, pangloss-api, pangloss-core, pangloss-models, pangloss-memgraph, typer
  src/pangloss_calendar/
    days.py               describe a day in both calendars; a month's days; the next and the last        (pure, on pangloss_dates.calendar)
    observances.py        the file format, validation, falls_on, observances_on                           (pure)
    views.py              place dates in a month: narrow on days, wide in the spanning lane, stated or possible (pure)
    fields.py             which model fields hold dates (reads the registry)
    graph.py              all the Cypher: constraints, ensure_range, merge observances, FALLS_ON          (the only module that knows Memgraph)
    service.py            day, month, year, easter: put the above together; calls dates.query.on_day
    api.py                router (and configure_app only in version 2)
    cli.py                pangloss calendar seed | load-observances | status
    settings.py           CALENDAR_*
    migrations/           structure only
  tests/
```

It is added to `INSTALLED_APPS` after `pangloss_dates`. It declares **no models** (nothing for the registry, the migration planner
or the interface's model export to see), the same as for `dates.md`'s "no model for them". *To check* that an installed app with no
`models` module and its own `migrations` package is accepted by `makemigrations`/`migrate` (the memgraph package is one such case, but
check the app label).

Settings: `CALENDAR_DEFAULT` (default: `DATES_DEFAULT_CALENDAR`), `CALENDAR_FIRST_YEAR` / `CALENDAR_LAST_YEAR` (the span to browse and
to seed; **no default**, decided 2026-10-29), `CALENDAR_AUTO_EXTEND` (make days outside the span when asked, default off),
`CALENDAR_USE` (the liturgical use a view shows), `CALENDAR_NARROW_DAYS` (7), `CALENDAR_FIELDS` (default: all).

## Phases

0. **DONE 2026-10-29** (not committed): **In `pangloss-dates`**: `easter.py`; `easter_offset` and `feast` in the rule, with keys and validation; `extra_keys` on `day_keys` and
   `on_day`; `describe`. *Exit:* Easter agrees with `dateutil.easter` for both methods over 1400 to 1800 (*to check* how it labels
   the Julian result), is always a Sunday in the calendar asked for, and equals the two anchors (2000); the keys never miss (the
   existing eight-year tests, plus the new fields). *As built:* `dateutil` is not installed, so Easter is checked against printed
   tables instead (Western 1818 to 2038; Orthodox 2000 to 2025, and Julian 17 April 2000), plus the Sunday and 22 March to 25 April
   range for every year 1400 to 1800 in both calendars. `easter_offset` is limited to -80 to 250 so a day stays in the year of its
   Easter. `occurrences` takes `extra_keys_of(day)`. Not checked: Easter for years before 1400 or beyond 2038 against a table.
1. **Pure calendar** (`days`, `observances`, `views`): no database, no models. *Exit:* both names of every day 1400 to 1600 agree with
   `pangloss_dates.calendar` and `juliandate`; Julian 29 February 1500; month grids start on the right weekday in both calendars; the file
   format validates and rejects an impossible feast (30 February); the narrow/wide split on edge cases (a range of exactly 7 days).
   *As built (2026-10-29, uncommitted):* `packages/pangloss-calendar` exists with `days.py`, `observances.py`, `views.py` and 44 tests; it
   depends on `pangloss-dates` only (the other dependencies are added when they are used). Three changes from the plan: (1) the observance
   file is **TOML** (`[[observance]]` tables, read with the standard library's `tomllib`) and not YAML, which would need a dependency;
   (2) `leap_shift` applies only to fixed feasts on **24 to 28 February** (only those move when the leap day is made by repeating the 24th;
   the plan wrongly said "on or after the 24th"), and is refused elsewhere; (3) a narrow date is placed by its **strict** range, `stated`
   if one day and `possible` if a range of days, and a wide one goes in the spanning list. Days are written `J1500-03-02`, `G1500-03-12`
   or a JDN. Easter was also checked against `dateutil` for 1400 to 1800 (both methods agree; a test, skipped if `dateutil` is absent). Not done: the liturgical rule for the leap day is
   unchecked against a source.
2. **The graph**: migration (structure), `graph.py`, `seed`, `load-observances`, `ensure_range`, `FALLS_ON`. *Exit (live Memgraph):* seed
   twice gives the same counts; `ensure_range` outside the seed; a corrected observance file changes the edges and leaves one node;
   uniqueness refuses a second day.
3. **Service and API**: day, month, year, easter, observances; `calendar_fields()`; visibility. *Exit:* a live test with documents on
   Julian 2 March 1500 (an `ExactDate`, a `DateRange`, an approximate date, a `Period` that includes it, and a `Recurrence` that falls on
   it) finds each, stated or possible as it should be, and does not find a deleted or unpublished one for a reader who may not see it; the
   same in a Gregorian project (the same day by the other name).
4. **Measure and decide**: a month view over 100,000 dates on the scratch database; write the number here. If under about a second, stop
   at version 1; if not, build the date-first query; only then consider version 2.
5. **Interface** (only when you ask for it): a month page, a day page, "new document on this day" with the date filled in. The
   interface has no way yet for an installed app to add pages (its routes are in `interface-app`): deferred (decision 4 below).
6. (Gate) Version 2.

## Tests, in short

- Pure: day pairs, leap years, weekdays, Easter, observance evaluation, month grids, the narrow/wide rule; property tests that Easter is a
  Sunday and every fixed feast is a real day in both calendars.
- Live: the phases' exit tests above; plus "install without seeding" (a day page still works through `ensure_range`) and "the package
  absent" (a project without it is unaffected, and a `Recurrence` with a `feast` is refused).
- Not covered by mocks: the performance run in phase 4.

## Risks

- **Observance data** is the real work and is not code (sources, uses, the leap-day rule). The package must be useful with none loaded.
- **A calendar view of uncertain dates can mislead**: hence stated against possible, and the spanning lane. The wording of these needs
  you, for the interface strings.
- **Fields that hold dates** are found from the models, so a model change changes what the calendar shows; `CALENDAR_FIELDS` pins it.
- **Month view cost** (phase 4) and, in version 2, the memory of the edges and Year nodes as supernodes.
- **Two calendars on one day** (a Julian month and a Gregorian one containing it) must never be confused in the API: every month and year
  route carries the calendar in its path, and nothing defaults silently except `CALENDAR_DEFAULT`.

## Decisions (2026-10-29)

1. **Edges: later.** Version 1 has none; phase 5 stays a gate.
2. **Observance data is provided by the users.** The package ships the loader, the file format and one worked example, and no
   saints' calendar. (The moveable cycle from Easter, if shipped at all, is in the example file, not built in.) So `leap_shift` is
   a field users may set, and there is no question of which use to ship.
3. **Easter and `feast` live in `pangloss-dates`** (phase 0 as written).
4. **Interface: deferred.** The direction, for when it is taken up: the interface's configuration (`InterfaceConfig`) says where a
   thing is put, by "use" declarations (a **use page**, a **use section**, a **use card**, ...). A use page creates routes as well as
   placing the page. Phase 5 (the interface) waits for that; the calendar's API does not depend on it.
5. **The span is a setting.** `CALENDAR_FIRST_YEAR` and `CALENDAR_LAST_YEAR` have no default: `seed` refuses without them, and the
   browse routes answer a year outside them with a clear error (or make the days, if `CALENDAR_AUTO_EXTEND` is on). Decided to
   leave the numbers to the project.
6. **"Narrow" is a setting, `CALENDAR_NARROW_DAYS`, default 7** (see the explanation given with this decision: it only decides whether
   a date with a range of days is drawn on each of its days or listed apart in the month view).
7. **Month view computed per request** until phase 4's measurement says otherwise (not objected to).

## Not verified

The `dateutil.easter` labelling; the Julian Easter anchors beyond 2000 (the first step of phase 0 is to take them from a printed table, not from code);
whether embedded `Date` nodes carry `PGIndexableNode` (for the date-first query); whether an app with migrations and no models is accepted
by the migration commands; the liturgical rules above (leap-day shift) and any feast date; all performance claims (none are measured).
