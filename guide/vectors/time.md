# Finding the other reports of an event

With `pangloss-dates-vectors`, every document and entity with a date gets a vector made from **when** it was, so that
a profile that weighs it finds the items of the same time: the other reports of an event, each source with the date
as it knew it (one the day, another the month, a third "about 1300"), and, of an event that recurs, the report of the
same year rather than of the year before. It is a fourth **part** of [similar items](README.md), beside the class,
the graph and [the name](names.md), and works on Memgraph and on Neo4j.

It finds **candidates**: the items of about the same time. It does not decide that two dates are the same, or that one
is before the other (for that, [rules on dates](../../implementation_docs/dates.md#dates-in-derived-rules)).

The reference is [the time part](../../implementation_docs/dates-vectors.md).

## 1. Install it

```python
INSTALLED_APPS = [
    "pangloss_memgraph",
    ...
    "pangloss_dates",
    "pangloss_vectors",
    "pangloss_fastrp",
    "pangloss_dates_vectors",    # the time part
    "my_app",
    "pangloss_interface",
]
```

It needs `pangloss_dates` and `pangloss_vectors`, and numpy in the server's environment (a dependency of the
package). It reads the dates your models already have (any field whose type is a date of `pangloss-dates`): nothing
in the models changes.

## 2. Weigh time in a profile

Installing the package changes nothing by itself: the time part has a weight of 0, so no profile uses it until you
say so. Add a profile that weighs it beside the parts you already have:

```python
# settings.py
VECTORS_PROFILES = {
    "when": {"graph": 1, "class": 0.1, "time": 0.5},
}
```

`"when"` is the default's parts at their own weights, with time at half the graph. The graph says who and where; time
says when. Neither is enough alone: by the graph, the reports of dues paid by the same person to the same group year
after year are all alike, and by time alone everything of the same years is. (Measured on made-up data: with the graph
alone, the other report of the same year's payment was first 6% of the time; with time at 0.5 it was among the three
nearest 93% of the time, and the other report of an event told twice was first 98% of the time. The figures are in
[the reference](../../implementation_docs/dates-vectors.md#measured).) Give time more (1) if events that recur matter
most to you, less (0.25) if they do not.

If you do not give `"default"` it stays as it was (the graph at 1, the class at 0.1), so the "Similar" section of
each item's page does not change; its menu of the profile now has `when` too. `pangloss vectors weights` shows the
profiles.

## 3. Migrate, then build the vectors

A new profile has vector indexes of its own:

```sh
pangloss makemigrations        # the indexes of "when": one, and one for each group
pangloss migrate
pangloss vectors rebuild       # (or only the time part and the profiles that weigh it: --part time)
pangloss vectors status
```

For the demo, `makemigrations` wrote:

```
demo_app.0026_addindex_addindex_addindex
    - Create the vector index pgv_when_293 on :PGV_when_293(vector) (dimension 293, metric cos)
    - Create the vector index pgv_when_293_person on :PGV_when_293_Person(vector) (dimension 293, metric cos)
    - Create the vector index pgv_when_293_statement on :PGV_when_293_Statement(vector) (dimension 293, metric cos)
```

293 is 37 for the class, 128 for the graph and 128 for time.

## 4. Ask for the items of the same time

The section "Similar" of an item's page, with `when` chosen in its menu, or over the API:

```sh
curl "http://127.0.0.1:8000/api/Activity/{id}/similar?profile=when"
```

From Python, on the server's side:

```python
import pangloss_vectors

found = await pangloss_vectors.nearest(statement_id, profile="when", group="Statement", k=10)
found.hits          # [Hit(id, type, score), ...], nearest first
```

In the demo, the statements nearest "Leo crowns Charlemagne" (25 December 800) by `when` were the two other reports of
that day first, then "Charlemagne goes to Rome" (24 November 800), then the two activities of July 799; by `default`
all five were equally near.

## 5. Which dates count, and for what

- A **statement's** date counts for the statement and for the factoid it is in: a factoid has the dates of all its
  statements.
- A date an **entity** has itself (a person's birth, a feast's day) counts for the entity. An entity gets no time
  vector from the documents that name it: beside the graph it was found to add nothing.
- A date on anything else (a wrapper, an embedded object) counts for the factoid at the top only.
- A date that is only "unknown" counts for nothing; an item with no date has no time vector, and is found by the other
  parts of the profile alone.
- A date inside what a source **denies** (a statement in a space with `logical="not"`, such as `Negative[...]`) counts
  for nothing, for the statement or the factoid. A date in what a source only reports or thinks possible counts as
  any other. After upgrading, a project with semantic spaces has a rebuild of the time part due once (`pangloss
  vectors rebuild --part time`), and again whenever it changes a space's `veridical` or `logical`.
- A repeated date (a `Recurrence`) counts as the span it repeats over, not as its day of the year.

## 6. The two settings

You will rarely need them.

```python
DATES_VECTOR_WIDTH = 2          # years
DATES_VECTOR_DIMENSION = 128
```

- **`DATES_VECTOR_WIDTH`** is how vague a date is taken to be, in years: two dates a width apart are still fairly
  near, five widths apart they are not. Make it **as vague as your dates are**, and **no wider than the years
  between events that recur**. Keep 2 if your dates are mostly to the year or to a few years; set 1 if they are exact
  and you have events year after year. More than 0, at most 100.
- **`DATES_VECTOR_DIMENSION`** is how many places the years are spread over. The years go round them like a clock: at
  128 places of 2 years, two dates 256 years apart look the same to time alone. With the graph in the profile this
  hardly matters (the graph tells them apart). If time alone should tell centuries apart, make **the dimension times
  the width longer than the span of your dates**. A date longer than that (a period of centuries; a range whose start
  is unknown, which runs from `DATES_EARLIEST_YEAR`) says nothing of when: it is a little like every date. A whole
  number from 8 to 2048.

Both are checked when the models are initialised (`pangloss check`, or starting the server), and a value that is
not allowed is refused with what the setting should be. **A change of either makes a rebuild due** (`pangloss
vectors status` says so): run `pangloss vectors rebuild --part time`. A change of the dimension also changes the
indexes of every profile that weighs time: run `pangloss makemigrations` and `pangloss migrate` first.

## 7. Keeping it current

As with the other parts, the worker brings the time vectors of what you save up to date, exactly: a date added,
changed or taken away is right after the worker's next turn, and nothing is counted stale. Run `pangloss vectors
rebuild` after a large import, as for every part.

## Not yet

- A date on a wrapper counted for the statement that holds the wrapper (it counts for the factoid only).
- The rule of a repeated date (its day of the year) in the vector.
- An entity's time from the documents that name it (measured, and not worth it beside the graph).
