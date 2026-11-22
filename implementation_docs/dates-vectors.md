# The time part of similarity ✅

`pangloss-dates-vectors`: the part `"time"` of [`pangloss-vectors`](vectors.md), a vector of each item from its
**dates** ([`pangloss-dates`](dates.md)), so that dates that overlap are near and dates years apart are not. Built as
phase 9 of [the build plan](similarity-build-plan.md) (2026-11-22), on both backends; the plan's "9.2 as built",
"9.1 and 9.3 as built", "9.3 measured" and "9.4 decided" say where the code differs from the steps. How to use it is
[the guide](../guide/vectors/time.md).

```python
# settings.py
INSTALLED_APPS = [..., "pangloss_dates", "pangloss_vectors", "pangloss_dates_vectors"]
VECTORS_PROFILES = {"when": {"graph": 1, "class": 0.1, "time": 0.5}}   # the part counts only in a profile that weighs it
```

Needs `pangloss_vectors` and `pangloss_dates`, and a backend with Cypher and a vector index (`requires = {"cypher",
"vector_index"}`: Memgraph and Neo4j). Depends on numpy, imported only when a vector is made (not by a client of the
SDK that imports the models). `pangloss-dates` is not changed and knows nothing of it: why it is a package of its own
is in [dates](dates.md#dates-in-similarity).

## Contents

- What is built, and what is not
- What the time part is for
- The maths
- Whose vector a date is
- The settings
- Rebuild, refresh and overlay
- In the demo
- Measured
- As built: where the code differs from the plan
- The code

## What is built, and what is not

| | What |
|---|---|
| ✅ | The maths with no database in it (`maths.py`, step 9.2): a date's four bounds as a line in pieces, blurred by a bump of the width, read at the places of a ring of years; an item's dates added |
| ✅ | The settings (`settings.py`): `DATES_VECTOR_DIMENSION` and `DATES_VECTOR_WIDTH`, checked at `initialise()`, in the part's signature |
| ✅ | The part `"time"` (`part.py`, step 9.3): rebuild, an exact refresh, overlay; at weight 0; whose vector a date is (9.2's rule) |
| ✅ | The suite every part passes (`pangloss_testing.parts.PartSuite` with `dated = True`), and the part's own claims, on both backends (`tests/live/test_time_part_live.py`) |
| ✅ | Measured on a planted world with dates: through the maths (9.2, 5,986 people) and through the part at size on both backends (9.3, 32,137 people, 856,790 nodes) |
| ✅ | An entity's span from the documents that name it: measured and decided against (9.4, below) |
| ✅ | The demo: the profile `when` (graph 1, class 0.1, time 0.5) and its indexes (step 9.5) |
| ⏳ | An entity's span from the documents that name it, if a project has names and dates and no graph part (9.4: not built, and why) |
| ⏳ | A date on a wrapper or an embedded object counted for the nested document that holds the wrapper: today it counts for the head only |
| ⏳ | A `Recurrence`'s rule: its vector is its lifetime only, nothing of the day of the year it falls on |
| ⏳ | The overlay of an update plan (no caller asks one yet: phase 10's service overlays `Create` payloads) |
| ⏳ | Anything in the interface of its own: a profile that weighs time is one more entry in the menu of the section "Similar", as any profile is |

## What the time part is for

**Finding candidates, not comparing two dates.** Given a statement, the time part makes the statements of the same
time near it, so that a profile that weighs it finds **the other reports of an event**: two sources that tell the
same gathering, each with the date as it knew it (one the day, another the month, a third "about 1300"). It also tells
apart **the years of an event that recurs**: the same dues paid by the same person to the same group every year,
which the graph cannot tell apart (the same people, the same group), are apart by their dates. It does not say
whether two dates are the same, or that one is before another: `pangloss_dates.rules` does that, exactly, on the
bounds ([dates](dates.md#dates-in-derived-rules)). A part's vector goes into a profile with other parts, and time is
worth most beside the graph (below, "Measured").

## The maths

`maths.py` is the whole of the computing, with no database in it: the bounds of a date to a vector.

```
earliest_fuzzy  earliest_strict      latest_strict  latest_fuzzy          (day numbers, `pangloss_dates.bounds`)
      │               │                    │              │
      ▼               ▼                    ▼              ▼
      ·           ────────────────────────────            ·     1    how far the date could be each day:
      ·       ╱                                ╲          ·          wholly between the strict bounds,
──────────╱                                        ╲──────────  0    falling to nothing at the fuzzy ones
                             │
                             ▼   blurred by a bump of `width` years, and read at a centre every `width` years
             ▁ ▂ ▄ ▆ █ █ █ █ █ █ █ ▆ ▄ ▂ ▁                           the vector, then at length one
```

- **A date is its four bounds as a line in pieces**: 1 between the strict bounds, falling in a line to 0 at the fuzzy
  ones (a date that is exactly what it says is a box). Every kind of date of `pangloss-dates` stores these four day
  numbers, so a day, a month, a year, a range, a period and an EDTF date are alike to it, in either calendar (a Julian
  date is placed by the day it was).
- **Blurred by a bump of the width**: a logistic curve whose spread is `DATES_VECTOR_WIDTH` years. So a day and its
  year are near, and two years ten years apart are not. A vague date is a wide low hill, an exact one a narrow one:
  they are near when one is inside the other, and nearer the more of the vague one the exact one covers. It is
  computed exactly, with no sum over days: a bend blurred by a logistic curve is `softplus` and a step blurred is the
  logistic function, so a date at a centre is four of them (no `scipy`).
- **The ring**: the centres are `DATES_VECTOR_DIMENSION` places, a width apart, and **the years go round them**: the
  year after the last place is the first again (`maths.Ring`). So a vector has the same dimension whatever years a
  project's dates are in, no date is outside it, and nothing has to be said of a range of years. Neighbouring years
  are neighbouring places (it is not a hash): within `dimension × width` years (256, as it is given) the ring changes
  nothing; two dates that far apart have the same vector, and beyond it time alone no longer tells them apart. The
  graph does, which is why the ring cost nothing in a profile (below).
- **A date longer than the ring** (a period of three centuries; a range whose start is not known, which runs from
  `DATES_EARLIEST_YEAR`) is at every place alike: the most of it at each place is taken, not the sum, so no part of it
  counts twice. It says nothing of when, and is a little like every date (0.16 with a year, as it is given) and no
  more like one than another. A project with such dates that should count gives the ring more places.
- **Several dates of one item** are added, each at length one first, so that a long period does not drown a day; then
  the sum at length one.

The cosine of two dates falls with the gap between them, measured in widths, and is the same wherever they are (to
about a hundredth: the centres are a width apart). At the width 2, two years a gap apart (9.2 as built):

| Gap, years | 0 | 1 | 2 | 3 | 5 | 10 |
|---|---|---|---|---|---|---|
| Cosine | 1 | 0.92 | 0.73 | 0.51 | 0.18 | 0.005 |

A year in the middle of its decade is 0.85 to the decade (0.53 at its ends); a decade and the next 0.14.

## Whose vector a date is

As 9.2 decided, said in `part.counts_for`:

- **A date held by a date** (an end of a `DateRange`, the start or end of a `Period` or a `Recurrence`) is part of
  that date and counts for nothing itself.
- **Any other date counts for what holds it, if that is a document or an entity**, and **for the head it is under**:
  a factoid has the dates of all its statements, and each statement its own; a head that holds a date itself (a
  person born) counts it once. "A document or an entity" is said as the class part says it: a citation is not one.
- **A date held by anything else** (a reified relation, an embedded object, a semantic space) counts for the head
  only.
- **A date only unknown** (an `UnknownDate` by itself, precision `unknown`) counts for nothing. An `OngoingDate` by
  itself does count, as a box at `DATES_OPEN_END_YEAR`.

An item with no date that counts has no time vector. Only an item of a class that has vectors
(`pangloss_vectors.meta.included`: not `VECTORS_EXCLUDE`, not `VectorsMeta(include=False)`) gets one, and only one a
reader could be shown (its head there, not deleted, not merged into another). Nothing takes a class out of the time
part alone. A date an entity holds itself has the entity's id as its `head_node_id`, like every node below a head, so
the refresh finds it with the rest.

**An entity has no time vector from the documents that name it** (9.4, below): only from its own dates.

## The settings

| Setting | Default | |
|---|---|---|
| `DATES_VECTOR_WIDTH` | 2 | The years between two places of the ring, and the spread of the bump a date is blurred by: a number of years from 0.01 to 100 (`1`, `2.5`; `2` and `2.0` are the same) |
| `DATES_VECTOR_DIMENSION` | 128 | The places of the ring, the length of the part's vectors: a whole number from 8 to 2048 |

Both are **refused at `initialise()`** (`PanglossInitialisationError`, saying what the setting is) when the app is
installed: a width that is not a number (a bool, a string, None), is NaN, is less than 0.01 (a date is worked out at a centre every width of its span), or is more than 100; a
dimension that is not a whole number (a bool, a float) or is outside 8 to 2048. Both are the part's `signature()`,
and nothing else is: a change of either makes a rebuild of the time part due (`pangloss vectors status` says so),
a new class does not, and a class newly left out of the vectors does by the signature the store compares. A change of the dimension changes the dimension of every profile that weighs
time, and so its vector indexes: `pangloss makemigrations` and `pangloss migrate` before the rebuild.

**How to choose them.**

- **The width as vague as the dates are**, and **no wider than events that recur are apart**. Two dates a width apart
  are still fairly near (0.73 at the width 2 is two years apart); five widths apart they are not. A project whose
  dates are mostly to the year or to a few years keeps 2; one with exact dates and events year after year sets 1
  (measured below: the years of a payment told apart far better, the events told twice no worse). The trial on real
  data found 1 too narrow for its vaguer dates.
- **The dimension times the width longer than the span of the project's dates**, if time alone should tell centuries
  apart: at 128 × 2 the ring is 256 years, so 1300 and 1556 are the same place. Beside the graph part this does not
  matter (measured below: down to 32 places nothing was lost), so the default is enough for a profile that weighs the
  graph too. A project with long periods that should count (longer than the ring, they say nothing) gives it more.

## Rebuild, refresh and overlay

- **A rebuild** (`pangloss vectors rebuild`, or `--part time`) reads every date in pages of 10,000 by the index of
  `PGIndexableNode(id)`, each with what holds it and its head, and keeps them compactly (four integers a date, and a
  pair for each item it counts for: never a matrix of every date); then makes the vectors 1,000 items at a time
  (`maths.of_items`) and writes them.
- **A refresh** reads the dates under the heads written (by the index of `PGIndexableNode(head_node_id)`), writes the
  vectors of the items they count for, and removes the time vector of a written head, or of a document under it, that
  has one stored and no date that counts now (a date taken away, a statement removed, a class changed in place to one
  without vectors). **Exact: nothing is ever stale**, and nothing is kept with a generation (`kept()` is the other
  parts' business). Nothing before the first rebuild.
- **An overlay** of a write plan gives the vectors its head and the documents in it would have, from the planned nodes
  of its dates (a planned node with the label `Date`, its bounds the `DBField`s the date's validator worked out, held
  by the planned node whose relation it is), by the same rule; nothing is written. An entity written in the document
  (`create_inline`) is a head of its own and is not walked.

The part is `local` (a write changes only the vectors of what it wrote) and at **weight 0**: installing the package
changes no profile and no result until `VECTORS_PROFILES` weighs it.

## In the demo

`pangloss-demo` installs the app (after `pangloss_names`), and its settings say

```python
VECTORS_PROFILES = {
    "who": {"name": 1, "graph": 0.25},
    "when": {"graph": 1, "class": 0.1, "time": 0.5},
}
```

`"when"` is the default profile's parts at their own weights (the demo does not give `"default"`, so it is the class
at 0.1 and the graph at 1) with time at 0.5, the weight measured in 9.2. `"default"` and `"who"` are as they were.
`DATES_VECTOR_WIDTH` and `DATES_VECTOR_DIMENSION` are not set: the demo's dates (about 730 to 830, Julian) are well
inside the ring of 256 years. The migration `demo_app` 0026 is the three vector indexes of `when` (dimension 293: 37
of the class, 128 of the graph, 128 of time; one for every item, one for each group, `Person` and `Statement`) and
nothing else. [Demo setup](demo-setup.md).

**What has a time vector in the demo**: every kind of `Statement` (each is `Dateable`, and a nested document, so it
has its own date's vector), the heads above them (`Factoid`, `DerivedFactoid`: the dates of all their statements,
those in `Negative`, `Hypothetical` and `Causes` too), and `Feast` (its `when`; a feast attached by hand, `NoRule`,
has none). A `Feast`'s date is the calendar's, not when something happened; a feast every year with no start or end
runs from `DATES_EARLIEST_YEAR` to `DATES_OPEN_END_YEAR` (700 to 1600 in the demo), longer than the ring, so it is
alike at every place. `Person` has no date (`born` went in migration 0021), nor has `Source` (`written` is a
`datetime.date`, not a date of `pangloss-dates`). Nothing is excluded; `TODO.md` asks the user.

On a scratch copy with `populate.py` (2026-11-22; 22 time vectors, 55 in `when`; the factoids unpublished, so the
graph part had 5 vectors and the search was asked with `see_unpublished`), the nearest statements of "Leo crowns
Charlemagne" (25 December 800) by `when` were the two other reports of that day at 1.0, then "Charlemagne goes to
Rome" (24 November 800) at 0.999, then the two activities of July 799 at 0.876; by `default` all five activities were
at 1.0, July 799 among them. These are what the command printed, not a measurement.

## Measured

All on the dated planted world of `pangloss_testing.planted` (`planted.world(dated=True)`; the scripts and their
output in `notes/similarity-evaluation/`). Every statement may say when, as its source knew it (the day 40%, the month
15%, the year 30%, some years it was within 15%). Two kinds of event are planted: **a gathering told twice** (a sixth
of the gatherings told once more, by fewer of the people, the date said its own way), and **dues paid year after
year** (one family in ten, six to twelve years, each payment reported twice by the same person to the same group, so
that nothing but the date tells one year's from the next). The share of an event's other reports that are first,
among the three nearest and among the ten nearest factoids of a report (those as near counted before it).

**Through the maths, 9.2** (2026-11-22; 5,986 people, 18,301 factoids, 1,200 reports of a gathering told twice, 2,374
of a payment; the stored graph and class vectors of the scratch Memgraph and time vectors made from the truth,
`planted.py time`, `planted_time_memgraph_small.txt`):

| Weights | Told twice: first / 3 / 10 | Year after year: first / 3 / 10 |
|---|---|---|
| Graph (class 0.1 changes nothing) | 89.0% / 96.7% / 98.8% | 5.6% / 16.0% / 52.4% |
| Time alone, width 2 | 15.2% / 26.3% / 33.1% | 13.1% / 25.6% / 31.2% |
| Graph + time 0.25, width 2 | 97.8% / 99.4% / 99.8% | 40.2% / 78.9% / 99.9% |
| **Graph + time 0.5, width 2** (the demo's `when`) | **98.4% / 99.6% / 99.7%** | **57.4% / 92.8% / 100%** |
| Graph + time 1, width 2 | 98.3% / 99.3% / 99.7% | 80.2% / 98.9% / 100% |
| Graph + time 0.5, width 1 | 98.5% / 99.4% / 99.6% | 91.2% / 99.9% / 100% |
| Graph + time 1, width 1 | 97.3% / 98.9% / 99.3% | 95.5% / 100% / 100% |
| Graph + time 0.5, width 5 | 98.0% / 99.7% / 99.8% | 23.8% / 54.4% / 97.6% |

- **With time, an event's other report is nearly always among the nearest** (the trial on real data of 2026-11-11:
  95% to 99.5% among the ten), and a payment's other report, which the graph cannot find among the other years' (5.6%
  first), is among the three nearest.
- **The ring costs nothing beside the graph**: at the width 2, 512, 128, 64 and 32 places gave the same figures to 0.3
  of a point (time alone falls, from 33% among the ten to 26% at 32 places, which no profile is).
- **The width is the project's.** Here 1 tells the years of a payment apart far better (91% first against 57%) and
  costs the gatherings nothing: the planted dates are vague by years only one time in seven. On the real data of the
  trial 1 was too narrow (95.6% among the ten against 99.1%). The default stays 2.
- The graph vectors of a payment's reports are not the same for each year (each report's own nodes are in them), so
  time has to outweigh that noise: why "first" rises with the weight of time.

**Through the part at size, on both backends, 9.3** (2026-11-22; seed 1: 32,137 people, 96,693 factoids, 137,337
records, 856,790 nodes in all, 147,450 of them dates and 116,030 not held by a date; 6,400 reports of a gathering told
twice, 11,360 of a payment; a profile `when` of graph 1, class 0.1, time 0.5, 273 places; `planted.py reports`,
`planted_reports_memgraph.txt`, `planted_reports_neo4j.txt`):

| | Memgraph | Neo4j |
|---|---|---|
| Every date read with what holds it and its head (15 pages) | 1.8 s | 2.7 s |
| The time part rebuilt (212,723 vectors) | 52.7 s | 25.4 s |
| The profile `when` combined and indexed (253,367 vectors of 273) | 181 s | 107 s |
| Told twice, through the profile's index (k 40): the other report first / in 3 / in 10 | 98.0% / 98.7% / 98.7% | 97.7% / 99.0% / 99.0% |
| Told twice, narrowed to `Factoid` (an exact scan) | 99.3% / 100% / 100% | 98.7% / 100% / 100% |
| Year after year, through the index | 56.3% / 90.0% / 99.3% | 60.7% / 90.7% / 100% |
| Year after year, exact scan | 56.7% / 90.7% / 100% | 60.7% / 90.7% / 100% |
| A search through the index, median | 103 ms | 12 ms |
| A search narrowed to `Factoid` (96,693 of them scanned), median | 1.19 s | 0.77 s |
| The time part's refresh in a worker's turn, one head | 0.2 s | not timed apart |

- **A profile with time finds an event's other reports on both backends** (what phase 9 is done by). By the graph and
  class alone, from the same stored vectors: first 88.8%, among the ten 99.0%; a payment's 5.8%, among the ten 56%.
- **The index loses about one report in a hundred** against the exact scan (98.7% against 100% among the ten), as
  phase 8 found for names.
- **The rebuild of the time part is the writing**, not the reading or the maths (1.8 s to read, under a second to
  compute): half the graph part's time on each backend.
- **A worker's turn after a new dated factoid** was 5.2 s on Memgraph and 4.4 s on Neo4j, and that was the graph part
  (a gathering at a place many are at: 247 graph vectors rewritten in 4.5 s); the time part's refresh was 0.2 s.
  After a small factoid of two new people the whole turn was 1.3 s, each part about 0.2 s.

**An entity's span, 9.4** (2026-11-22; the world of 5,986 people, 1,197 mentions; who a mention is among the people:
the name with the table of variants, the stored graph vectors, and a time vector of each person and mention made from
the truth, of the dates of the factoids that name them; `time_entities.py`, `time_entities_small.txt`):

| Weights | Right first | In five | In ten |
|---|---|---|---|
| Name | 50.0% | 97.2% | 99.6% |
| Name + time 0.1 | 73.6% | 99.2% | 99.8% |
| Name + graph 0.25 | 76.4% | 99.7% | 99.9% |
| Name + graph 0.25 + time 0.1 | 71.3% | 99.7% | 99.9% |
| Name + graph 0.25 + time 0.25 | 55.5% | 99.4% | 99.8% |
| Name + graph 0.1 | 80.5% | 99.4% | 99.7% |
| Name + graph 0.1 + time 0.1 | 78.4% | 99.4% | 99.8% |

By the name alone, when someone lived tells namesakes apart (50% to 74% right first); **beside the graph it adds
nothing and costs a little**: the graph already says who is named with whom, which says when as well, and a person's
family lived when they did. **So it is not built.** It would also have cost what the part has: a person's span depends
on every document that names them, through wrappers, so the part would stop being local for entities and a write of a
factoid would refresh the people it names. An entity's own dates do give it a vector. To come back to if a project has
names and dates and no graph part.

**In the tests** (`tests/test_time_planted.py`, pure, 1,500 people, three seeds, time alone, no database): of what
happened year after year, the other report of the year is first among the reports of the same thing (measured 99.7%
to 100%; the floor 98%); an event told twice is among the nearest tenth of all the factoids by time alone (100%; the
floor 99%) and the nearest hundredth (83% to 90%; the floor 75%).

## As built: where the code differs from the plan

- **No range, and a fixed dimension: the years go round a ring** (the step had a centre every width over
  `DATES_VECTOR_RANGE`, and a date outside the range with no vector, counted). There is no such setting, and no date
  is outside.
- **A date longer than the ring is at every place alike** (mended after 9.3: it went round more than once and its
  ends counted twice; `tests/test_time_maths_more.py`).
- **A `Recurrence` is its lifetime**, as its bounds say it: nothing of its rule. "A recurring event's years are apart"
  is of the statements of each year, which is what is planted.
- **"A demo profile with time on `Statement`"** (the step): a profile is not on a class. `when` has a vector for every
  item with any of its parts, and `Statement`, a group, has an index of it of its own, as `Person` has.
- **Not built**: an entity's span (9.4, above).

## The code

| File | |
|---|---|
| `maths.py` | `Ring`, `blurred`, `vectors`, `summed`, `vector`, `of_items`: no database |
| `settings.py` | `DATES_VECTOR_DIMENSION`, `DATES_VECTOR_WIDTH` (`dimension()`, `width()`, `ring()`), and `check` at `initialise()` |
| `part.py` | The part `"time"`: `counts_for` (whose vector a date is), `Dates` (kept compactly), `rebuild`, `refresh`, `overlay`, `overlay_rows` |

Tests: the pure ones in `tests/` (the maths, `test_time_maths.py` and `test_time_maths_more.py`; the part's rule,
signature and settings and their refusals, `test_time_part.py`; the planted floors, `test_time_planted.py`); the live
ones in `tests/live/test_time_part_live.py`, on both backends (the part through `PartSuite` with dates, and its own:
a nested statement's date for the statement and its head, a person born, a date taken away, the refresh's removals; a
merge of an entity with a date into one without, marked `xfail(strict=True)`: [`TODO.md`](../TODO.md)).
