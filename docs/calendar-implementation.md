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

## Characterisations (replaces "observances", 2026-10-29)

*The first version of this plan, and the code up to phase 4, had feasts as `:CalendarObservance` nodes loaded from a TOML file. Decided
with the owner on 2026-10-29: they are entities instead.*

`pangloss_calendar.models.DateCharacterisation` is an **abstract entity** (so the package has a model after all: abstract, no
migration of its own). A project subclasses it for what it needs (`FeastDay`, a term day, a market day); a subclass is an ordinary
entity with the API, history, translations and relations that any has. Its fields: `use`, `rank`, and `when: Recurrence | NoRule`.
`NoRule` (an Embedded with no fields) is for one attached by hand: *a list of rules, and an optional embedded, are not supported by the
models, so the choice is made explicit*. A feast with two days in the year (the translation as well) is two entities.

- **By rule.** A `Recurrence` (pangloss-dates) is the rule: 21 March, the third Sunday of March, `easter_offset` 49, over a lifetime
  ("observed 1450 to 1530"), in **its own calendar** (21 March Julian is not 21 March Gregorian). `characterisations.days_between`
  works a yearly rule out year by year, not day by day (checked against trying every day); `falls_on_day` checks one day. A repeated
  event of another model can fall on a characterisation with `feast = "<its id>"`.
- **By hand.** `POST /api/calendar/attach` (logged in) attaches one to a **day**, a **month** or **year** (of a calendar), or a **span** of
  days (`:CalendarSpan {first_jdn, last_jdn}`, made when needed, in no calendar: a week, Lent, a term). A month or year covers its days
  without copying: the day view and the month view look at the day's own edges and those of its month, year and any span that
  contains it. `POST /api/calendar/detach` takes it away.
- **The edges.** `(:CalendarDay|CalendarMonth|CalendarYear|CalendarSpan)-[:CHARACTERISED_BY {origin: 'rule' | 'manual'}]->(characterisation)`.
  `origin: 'manual'` edges are never touched by the package except `detach`. `origin: 'rule'` edges are **derived** and made by
  `pangloss calendar link` (and by `seed`), which deletes and remakes all of them: they are stale after an entity is changed until the
  next run, because the core has no hook after a write. **The views do not use the rule edges** (they work the rules out), so a stale
  edge never gives a wrong day or month page; the edges are for graph questions ("every day Benedict fell on").
- **Not supported yet:** a rule that repeats a *span* (Lent every year): `Recurrence` repeats single days. (Leap-day shifts of feasts on 24 to 28 February are supported: `leap_shift` on the rule, in `pangloss-dates`.)
- **No data is shipped** (decided 2026-10-29: users provide it). To load a list, create the entities through the API or the SDK.

### The span, the margin and what is out of reach

`CALENDAR_FIRST_YEAR` and `CALENDAR_LAST_YEAR` (no default) are the span of the calendar. **The reach** is the span with
`CALENDAR_EXTEND_MARGIN_YEARS` (default 10) either side.

- **Just outside the span (inside the margin): the calendar grows.** `link` and `attach` make the days they need (only the days needed,
  with their months and years), so a rule that starts in the year before the span, or a day attached 5 years past it, just works and the
  graph now has those days.
- **Well outside (beyond the margin): nothing is made.** `link` leaves the days outside the reach unlinked and says so (*`clipped`*: a rule
  with a lifetime that goes beyond the reach has only the days inside it linked; *`outside`*: a rule wholly beyond it has none); `attach`
  refuses with 422. So the author of a medieval text who is in the project because he wrote one, with his birth in 384 BC, has no place
  in the calendar's graph. Dated documents are never linked to the calendar at all in version 1 (the views find them by their dates), so
  nothing was ever going to put him there: the rule only governs characterisations.
- The day, month, year and Easter views are worked out, not read from the graph: they answer for any year, in or out of reach. (If a
  project wants them refused outside the reach too, that is one check in the service: not done, and not asked for.)

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
| `GET /api/calendar/characterisations?use=&q=` and `/{id}/days?from=&to=` | the characterisations (feasts and the like), and where each is, by rule and by hand |
| `POST /api/calendar/attach`, `POST /api/calendar/detach` (logged in) | attach a characterisation to a day, a month, a year or a span, and take it away |

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
    models.py             DateCharacterisation (abstract entity) and NoRule
    characterisations.py  the days a characterisation's rule falls on                                   (pure)
    views.py              place dates in a month: narrow on days, wide in the spanning lane, stated or possible (pure)
    fields.py             which model fields hold dates (reads the registry)
    graph.py              all the Cypher: constraints, ensure_range, characterisations, edges, date-first query (the only module that knows Memgraph)
    service.py            day, month, year, easter: put the above together; calls dates.query.on_day
    api.py                router (and configure_app only in version 2)
    cli.py                pangloss calendar seed | link | status
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

*Read the phase notes below as history where they speak of observances, `load-observances`, `FALLS_ON` or the TOML file: those were replaced by characterisations (above) on 2026-10-29.*


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
   *As built (2026-10-29, uncommitted):* `migrations/0001_initial.py` (hand-written: an index and a unique key for each of the four node
   kinds), `graph.py`, `cli.py` (`seed`, `load-observances`, `status`), `settings.py`; the package now depends on `pangloss-memgraph` and
   `typer`. 7 live tests (in `pangloss-memgraph/tests/test_calendar_live.py`, which has the database fixtures) and 3 for the refusals.
   Measured on the test Memgraph: **1400 to 1600 (73,416 days) seeds in 2.8 s**; a second seed writes nothing and takes no time; a
   missing month is made in 6 ms. Decisions made on the way: `FALLS_ON {calendar, year}` is made only for the calendars asked
   (`--calendar`, default `CALENDAR_DEFAULT`), so a Julian project gets no Gregorian edges; `load-observances` and `seed` delete and remake
   the edges of those calendars, so a correction leaves none stale; a month's node exists with its whole `first_jdn`/`last_jdn` even when
   only some of its days do (the Gregorian months at the edge of a seed). *Found:* a `MATCH (b {jdn: a.jdn + 1})` is not an index
   lookup in Memgraph (it scanned every day for each pair; 73,000 days did not finish): the pairs are made in Python and
   `UNWIND`ed. *Not checked:* `makemigrations --check` and `migrate` through the real commands with `pangloss_calendar` in
   `INSTALLED_APPS` (the migration was applied through `apply_changes`, twice, with the same result); seeding on the 642k-node database.
3. **Service and API**: day, month, year, easter, observances; `calendar_fields()`; visibility. *Exit:* a live test with documents on
   Julian 2 March 1500 (an `ExactDate`, a `DateRange`, an approximate date, a `Period` that includes it, and a `Recurrence` that falls on
   it) finds each, stated or possible as it should be, and does not find a deleted or unpublished one for a reader who may not see it; the
   same in a Gregorian project (the same day by the other name).
   *As built (2026-10-29, uncommitted):* `fields.py` (`calendar_fields`, with `CALENDAR_FIELDS` narrowing; a date inside an embedded object is
   not searched), `service.py` (pydantic reports: `day`, `month`, `year_report`, `easter_report`, `find_observances`, `days_of_observance`)
   and `api.py` (the six routes of the table above). 5 live tests in `pangloss-memgraph/tests/test_calendar_service_live.py`, including the
   exit test (an `ExactDate`, a `DateRange`, an approximate date, a `Period` and a weekly `Recurrence` on Julian 2 March 1500; found
   `stated` or `possible`; the Gregorian name of the day gives the same answer; an unpublished document is found only by a reader who may
   see it, a deleted one by none) and the routes through ASGI. Things that are as they are: **`stated` means the strict bounds hold the
   day** (so an approximate day "about 6 March" is `possible` on the 2nd, a range 1 to 3 March is `stated` on the 2nd; in the month view a
   *range* is drawn `possible` on each day, by the rule in `views.py`, which is a different question: whether the event was on that day
   for sure); a month is filled from the **strict** range only; a month reads each date's document (`Model.get`, 8 at a time) to learn its
   range, up to `MONTH_LIMIT` a field, and says `truncated` if more (replaced by the date-first query below, after phase 4);
   the days need not be in the graph (the answer is worked out; `CALENDAR_AUTO_EXTEND` makes them as they are asked for); the feasts are
   read from the graph on each request. *Not done:* the year's counts per month (the year gives the months, Easter and the moveable
   feasts); a project without `pangloss_calendar` (`feast` rules are not refused there yet); `pangloss_calendar` through
   `INSTALLED_APPS` in a running server.
4. **Measure and decide**: a month view over 100,000 dates on the scratch database; write the number here. If under about a second, stop
   at version 1; if not, build the date-first query; only then consider version 2.
   *Measured (2026-10-29, test Memgraph on :7687, 100,000 documents each with one Julian date, written straight as Cypher in the shape the models
   write; 70% one day, 15% a month, 10% a range of 2 or 3 days, 5% a year; spread over 1490 to 1510):* a month of about 700 dates
   (380 on days, about 290 spanning) takes **1.1 to 1.5 s**; a day with 310 hits **1.2 s**. Of a month, **about 0.9 s is the two searches** (a
   single-date search and a recurrence search over the field; the `EXISTS` inside `Model.search` that dates-implementation.md predicted does not use
   the `:Date` indexes) and **0.3 to 0.5 s is reading the 614 documents** (`Model.get`, 8 at a time). Worst case, all 100,000 in one month: **3.3 s** for the
   month (cut at `MONTH_LIMIT`, `truncated: true`), 2.8 s for the day. **The day silently stops at 1000 hits** (`on_day`'s `limit`), with no
   flag: to fix whichever way phase 4 goes. *Decision rule of this plan:* over about a second, so build the date-first query (below) before
   anything else; it would remove the 0.9 s of searching, and with the dates it finds it can read the bounds in the same query, which also removes
   the 0.3 to 0.5 s of reading documents. Version 2 (edges) is not needed. *Not measured:* the 642k-node scratch database (the cost is in the
   dates' own count, not in the other nodes, but this was not shown), real labels and real distributions, a project with several date fields.
   *Date-first query built (2026-10-29, uncommitted):* `graph.dated_between(label, field, first, last, strict, keys, limit)` starts from the dates
   (`MATCH (d:Date)` on the fuzzy bounds, which have the index, then the strict bounds as a filter), goes to the node by the edge named
   for the field, to its head for `deleted`/`published` (the same `$see_unpublished` as the lists), and returns the bounds and a repeated
   event's rule in the same query, so no document is read (`service.py` no longer uses `Model.get`, `on_day` or `pages`). A repeated event is
   a candidate by its lifetime and, for a day, by `pattern_keys` against `day_keys`; the exact rule is then checked in Python. Same
   answers (380 on days, 297 spanning, 310 on the day) and, on the same 100,000 dates: **month 0.06 to 0.08 s (was 1.1 to 1.5 s); day 0.06 s
   (was 1.2 s); all 100,000 in one month 0.6 s (was 3.3 s), cut at `MONTH_LIMIT` (now 20,000 a field) with `truncated: true`**; the day
   report has `truncated` too (it stopped silently at 1000). Under the line, so **version 1 stands and version 2 (edges) is not built.** Not
   covered: the `review_status` filter of the lists (the calendar shows documents whatever their review status, as long as they are
   published); a date in an embedded object (only the edge from the node itself is followed).
   *Characterisations built (2026-10-29, uncommitted):* `models.py`, `characterisations.py`, `graph.py` (read, `manual_between`, `attach`/`detach`,
   `link_rules`, `CalendarSpan`), `service.py`, `api.py` (`/characterisations`, `/attach`, `/detach`, with the day, month, year and
   Easter reports carrying them), `cli.py` (`seed`, `link`, `status`; `load-observances` and `observances.py` removed), the settings
   `CALENDAR_EXTEND_MARGIN_YEARS`, and migration 0001 changed (a unique key on `CalendarSpan` instead of `CalendarObservance`: never
   applied anywhere but the test database). Tests: 35 pure and CLI in `pangloss-calendar`, and 14 live (`test_calendar_live.py`,
   `test_calendar_characterisations_live.py`, `test_calendar_service_live.py`): the rules linked inside the span and the margin with the
   days made to fit and a rule wholly outside left alone; relinking after an edit keeping what was attached by hand; day, month, year and span
   attached and taken away; an attachment beyond the reach refused; the API with login. Found on the way: **a rule's keys were being
   worked out in the calendar the page is read in**, so a Julian yearly rule read under a Gregorian day name could be missed: the keys
   are now those of both calendars and the rule is checked in its own (test: a Julian "2 March" read as G1500-03-12). *Not done:* a rule
   that repeats a span; the leap-day shift; edges that follow a change by themselves (`link` by hand); `review_status` filtering;
   `pangloss migrate` through the real command with the app installed (the abstract model should need none: *to check* with a
   project that subclasses it and runs `makemigrations`).
   *Finishing (2026-10-29, uncommitted):* (1) **`leap_shift`** is a field of `RecurrenceRule` and `Recurrence` (yearly, fixed day 24 to 28 February; a day later in a
   leap year; its `pattern_keys` has both days; tested against trying every day, and refused elsewhere). (2) **A rule on a `feast`** is refused unless
   `pangloss_calendar` is installed, and its value must be the id of a characterisation. (3) **The year report counts** the dates that meet each month.
   (4) **Migrations, found by running `makemigrations` in a project that subclasses `DateCharacterisation`:** without work, the planner would
   *drop* the calendar's indexes and keys (it knew only the database package's structure) and would write the models' migrations *into the
   installed packages*, and a server would refuse to start (`MIGRATION_CHECK`). So: an installed app may have a `structure` module with `INDEXES` and
   `CONSTRAINTS` (`pangloss_memgraph.initialise_database.installed_app_structure`, read into the snapshot), and **`pangloss-dates` and
   `pangloss-calendar` ship their migrations** (`pangloss_dates.0001_initial`; `pangloss_calendar.0001_initial` by hand, `0002` for `DateCharacterisation`
   and `NoRule`, both written by `makemigrations`). Tried for real in a throwaway project on the test database: `migrate` applies all of them,
   `makemigrations --check` says no changes, `pangloss calendar seed | link | status` run, and `pangloss run` starts ("the database and the models
   agree with them"), serves `/api/calendar/...` and answers an attach without a login with 401. *The same is true of every other
   package with models (zotero, review, history...): none ships migrations yet, so `makemigrations` in a project that installs them writes
   them into the package; that is outside the calendar and is not changed here.*
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
