# Dates and the calendar: uncertain dates, periods, recurrence 🚧

**Status: the original design (2026-10-21). Both packages have since been built in a narrower form, and the plans for what was built are [dates-implementation.md](dates-implementation.md) and [calendar-implementation.md](calendar-implementation.md); to use them see the guides ([dates](../guide/dates/README.md), [calendar](../guide/calendar/README.md)).** Where this page and those disagree, they are right. Not built from this design: **the probability mass over days** (a date is its four bounds, not a distribution), **relative dates**, the `OCCURS_ON` edges and the background worker that would write them (the date-first query replaced them), and the "pending derivation" mechanism. Two optional packages, `pangloss-dates` and `pangloss-calendar`, for the dates of
historical data: dates that are approximate, fuzzy, relative, or only a range; periods with uncertain ends; and
events that repeat. *To check* marks a fact about existing code or a library that
the design depends on and that has not been verified.

The motivating project works on 1450 to 1530 and keeps its dates in a **normalised Julian calendar**, but the design
is meant to be general: nothing about it belongs in `pangloss-models`, except the few small extension points under
"What the core needs".

## Two packages

> **Update 2026-10-29: observances are now entities** (`DateCharacterisation`, subclassed by the project), edged from days, months, years and spans by `CHARACTERISED_BY`, not `:CalendarObservance` nodes loaded from a file: see the [calendar plan](calendar-implementation.md).
>
> **Update 2026-10-28:** `pangloss-dates` is built ([dates-implementation.md](dates-implementation.md)), and the plan for `pangloss-calendar` is in [calendar-implementation.md](calendar-implementation.md). It changes this document in one way: version 1 has **no `OCCURS_ON` edges** (day and month views are queries over the dates' indexed bounds); the edges below are a later, measured step.

| | |
|---|---|
| **`pangloss-dates`** | The Embedded types (below), the day arithmetic, the probability maths, EDTF import and export, and recurrence rules and their expansion. Needs only `pangloss-models`. Each date stores hard bounds as integers, so **range queries work without the calendar package** |
| **`pangloss-calendar`** (optional) | The calendar nodes (year, month, day), observances (saints' days), the background worker that connects dates to the calendar, and the outward APIs and interface for browsing and tagging calendars. A project that does not want a calendar graph never installs it |

Both are added to `INSTALLED_APPS` like `pangloss_interface`. They ship their own migrations (structure, and the
seed of calendar nodes) in the way `pangloss_memgraph` does.

## The day number

Dates are kept as an integer **day number**: the Julian Day Number of a day, taken in a *normalised Julian*
calendar (the year is taken to begin on 1 January; how a source dates its year is recorded, not used for
arithmetic). An integer orders correctly, can be indexed, and does not depend on either calendar's month lengths.

- Python's `datetime.date` is proleptic Gregorian, so it is **not used**. A library for Julian and Gregorian
  conversion does the work (to check which; the conversions are short enough to write and test if not).
- The weekday is calendar independent: `(JDN + 1) mod 7` is 0 for Sunday.
- Pangloss field types are limited (`str`, `int`, `float`, `bool`, `Decimal`, `date`, `datetime`, enums,
  `TypedDict`s and lists of these). So the Embedded types below hold **integers, strings and enums**; a custom Pydantic
  type converts to and from a readable string at the edges (JSON carries `"J1503-04-02"`, with the calendar named).
- A date also records what the **source said** (`source_text="last week, probably Tuesday"`), its **calendar**
  (Julian, Gregorian), and its **year style** (1 January, 25 March, Easter, ...) for double dates ("1 Feb 1500/1").
  The evidence is kept apart from the distribution derived from it.

## The types

Easy to use for people who do not know EDTF, and all of them reduce to one internal form: **hard bounds** plus a
**probability mass over days**.

| Type | Means |
|---|---|
| `ExactDate` | A year, a year and month, or a day, in a calendar (the precision says which) |
| `DateBetween(earliest, latest)` | Hard bounds (terminus post and ante quem), uniform inside by default |
| `ApproximateDate(date, tolerance)` | "circa" |
| `DateOneOf` | Explicit weights: "Tuesday 80%, Monday 10%, Wednesday 10%" |
| `PeakedDate(range, mode, confidence)` | "last week, probably Tuesday" |
| `RelativeDate(anchor, offset)` | An offset from another date (the document's own date, an event, a death) |
| `Period(start, end)` | Each end is any of the above, or open ("ongoing"): an occupation, a role, a residence |
| `Recurrence(rule, start, end)` | A repeated event (below) |
| `EDTFDate("1500-03-?~")` | EDTF text, for experts and imports; mapped to the types above |

EDTF has qualifiers (uncertain `?`, approximate `~`, both `%`, unspecified digits `XX`, intervals, sets) but **no
probabilities**; the mapping from a qualifier to a distribution is a convention of this package, and configurable.
There is a Python `edtf` library; its coverage and its support for the Python versions in use have **not been
checked**.

Pangloss analyses nested Embedded objects (a `Period` holding two dates) and unions of Embedded types, but not
**lists** of Embedded objects: a field has one of each. Lists of integers or strings (excluded days) are fine.

## The probability maths

Each date is a probability mass function over day numbers. Everything is built from a few pieces:

- **Explicit weights**: a categorical distribution (80 / 10 / 10 exactly).
- **A smooth peak**: a two-sided geometric distribution about the mode, `p(k) ∝ r^|k|` at distance `k`, where for a
  mode that has probability `m`, `r = (1 - m) / (1 + m)`. For `m = 0.8`, `r = 1/9`: the neighbours get 8.9% each, the
  next ones 1%. Truncate to the stated range and renormalise.
- **Uniform** over a range; a **truncated normal** for "circa"; **mixtures** of these.
- **Relative dates**: the distribution of the anchor convolved with that of the offset.
- **Hard bounds** truncate and renormalise.
- **Cumulative distribution** `F(t)` for any date, which is what periods and recurrences need.

Caveats, to be stated in the user documentation: these are **degrees of belief**, not frequencies. Combining two
sources for one event (multiplying and renormalising) assumes independent evidence and can contradict (no overlap).
The distribution depends only on the **stored description** of a date (and, for a relative date, on the description
of its anchor), never on other dates' derived data, so it can always be recomputed.

## Periods

`Period(start, end)`: for a role or an occupation, `start` and `end` are each a date of any type above, or open. The
probability that the period includes a day `t` is `P(start <= t) * P(end >= t)` (independent ends). The probability
that two periods overlap (were two people in office together?) is computed in Python from the two pairs of
distributions, not in Cypher.

## Recurrence

"Maximilian orders a mass to be said every third Sunday of March" did not go on for ever, and should repeat on given
days. A standing order is modelled as a **rule plus a fuzzy lifetime**, not as a list of occurrences:

`Recurrence(rule, start, end)`

- `start` and `end` are ordinary dates of the types above ("from about 1505", "until he died": an end can be
  relative to another date, such as someone's death; an open end needs a **horizon** so it can be indexed).
- `rule` is a small structured vocabulary taken from iCalendar's `RRULE`: weekly on given weekdays, monthly on the
  *n*th weekday (`FREQ=MONTHLY;BYMONTH=3;BYDAY=3SU` is the third Sunday of March), yearly on a month and day. Plus what
  early modern rules need: yearly on a **feast** (looked up in the observances), yearly at an **offset from Easter**
  (the Julian computus), and a list of **excluded days** (integers).
- A rule that is itself uncertain ("the first or the third Sunday") is a mixture of weighted rules, as `DateOneOf` is.
- `dateutil.rrule` works on Gregorian `datetime`s, so it cannot expand these; the package has its own expander over
  day numbers and borrows the `RRULE` syntax. (Whether any library expands recurrences in the Julian calendar has not
  been checked.)

An instance on day `t` is real if the order was in force: `P(start <= t) * P(end >= t)`. The same cumulative
distributions as periods give it.

Three different things are kept apart: the **standing order** (the rule, from the foundation document); **attested
occurrences** (a payment record for one mass on one day: ordinary documents with ordinary dates, linked to the rule
as `occurrence_of` if wanted); and a **lapse** (evidence that it stopped earlier: a new, earlier `end`, or an exclusion).

### Not expanding, but inverting: "everything on this date"

Occurrences are never stored, and a point query never expands a rule. For a day `D`:

1. **Bounds.** Each rule has indexed integers: the earliest possible start and the latest possible end. A range
   lookup keeps only the rules that could be in force on `D`.
2. **Patterns.** Each rule is attached to one or two **pattern** nodes (`every Sunday`, `3rd Sunday of March`,
   `21 March`, `Easter + 14`, `feast: St Benedict`): a small fixed set, a few hundred to a thousand, so a rule never
   connects to thousands of days.
3. A pure function turns `D` into **its pattern keys** (weekday, month and day, the ordinal weekday in the month,
   the offset from that year's Easter, the feasts that fall on it, from the observances of the chosen use). `MATCH` those
   patterns, follow their rules, apply the bounds, and **verify the exact rule** on the few candidates (this
   covers rules the pattern only approximates, such as Sundays in March, and the excluded days).
4. Compute each survivor's probability of being in force on `D`, in Python, from the stored descriptions; add the
   ordinary dated items for the day.

A **month calendar** is the same join: the days' pattern keys joined once to the rules, grouped by day. Nothing loops
over rules. The pattern edges are derived data (below); without `pangloss-calendar` the same query works by scanning the
rules in the bounds range and testing the predicate in Python (fine up to something like 100,000 live rules; an
estimate, not measured).

## The calendar (in `pangloss-calendar`)

**Calendar nodes are not head nodes and not Pangloss entities.** There is no model for them; the package creates and
queries them with its own Cypher, and adds its own routes (as the interface does under `/api/interface`).

- Labels `:CalendarYear`, `:CalendarMonth`, `:CalendarDay`, each with a unique integer key (the day number, or year
  and month), and `CONTAINS` edges down and `NEXT` between days. For 1450 to 1530 that is about 29,000 days, 960 months
  and 80 years: tiny. Indexes and constraints are created by the package's migration, and the nodes by a batched
  `RunPython` seed.
- **Observances** (saints' days and the like) are `:CalendarObservance` nodes joined to days, not properties of
  them: a day can have several, and they differ by liturgical use and diocese (Sarum, Roman, ...). Moveable feasts are
  computed from the Julian Easter for each year. They are data, not structure: loaded by an idempotent command
  (`pangloss calendar load-observances`, using `MERGE`), so a list can be corrected without a migration.
- **Feast descriptions are documents "about a day"**: a document with an `ExactDate` field, found through the day's
  link to that date (probability 1). It does not need a relation to a Day node. (The alternative, making Day, Month and
  Year real Entities, was rejected: 30,000 entities with creation records and routes, and the reverse-field problem.)

### Connecting dates to the calendar

A date node is connected to the calendar by `(date)-[:OCCURS_ON {p}]->(Day | Month | Year)`:

- **Hierarchical edges.** A whole-year date points at its Year with mass 1, a whole-month one at its Month; queries
  split the mass uniformly down to the days. That is valid only where the distribution is uniform inside the unit; a
  non-uniform distribution gets day edges. So a date stores a **sparse set of (unit, mass)** pairs with a cap of about
  30.
- **Derived, in the background.** The synchronous write computes only what is cheap and pure: validation, the
  **bounds**, and a `spec_hash` of the description. The edges are written later by a worker; they are not needed to
  be read at once (the target is seconds for one edit; a bulk upload takes as long as it takes).
- **The marker** is a literal field on a shared base `Date` class (something like `derived_hash`, which the worker sets
  to `spec_hash`): pending means `derived_hash <> spec_hash`. Every subclass node carries its parents' labels, so one
  label-and-property index on `:Date(...)` finds the pending work. It looks like what `DBField` is for (*to check* how
  DB fields are filled). The alternative, a `:BackgroundJobPending` label, would need a core hook for labels on Embedded
  nodes. No job nodes (a million dates would be a million nodes).
- **The worker** runs as a task in `pangloss run`, or as `pangloss calendar worker`. It claims a batch (a lease,
  `claimed_until`, so a crashed worker's work returns), computes outside a transaction, then in one transaction deletes the
  date's old `OCCURS_ON` edges and creates the new, **only if `spec_hash` still matches** (compare and set). If the document
  was updated meanwhile the node is gone or has a new hash, and the stale result is not written. An update **cancels its
  pending work for free**: replacing the tree deletes the node with its marker and edges. The worker backs off while a
  migration runs (writes are refused then).
- **What you see**: calendar views are eventually consistent. Show a count of dates still being indexed, and a
  `derived_at`. Range queries, which use the bounds, are exact at once.
- Pattern edges for recurrences are derived in the same way, from a rule's own hash.

## What the core needs

Small and general; none is specific to dates.

1. **Nodes a document does not own.** `build_update_query.py` treats everything reachable from the head node by
   forward edges as owned by it (the traversal skips only `:Entity` and `:PGUrl` nodes, and edges marked `reverse`) and
   `DETACH DELETE`s it on update. A forward edge from a date to a `CalendarDay` that is not an `Entity` would put the
   day in the document's tree, and **updating any document with a date would delete the calendar** (then its months and
   years). Fix: one marker label (say `:PGExternal`) added to the exclusion in `TREE_TRAVERSAL`, put on the calendar
   nodes. (A workaround without a core change is writing the edge as `reverse: true`, which bends the flag's meaning.)
2. **Pending derivations**: a mechanism (a registered handler per kind, the index on the marker, a worker loop with
   a lease and a compare-and-set on a hash, back-off while migrating) that the "derived nodes written later as a
   background job" item in [TODO.md](../TODO.md) also wants. Built once in core, used by dates; the guard answers the race
   conditions that item mentions in the old `DeferredQueryRunner`.
3. **A way to add routes and commands from an installed app**: exists (`INSTALLED_APPS`, `cli.py`, `api.py`).
4. Possibly an **option to leave out the reverse field** of an entity or an Embedded relation: not needed if the
   calendar nodes are not entities (the head view lists every incoming relation, unpaged).

## Interactions

- **[Migrations](migrations.md)**: the Embedded types are ordinary models, so changing a field is an ordinary migration.
  The calendar's structure and seed are the package's own migrations; changing a *convention* (the "circa"
  tolerance, the rule vocabulary) means recomputing derived data: a `RunPython` that clears the derived hashes so the
  worker rebuilds.
- **[History](history.md)**: a date is part of its head node's snapshot as its description (not its derived edges),
  so restoring a version restores the description and the worker derives the edges again.
- **Reading back**: whether the normal read path ignores edges that no declared field covers (the `OCCURS_ON`
  edges) is *to check*.

## Testing

- The day arithmetic against known Julian and Gregorian pairs, including 1500, and the weekday rule.
- Each distribution: it sums to 1, truncates and renormalises, the geometric peak gives `m` at the mode, the
  convolution of a relative date, the cumulative distribution; a property test that every type reduces to bounds
  that contain all the mass.
- EDTF: a table of strings to types and back.
- Periods: the in-force and overlap probabilities against a brute force sum.
- Recurrence: the expander against hand-worked months (third Sunday of March, across 1500); excluded days; a rule
  with an open end and a horizon; the inverted lookup against expanding every rule in a small data set (they must
  give the same days).
- The worker: a stale result is not written; an update cancels pending work; a crash returns the lease; it backs off
  during a migration; the update-then-calendar-survives test for the traversal exclusion.
- Not covered by a mock: a run against the real Memgraph with tens of thousands of dates (the memory of the edges is
  the cost to measure).

## Phases

1. **`pangloss-dates`, without a database**: the day arithmetic, the distributions, the EDTF mapping, the bounds, the
   recurrence expander and the point-in-force function. Pure Python, easily tested.
2. **The Embedded types** with bounds-only storage, and range and overlap queries (including the recurrence scan).
3. **Core**: the `:PGExternal` exclusion, then the pending-derivation mechanism.
4. **`pangloss-calendar`**: the calendar nodes and seed, the observances, the worker, the pattern nodes, and the calendar
   queries and routes.
5. The interface: calendar views, tagging, and the editing of a date's description.

## Open questions

- Which library for day arithmetic and for EDTF (coverage, maintenance, Python versions).
- The exact conventions: tolerance for "circa" by precision, how a source's year style is recorded and shown.
- Liturgical uses to ship observances for, and where the data comes from; whether a use may be chosen per query.
- The horizon for an open-ended recurrence or period.
- Whether `occurrence_of` (attested occurrences linked to a rule) is in the first version.
- Whether the base `Date` class can be a plain Embedded with a DB-written field today (*to check*), and where the hook for
  edges would attach if a synchronous version is ever wanted (`QueryObject` collects `match_query_strings` and
  `create_query_strings`).
- Memory: the number of edges per date and the supernode problem (a Year or a popular pattern with very many edges);
  measure with a realistic load before fixing the cap.
