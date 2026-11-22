# The time part of similarity 🚧

`pangloss-dates-vectors`: the part `"time"` of [`pangloss-vectors`](vectors.md), a vector of each item from its
**dates** ([`pangloss-dates`](dates.md)), so that dates that overlap are near and dates years apart are not. Being
built as phase 9 of [the build plan](similarity-build-plan.md); its "9.2 as built" says what the maths is and how it
was measured. **This page is a stub**: step 9.5 writes it, with the guide and the demo.

```python
# settings.py
INSTALLED_APPS = [..., "pangloss_dates", "pangloss_vectors", "pangloss_dates_vectors"]
VECTORS_PROFILES = {"default": {"graph": 1, "class": 0.1, "time": 0.5}}   # the part counts only in a profile that weighs it
```

Needs `pangloss_vectors` and `pangloss_dates`, and a backend with Cypher and a vector index (`requires = {"cypher",
"vector_index"}`: Memgraph and Neo4j). Depends on numpy, imported only when a vector is made. `pangloss-dates` is not
changed and knows nothing of it.

## What is built (2026-11-22)

- ✅ **The maths** (`maths.py`, step 9.2): a date's four bounds (`earliest_fuzzy` … `latest_fuzzy`) as a line in
  pieces blurred by a logistic bump of `DATES_VECTOR_WIDTH` years, read at `DATES_VECTOR_DIMENSION` places a width
  apart that the years go round (`Ring`); an item's dates each at length one, added.
- ✅ **The settings** (`settings.py`): `DATES_VECTOR_DIMENSION` (a whole number from 8 to 2048, 128) and
  `DATES_VECTOR_WIDTH` (years, more than 0 and at most 100, 2), checked at `initialise()` when the app is installed.
  Both are in the part's signature, with the classes that have vectors.
- ✅ **The part** (`part.py`, step 9.3), at weight 0: in no profile until a project weighs it.
  - **Whose vector a date is.** A date held by a date (an end of a `DateRange`, the start or end of a `Period` or a
    `Recurrence`) counts for nothing itself. Any other date counts for what holds it, if that is a document or an
    entity, and for the head it is under (a factoid has the dates of all its statements); a date held by anything
    else (a reified relation, an embedded object, a semantic space) for the head only. A date whose precision is
    `unknown` counts for nothing. An item with no date that counts has no vector; so has an item of a class that has
    no vectors (`VECTORS_EXCLUDE`), or one a reader could not be shown (its head deleted, merged into another).
  - `rebuild`: every date read in pages (by the index of `PGIndexableNode(id)`), kept as four integers and the items
    it counts for, and the vectors made a thousand items at a time. `refresh`: the dates under the heads written (by
    the index of `PGIndexableNode(head_node_id)`; a date an entity holds itself has the entity's id there), and the
    time vector removed of a written head or a document under it that now has no date that counts; exact, nothing
    stale. `overlay`: the vectors of a plan's head and of the documents in it, from the planned nodes of its dates.
  - Tested on both backends with the suite every part passes (`pangloss_testing.parts.PartSuite`, on the models of
    `similar_models.declare(dated=True)`, whose payloads then say dates) and the part's own claims
    (`packages/pangloss-dates-vectors/tests/live/test_time_part_live.py`).
- ⏳ **Not built**: an entity's span (the dates of the documents that name it, step 9.4), the docs for a user, the
  guide and a profile with time in the demo (step 9.5); the queries measured at size on both backends (main's).
