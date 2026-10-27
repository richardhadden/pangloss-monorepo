# Dates: the implementation plan for `pangloss-dates` ⏳

**Status: a plan, nothing built (2026-10-27).** This narrows [dates.md](dates.md) to what is built first: the date
types with four stored bounds, a Julian day number, and EDTF as an input option. The probability maths, recurrence,
and the calendar package stay in `dates.md` for later. *To check* marks a fact about code not yet verified.

## What was asked for

- A **single date**: precise (year, year and month, or a day), or given as an EDTF string.
- A **date range** standing for one date whose day is not known: an earliest and a latest.
- A **period** (a person holds a job): a start and an end, each precise or a range (or open).
- Nobody is expected to write EDTF; it is an option.
- On save, the date holds four bounds: earliest possible, earliest *likely*, latest *likely*, latest possible.

## How EDTF fits with the Julian calendar

Checked on 2026-10-27 (`edtf` 5.0.2, Python >= 3.10, and it runs on 3.15.1):

- EDTF itself names no calendar: a date is year-month-day, and the standard assumes Gregorian. For 1450 to 1530 the
  sources are Julian, so the **calendar is a separate field of ours** (`julian` by default), never part of the string.
- `python-edtf` is a **parser with Gregorian bounds**. `parse_edtf("1500-02").upper_strict()` is `(1500, 2, 28)`;
  in the Julian calendar 1500 is a leap year and February ends on the 29th. Its bounds are wrong for us and cannot be
  switched to Julian. It returns `struct_time`-like tuples and has no day number.
- Its **fuzzy** bounds (`lower_fuzzy`, `upper_fuzzy`) pad "arbitrarily by 100% of the uncertain timescale" (`1500~`
  gives 1499 to 1501; `1500-03-02?` gives 1499-02-01 to 1501-04-03). Useful as a starting convention, not as truth.
- It rejected `1500-03-?~` (a Level 2 mix) and `1450-02-30` (not a date). Its coverage of Level 2 is to be tested.

So the plan is: **use `edtf` only to parse** (qualifiers `?`, `~`, `%`, `X`, intervals, sets, seasons) into a tree,
then **our own code turns each part into day numbers** in the chosen calendar. This also means `edtf` can be an
optional dependency (an extra: `pangloss-dates[edtf]`), and we write and export EDTF for the simple cases ourselves
(*decision below*).

## Julian calendar libraries

| | Checked | Verdict |
|---|---|---|
| `juliandate` 1.0.5 (Python >= 3.8) | `from_julian(y,m,d)`, `to_julian(jd)`, `from_gregorian`, `to_gregorian`; returns a **float Julian Date** (noon-based: `2268983.5` for 1500-03-02 Gregorian), `from_julian(1500,3,2)` is 10 days later | Does the right conversion. Floats and a .5 offset are awkward, and it has no weekday or month length |
| `JulianPy` 1.0.1 (2023, one commit) | datetime to Julian Date; no Julian-calendar dates | Not what is needed (it is a Julian *Date*, not the Julian *calendar*) |
| our own | | The conversions are about 30 lines (the standard integer algorithm for the Julian calendar, and for Gregorian), plus month length and leap year |

**Recommendation: write our own** `pangloss_dates.calendar` (integer algorithms, exact, no floats), with
`juliandate` used **only in the tests** as an independent check. It is the one thing everything else depends on, it is
small, and we need month lengths and the weekday anyway.

## The day number

An integer **Julian Day Number** (days, no fraction): `jdn(1500, 3, 2, calendar="julian")`. An integer orders, indexes,
and adds. `to_date(jdn, calendar)` goes back. The weekday is `(jdn + 1) % 7` (0 = Sunday), whichever calendar.
Gregorian is supported as a calendar value so data from after 1582 (or from sources that use it) is not forced to
Julian; **no cutover logic** (a date is in one calendar, and says which).

## The four bounds: names

For a date, the descriptions are the **evidence**; the bounds are **derived** from them and stored for range queries.

| | Meaning |
|---|---|
| `earliest` | The first day it can possibly be (hard: a terminus post quem) |
| `latest` | The last day it can possibly be (terminus ante quem) |
| `earliest_likely`, `latest_likely` | The range holding the usual reading: where the source's own words place it, before allowing for doubt |

"Conservative" is the wrong word (it suggests careful, not narrow). Options: **likely** (recommended, plain and
does not claim a probability), **probable**, **core**, **inner** and **outer**, or **strict** and **fuzzy** (which is
what EDTF calls them, `lower_strict` and `lower_fuzzy`; but "fuzzy" reads as vague). Field names:
`earliest`, `earliest_likely`, `latest_likely`, `latest`, always with `earliest <= earliest_likely <= latest_likely <= latest`,
checked on save.

How each input type fills them:

| Input | `earliest` / `latest` | `*_likely` |
|---|---|---|
| Precise day | that day | the same day |
| Precise month or year | first and last day of it | the same (the whole month is what is stated) |
| Range (earliest, latest) | the stated ends | the same, unless a likely range is given |
| EDTF `1500~` (approximate) | strict range padded by the convention (default: one unit of the precision, a year for a year) | the strict range |
| EDTF `1500-03-02?` (uncertain) | padded the same way | the strict range |
| EDTF `1500-XX-XX`, `15XX` (unspecified digits) | the full span | the full span |
| EDTF interval `a/b` | in a **Period**, not a date | |
| EDTF set `[1500,1502]` | earliest to latest of the members | the same |

The padding is a **setting** (`DATES_APPROXIMATE_PADDING`, per precision), and the stored bounds change only when the
date is saved again, so changing the convention is a migration that re-saves (as `dates.md` says).

## The types (embedded)

All are `Embedded` (a separate node written with its container). A field can be a union (`SingleDate | DateRange`),
but not a list or `X | None` (*current limitation, models.md*), so "no end" is a value, not a missing field.

```
Date            base: the four bounds + calendar + source_text + precision (all derived or recorded)
  ExactDate     year, month=None, day=None            -> "1500", "1500-03", "1500-03-02"
  EDTFDate      edtf="1500-03-02?"                    -> parsed by python-edtf
  DateRange     earliest: parts, latest: parts        -> bounds from the ends (and a likely range, optional)
Period          start: Date types, end: Date types or open ("ongoing")
```

- `Period` holds the **start** and **end** as embedded objects (a nested Embedded, which is supported). It stores its
  own four bounds too: `earliest` = start's `earliest`, `latest` = end's `latest` (or a horizon if open), so a period
  can be range-queried without opening its ends. Open ends need `is_open: bool` and the horizon setting.
- `calendar` (`julian` | `gregorian`) and `source_text` (what the source said) are ordinary literal fields on `Date`.
- `precision` (`year`, `month`, `day`, `range`) is derived and stored (useful to display and to filter).

### What is typed and what is derived

The bounds must be written by Pangloss, not typed by a client. Two ways (*to check* which the models allow today):

1. They are `DBField`s (written to the database, left out of client models), filled by a hook on write.
2. They are normal fields filled by a `model_validator(mode="after")` on `Date`, so they exist on the `Create`
   model, are recomputed whatever the client sends, and appear on read.

(2) is easier to test in pure Python and is needed anyway for the validation of the input (`month` 1 to 12, a day
that exists in that month and calendar, `earliest <= latest`). (1) is cleaner for clients. **Recommendation: validator
that always overwrites the bounds, with the fields on read only**; if `Embedded` validators do not reach the generated
`CreateDB` model (*to check*, `initialise_models/common.py` `get_model_validators` has a per-kind switch), that
is the first thing to fix in core.

## Querying

Because the bounds are integers on the date node, **range queries work now**, with the structured search:

- "documents dated within 1500-03" is `earliest_likely >= a` and `latest_likely <= b`; "could be in" is `earliest <= b`
  and `latest >= a`.
- It uses the existing `Condition` operators (`gte`, `lte`, `between`) on the embedded date's bounds; **no search
  change is needed** provided nested embedded patterns work as relations (they do for Embedded objects, *to confirm
  in a live test*).
- `Meta(indexes=["earliest", "latest"])` is for documents; an index on an Embedded's property is not covered by the
  index feature (it takes document and entity classes only) -- *a small extension, a question below*.

The `Condition` takes JSON-friendly values, so the search accepts a day number; the string form `"J1500-03-02"` is
turned into one by the SDK and interface helpers (`pangloss_dates.parse`).

## Package layout

```
packages/pangloss-dates/
  src/pangloss_dates/
    calendar.py     jdn <-> (y, m, d), month length, leap year, weekday     (pure)
    parts.py        DateParts(year, month, day, calendar) -> (first_day, last_day)   (pure)
    bounds.py       Bounds(earliest, earliest_likely, latest_likely, latest) + checks + padding convention (pure)
    edtf.py         parse with python-edtf into parts + qualifiers; our own writer for simple cases (pure)
    models.py       Date, ExactDate, EDTFDate, DateRange, Period (Embedded)
    settings.py     DATES_* settings
  tests/
```

`pangloss-dates` depends on `pangloss-models`; `edtf` is an optional extra. The pure parts import nothing from
Pangloss, so phase 1 is testable without a database or model registry.

## Phases

1. **`calendar.py`**: integer conversions both ways; month lengths; weekday. Tests: a table of known Julian and Gregorian
   pairs (1500-03-02 Julian = 1500-03-12 Gregorian = JDN 2268994), every day from 1400 to 1600 round-trips, agreement
   with `juliandate` over all those days, 1500 is a Julian leap year and not a Gregorian one, weekday.
2. **`parts.py`, `bounds.py`**: parts to bounds, validation (no 30 February, 29 February only in leap years of the
   calendar), the four-bound invariant, the padding convention. Property tests: for random input the invariant holds
   and the stated day is inside both ranges.
3. **`edtf.py`**: a table of EDTF strings to bounds, and the Julian month-end case that `python-edtf` gets wrong
   (`1500-02`). Which Level 1 and 2 forms are accepted, and the errors for the rest (a clear message, not a traceback).
4. **`models.py`**: the Embedded types; the validator that fills the bounds; a document with each type created, read
   back and updated (live test on Memgraph); the structured search by a range of days.
5. **Index extension** if wanted, a doc page for the user guide, and the settings docs.
6. (Later, as in `dates.md`) probability mass, relative dates, recurrence, the calendar package.

## Decisions (2026-10-27)

- **Bound names: EDTF's words, `strict` and `fuzzy`.** In `python-edtf` *strict* is the range as stated and *fuzzy* is
  that range padded for doubt, so the four fields are, in order, `earliest_fuzzy`, `earliest_strict`, `latest_strict`,
  `latest_fuzzy`, with `earliest_fuzzy <= earliest_strict <= latest_strict <= latest_fuzzy`. Everywhere above,
  read `earliest` as `earliest_fuzzy`, `latest` as `latest_fuzzy`, and `*_likely` as `*_strict`. A hard
  terminus post or ante quem (a stated range's ends) is *strict*; padding by the approximate convention is *fuzzy*. The
  docstring says plainly that "fuzzy" means "allowing for doubt", not vague.
- **Calendar code: our own**, `juliandate` only as a test check.
- **EDTF: an optional extra that parses only**; bounds are computed by our code in the chosen calendar.
- **Bounds: a validator that always overwrites them**, fields read-only for clients. First check whether `Embedded`
  validators reach the generated models; fix in core if not.
- **Not yet decided: indexes on an Embedded's bounds.** Default: not now; range search works without, measure first.

## Changes of 2026-10-27 (later): indexes, recurrence, a sort date

### Indexes on the date bounds: yes

`Meta(indexes=[...])` takes only Document and Entity classes (`pangloss_models/indexes.py`, `indexed_classes`). Extend
it to **Embedded**: the same label index per class and `Meta(indexes=[...])` for label-and-property indexes. Every
subclass node carries its parents' labels, so the base `Date` class declares

```python
class Date(Embedded):
    _meta = Embedded.Meta(indexes=["sort_day", "earliest_fuzzy", "latest_fuzzy"])
```

and one index on `:Date(...)` serves `ExactDate`, `DateRange`, `EDTFDate`, and the start and end of a `Period` (they are
`:Date` nodes too). The package's own migration makes them, in the way `pangloss_memgraph` does. A `Period` and a
`Recurrence` are not `Date`s, so they get their own (`Period(earliest_fuzzy, latest_fuzzy, sort_day)`). Cost measured
earlier: about 20% on bare writes for a label-and-property index (~0.06 ms per node), so three indexes on a date is
cheap beside the text index.

### The sort date

To order documents by a date there must be **one integer per date**: `sort_day`, stored with the bounds and indexed.

- **Default: the midpoint of the strict range** (`(earliest_strict + latest_strict) // 2`). For a precise day that
  is the day; for "1500" it is about 2 July; for a range, the middle.
- **Choosing another**: `sort_by`, a value from a small enum: `midpoint` (default), `earliest_strict`,
  `latest_strict`, `earliest_fuzzy`, `latest_fuzzy`, `midpoint_fuzzy`. Set it two ways:
  - on the **field**, as an annotation that is the default for every value of that field: `birth: Annotated[SingleDate, SortBy.EARLIEST_FUZZY]`
    ("for a birth date, a person sorts by the earliest it could be");
  - on the **value**, a `sort_by` literal on the date (so an editor can choose for one document), which beats the
    field's.
  - An explicit `sort_day` typed by the user is *not* offered: it could contradict the bounds; the options above
    cover the cases.
- **`Period`**: the sort date is the **start's** `sort_day` (a person's jobs in the order they began); an open start
  uses `earliest_fuzzy`. `sort_by` applies to the start. A period also keeps `end_sort_day` for ordering by when it ended.
- **`Recurrence`**: the sort date is the **start** of the lifetime in the same way (the first possible day).
- Ordering by a date needs a search extension: the structured search orders by `toLower(label)`. Add
  `order_by` to the search request, a path to a date field (`{"order_by": "date", "direction": "asc"}`), compiled as the
  `sort_day` of the matching embedded date. Where a document has no date (or the date is a union without it), it sorts last.
  A list endpoint ordering is the same change. *Separate step, after the types.*

### Repeated events

"Maximilian orders a ceremony every Sunday from <date>" is a `Recurrence` (as `dates.md`): a **rule** plus a **fuzzy
lifetime**; occurrences are never stored. It is built in this first version, because the rule and the bounds are
needed together by the queries.

```
Recurrence      rule fields (below) + start: Date types + end: Date types or open + excluded_days: list[int]
```

- **Rule vocabulary (first version)**, as scalar fields since lists of Embedded are not supported and a rule is one
  Embedded: `frequency` (`weekly`, `monthly`, `yearly`), `weekdays: list[Weekday]` (every Sunday), `nth: int | None`
  with a weekday (the third Sunday), `month: int | None`, `month_day: int | None` (21 March), `interval: int = 1`
  (every second week). Out of the first version, later: a feast of the saints, an offset from Easter (needs the
  observances and the Julian computus), and rules with a probability ("the first or the third Sunday").
- **Stored bounds**: `earliest_fuzzy` is the start's `earliest_fuzzy`; `latest_fuzzy` is the end's `latest_fuzzy`, or
  the **horizon** (`DATES_OPEN_END_HORIZON`, a setting, e.g. 1600) for an open end; the strict pair likewise. These are
  indexed like a date's, so "everything in force in 1505" is a range query.
- **Pattern keys**: `pattern_keys: list[str]`, derived: the small fixed set of patterns the rule can fall on
  (`weekday:0` for Sundays; `monthday:3-21`; `nth:3:0:3` for the third Sunday of March). A pure function turns a day
  `D` into its keys, so **"everything on D"** is: bounds contain `D` AND `pattern_keys` contains any key of `D`
  (the search's list `contains_any`), then the exact rule is checked in Python on the few left, including excluded days
  and `interval`. No calendar nodes, no expansion, no new core mechanism. (The calendar package of `dates.md` is still
  how a month view or feasts would be done, later.)
- **In Python (pure)**: `occurs_on(rule, day)`, `occurrences(rule, first_day, last_day)` over day numbers (the
  rule is applied in the date's calendar), and the probability that an occurrence on `D` is real is left to the
  probability step later (for now the lifetime's bounds are a yes/no range).
- **Three things kept apart** (from `dates.md`): the standing order (the `Recurrence`); attested occurrences (ordinary
  documents with ordinary dates); lapses (a new earlier `end`, or an excluded day).

### Phases, revised

1. `calendar.py` (as before), plus **weekday and nth-weekday arithmetic** (the third Sunday of a month in either calendar).
2. `parts.py`, `bounds.py` (now with `sort_day`), and `recurrence.py` (pure: the rule, `occurs_on`, `occurrences`, `pattern_keys`).
3. `edtf.py`.
4. `models.py`: `Date` types, `Period`, `Recurrence`; the validator fills the bounds, `sort_day` and `pattern_keys`.
5. Core: `Meta(indexes=...)` on Embedded; the first look at whether validators reach the DB models.
6. Search: `order_by` a date field; live tests for range, "on this day" and ordering.

### Decisions, second round (2026-10-27)

- **Indexes on Embedded: yes**, as above (base `Date`, `Period`, `Recurrence`).
- **Sort date**: midpoint of the strict range by default; a field annotation sets a field's default; a `sort_by` on the
  value beats it; no free-typed `sort_day`.
- **Recurrence vocabulary, first version**: weekly, monthly, yearly; nth weekday; month day; interval; excluded days.
  Feasts and Easter offsets later.
- **"On this day"**: bounds plus `pattern_keys`, then the exact rule checked in Python; no calendar package.

### Calendar choice: thin subclasses (2026-10-27)

A project does not usually mix calendars, so the calendar is chosen by **which class a model uses**, not per value.

- The base types (`ExactDate`, `EDTFDate`, `DateRange`, `Period`, `Recurrence`) keep a `calendar` field (stored, so a
  date can be shown in the calendar it was written in) whose default is `DATES_DEFAULT_CALENDAR` (**Gregorian** unless
  the project sets it).
- **Thin subclasses fix it**: `JulianExactDate`, `JulianDateRange`, `JulianEDTFDate`, `JulianPeriod`,
  `JulianRecurrence` (and `Gregorian...` for symmetry). Each sets the default and a validator rejects the other
  calendar. They add no fields, so they are built by one helper (`calendar_variants("julian")`), not written by hand.
- A subclass inherits its parent's labels, so a search for `ExactDate` finds the Julian and the Gregorian ones, and
  the indexes on `:Date` cover them. Day numbers are the same in both, so ordering and range queries across them are
  correct.
- A `Period` holding a start and an end takes the dates of its own calendar; a Julian period with a Gregorian end is
  not allowed (use the base `Period` if that is ever needed).
- Open: the names (`JulianExactDate` against `JulianDate`), and whether a project setting alone, which makes the
  base classes Julian with no subclasses, is enough for projects that never use both.

### The class tree, as settled (2026-10-27; supersedes the earlier tree where they differ)

```
Embedded
└── JulianDate / GregorianDate / Date   the base of a family: the bounds, calendar, source_text, sort_by, sort_day, precision
    ├── ExactDate          year, month=None, day=None
    ├── EDTFDate           edtf string (parsed by python-edtf, bounds by us)
    ├── DateRange          earliest: ExactDate, latest: ExactDate        (embeds two exact dates)
    ├── OngoingDate        no fields: the end of an open period
    ├── Period             start: ExactDate | DateRange | EDTFDate | OngoingDate, end: the same
    └── Recurrence         rule fields + start, end as in Period + excluded_days
```

- The family root (`Date`, and the `Julian...` / `Gregorian...` variants of every class) is the base class. A field
  typed with the root takes any kind -- as a base class if the model code accepts subclasses of an Embedded in a field
  (*to check*), otherwise as a union alias of the same members.
- A **range embeds two `ExactDate`s**, so each end can itself be a year, a month or a day ("between 1500 and
  March 1502"). The range's strict bounds are `earliest.earliest_strict` to `latest.latest_strict`; its fuzzy bounds
  `earliest.earliest_fuzzy` to `latest.latest_fuzzy`. This replaces `DateParts`.
- **Period / Recurrence ends** are single dates or ranges, never another `Period` or `Recurrence`. (Read as "JulianExact or
  JulianDateRange"; the earlier message said "JulianPeriod", taken to be a slip.)
- The embedded `ExactDate`s inside a range or period are also `:Date` nodes, so a query that matches `ExactDate`
  directly (rather than through the field) finds them too; searches go through the document's field, so this only
  matters for a query written against the embedded class itself.

### Built so far (2026-10-27)

- `packages/pangloss-dates` exists (a workspace member; `edtf` is the optional extra; `juliandate` is a dev dependency for the tests).
- `pangloss_dates.calendar` (phase 1, first half): `Calendar`, `Weekday`, `to_jdn`, `from_jdn`, `convert`, `is_leap_year`,
  `month_length`, `weekday`, `nth_weekday` (1st to 5th, or -1 for the last), `first_and_last_day`, `InvalidDate`. Years are
  astronomical (1 BC is 0), valid from -4799 to 9999; no cutover.
- 31 tests: known days (JDN 0, 2000-01-01, the 1582 change, 1500-03-02 Julian = 1500-03-12 Gregorian = 2268994), every day
  1400 to 1600 round-trips and agrees with `juliandate`, the leap years, weekdays, `nth_weekday` against a brute force over 1400 to 1600
  in both calendars, and the days that do not exist.
- Next: `bounds.py` (the four bounds and `sort_day`), `recurrence.py`, `edtf.py`.

- `pangloss_dates.bounds` (built): `Bounds` (the four, checked in order; `sort_day(SortBy)`, `contains`), `SortBy`, `Precision`,
  `Padding` (the convention: an approximate year is a year either side, a month a month, a day a week),
  `exact_bounds`, `padded_bounds`, `spanning_bounds` (a range of two dates, or a period), `ongoing_bounds(horizon)`.
- `pangloss_dates.recurrence` (built): `RecurrenceRule` (weekly / monthly / yearly; weekdays, `nth`, `month`, `month_day`,
  `interval`, `excluded_days`; an impossible combination is `InvalidRule`), `occurs_on`, `occurrences`, `pattern_keys`, `day_keys`.
  A rule is applied in a calendar; an interval over 1 counts from an anchor day (weeks of seven days from it). The keys never miss
  (tested over eight years in both calendars for eight rules), and cut the candidate days to under 60%.
- 92 tests in all. Left of phase 1: `edtf.py`.
- `pangloss_dates.edtf` (built; needs the `edtf` extra): `parse_edtf_date(text, calendar, padding)` and `parse_edtf_interval` give
  `EdtfResult(bounds, precision, uncertain, approximate)` using `python-edtf` only to parse. Read: years, months, days,
  `?` `~` `%` (also on a part, read as qualifying the whole date), `15XX`, `150X`, `1500-XX`, sets (span of the members), intervals
  (start and end, `None` where open or unknown). Not read, with `EdtfUnsupported`: seasons, significant digits, long years, times,
  unspecified digits with a qualifier, open sets. `1500-02` ends on the 29th in the Julian calendar (the library says the 28th).
- **Phase 1 is complete: 113 tests.** Next: phase 4 (`models.py`), after the core check (validators on `Embedded` reaching the
  generated models, required fields on Create) and `Meta(indexes)` on Embedded.

### Core checks done (2026-10-27)

- A field typed with a base Embedded class accepts its subclasses (tested).
- Validators on an Embedded did **not** reach the generated models; now `mode="after"` model validators the class declares are copied to
  `Create`, `Update`, `CreateDB` and `UpdateDB` (`initialise_models/common.py`, `kinds.py` `declared_validators`). The derived bounds are
  therefore `int | None = None` fields that the validator always fills (a client's values are overwritten).
- `Embedded.Meta(indexes=[...])` is built: label-and-property indexes for an Embedded class that asks (none otherwise), made by
  `initialise_database` and migrations like the others. Full suite 2186 passed.
- Next: `models.py` in `pangloss-dates`.

### Phase 4 built: the models (2026-10-27, not committed)

- `pangloss_dates.models`: `Date` (abstract base: `calendar`, `source_text`, `sort_by`, and the worked-out `precision`, the four bounds, `sort_day`),
  `ExactDate`, `EDTFDate`, `DateRange` (two `ExactDate`s), `OngoingDate`, `Period` (`start`, `end`, `end_sort_day`; sorts by its start), `Recurrence`
  (rule fields, `start`, `end`, `end_sort_day`, and `pattern_keys` as a `DBField` that only the database models have). `pangloss_dates.julian`
  and `pangloss_dates.gregorian` have the thin families (`JulianDate`, `JulianExactDate`, ... : multiple inheritance from the family root and the
  plain type; the calendar is fixed and the ends of a range, period or recurrence are the family's own).
- One validator on `Date` (copied to the models that are written) fills everything in, whatever a client sent. Errors (a day that does not
  exist, an empty range, a rule that says no day, EDTF that is not EDTF, the wrong calendar) are validation errors.
- Core changes made for it: validators copied (above); `Embedded.Meta(indexes=...)`; a `DBField` list defaults to `[]` in the database models so a
  validator can fill it; **structured search now reaches into embedded fields**: `{"when": {"type": "JulianExactDate", "where": {"sort_day": {"between": [a, b]}}}}`
  (the type may be left out when the field is typed with one class; nested embedded objects work the same way).
- Tested: 15 model tests; a live test writes every kind to Memgraph, reads it back and finds documents by the bounds of their date.
- **Not done / to know:**
  - The indexes on `:Date` are not used by a search from a document: the date is reached by an `EXISTS` from the document's node, and an index does
    not help inside one. They help only a query that starts from the dates; to use them the search would have to start from the date and climb
    to the document (as `$incoming` does). Not built; measure first.
  - **Ordering by a date** needs `order_by` on the search (and list) request: not built.
  - The field-level sort default (`Annotated[ExactDate, SortBy.EARLIEST_FUZZY]`) is not built: an embedded class cannot see the field it is
    in. The class-level and per-value `sort_by` work. Needs a small core hook if wanted.
  - "Everything on this day" as a query (the bounds, then `pattern_keys` with `contains_any`, then `occurs_on`) is not written as a helper yet.
