# Matches criteria: someone described, not identified ⏳

**A specification, 2026-11-17. Nothing is built.** It follows the user's request of 2026-11-17 and their answers to
28 questions (the [Decisions](#decisions) at the end), and it was checked against the code the same day. It takes up
[notes/descriptions-and-assertions.md](../notes/descriptions-and-assertions.md), and departs from that record in one
main point: the description is **part of the document that mentions it**, not an entity of its own.

This page says what is to be built. How it came to be (each question with its options, the first plan, the review
of it against the code) is in [notes/matches-criteria-draft-2026-11-17.md](../notes/matches-criteria-draft-2026-11-17.md).

## Contents

- [The problem](#the-problem) and the feature [in short](#in-short)
- [What it looks like](#what-it-looks-like)
- [The model](#the-model)
- [What the core gains](#what-the-core-gains)
- [What is searched](#what-is-searched)
- [When it is evaluated](#when-it-is-evaluated)
- [The worker](#the-worker), [why it is exact](#why-it-is-exact), [measured](#measured-2026-11-17-before-building)
- [Derived facts in the criteria](#derived-facts-in-the-criteria)
- [Conditions relative to the document](#conditions-relative-to-the-document)
- [The same one in several places of a document](#the-same-one-in-several-places-of-a-document)
- [Shared descriptions](#shared-descriptions)
- [Identical criteria](#identical-criteria-evaluated-once)
- [Migrations](#migrations-that-make-a-pattern-invalid)
- [The API](#the-api), [the interface](#the-interface)
- [Other parts of Pangloss](#other-parts-of-pangloss), [where the code goes](#where-the-code-goes)
- [Steps](#steps-each-working-alone), [what is not yet known](#what-is-not-yet-known), [not in this plan](#not-in-this-plan)
- [Decisions](#decisions)

## The problem

Old data is full of "N. N., Maximilian's secretary". Neither way of entering it today is right:

| Way | What is wrong |
|---|---|
| A new `Person` for each mention | A singleton: one document, no other links. A dead end for networks, and it inflates counts |
| One `Person` "Maximilian's secretary" for all of them | Joins people who were probably different (he had several secretaries) |
| `Unreconciled` (`pangloss-review`) | The right kind of thing (part of the document, in an entity's place), but it holds only a label and waits for someone to choose one person |

What the source gives is a **description**: some person who was Maximilian's secretary. The wish is to store that
description as a search, and to have it **linked to every person it fits**, now and as data is added.

## In short

- **`MatchesCriteria[T]`** is a generic reified relation, shown as "Matches criteria". It holds the **criteria** (a
  structured-search pattern, the JSON of `POST /api/search`), an optional **wording** (what the source says), and a
  **`target`** list that the server fills: the **candidates**.
- A relation that takes a `Person` also takes a `MatchesCriteria[Person]`, when the entity class says so
  (`CriteriaMeta(allowed=True)`). It is offered as `Unreconciled` is.
- **A save only marks** the document as pending. A **background worker** runs the criteria, and runs them again
  whenever a write could change their result.
- The candidates are **computed, not asserted**. They are no part of a version: no `PGUpdate`, no history entry,
  no new `meta.version`. They are no references either: being a candidate does not protect an entity from deletion,
  and a merge does not move them.
- Because it is a reified relation, reads, the incoming lists of a candidate, the search form's "Through" and
  derived rules work with it as they do with any other.
- A new app, **`pangloss-criteria`**, holds the class, the worker, the routes, the commands and the interface module.
  The core gains general hooks, chiefly a field marker **`Computed()`** and **generic stand-ins**.

## What it looks like

```python
from pangloss_criteria import CriteriaMeta

class Person(Entity):
    _criteria_meta = CriteriaMeta(allowed=True)      # every relation that takes a Person takes a description too


class Activity(Statement):
    carried_out_by: list[InRole[Agent]]               # unchanged
```

Written from Python, or in a batch upload (the payload has the same shape):

```python
Activity(
    label="A letter carried to Innsbruck",
    carried_out_by=[InRole(
        role=courier,
        target=[MatchesCriteria[Person](
            wording="N. N., secretarius Maximiliani",
            criteria=Person.Where(incoming_=[Incoming(
                field="holder",
                from_=HoldsOffice.Where(office=secretary, employer=Rel(is_=maximilian)),
            )]),
        )],
    )],
)
```

As stored, and as the API reads it:

```json
{"type": "MatchesCriteria",
 "wording": "N. N., secretarius Maximiliani",
 "criteria": {"type": "Person", "$incoming": [{"field": "holder",
              "from": {"type": "HoldsOffice", "where": {"office": {"is": "…"}, "employer": {"is": "…"}}}}]},
 "target": [{"type": "Person", "id": "…", "label": "Johann Waldauf"}, {"type": "Person", "id": "…", "label": "…"}],
 "candidateCount": 3,
 "evaluatedWhen": "2026-11-17T10:12:00Z"}
```

`target`, `candidateCount` and `evaluatedWhen` are read-only. They may be sent back in an `Update` unchanged, as a
`DBField` may, and are ignored there.

## The model

```python
class MatchesCriteria[T](ReifiedRelation[T]):
    """Someone or something the source describes but does not name: whoever fits the criteria"""

    _meta = ReifiedRelation.Meta(label_index=True)        # the worker reads all of them by label
    _derived_meta = DerivedMeta(derivation="qualify")     # rules derive through it, and say so
    locals().update(interface_meta())                     # view_card / edit_card of the module

    # --- what the user writes ---
    wording: str | None = None
    """What the source says ("N. N., Maximilian's secretary")"""
    criteria: SearchPattern | None = None
    """A pattern of structured search whose root is one of the classes T allows"""
    same_as: UUID | None = None
    """Another description of this document: this is the same one, and has no criteria of its own"""
    description: Cites[Description] | None = None
    """A shared description, to which `criteria` adds conditions"""

    # --- what the worker writes ---
    target: Annotated[list[T], Computed()] = []
    candidate_count: Annotated[int, Computed()] = 0             # all of them, though at most 50 are linked
    candidate_count_everyone: Annotated[int, Computed()] = 0    # of what a reader who is not logged in sees
    evaluated_when: Annotated[datetime | None, Computed()] = None
    broken: Annotated[str | None, Computed()] = None            # why it is no longer evaluated (a migration)

    # --- what the server works out from the pattern when it is saved, for the worker ---
    criteria_hash: Annotated[str | None, DBField] = None  # the pattern, normalised
    depends_on: Annotated[list[str], DBField] = []        # the class labels the pattern touches
    names: Annotated[list[str], DBField] = []             # ids of every entity the pattern names
    anchors: Annotated[list[str], DBField] = []           # those of `names` every match must reach
    reach: Annotated[str | None, DBField] = None          # "local" | "far"
    shape: Annotated[str | None, DBField] = None          # the pattern without its ids and values
```

- **One of three forms**, checked on write: `same_as` alone; or `criteria`; or `description`, with or without
  `criteria`.
- **A view gives one count**, `candidateCount`: the reader's own of the two.
- **No label.** A reified relation has none. Its summary is made from `wording` and the criteria.

**`SearchPattern`** is a literal type that `pangloss-criteria` adds to the codec registry (`pangloss_models.literals`):

- It is stored as JSON text, since Neo4j cannot hold nested maps. It is exported with `format: "search-pattern"`.
- In Python it takes a `Model.Where` as well as the JSON.
- A `@create_validator`/`@update_validator` checks it with `check_match`. A field that does not exist is a 422 that
  names the path in the pattern. The root type must be one the relation allows.
- **Refused in a stored pattern:** `$same_as` (it stands for a cluster of entities read when the pattern is
  compiled, which the worker could not keep exact), a `$var`, and `$derived` until
  [its step](#derived-facts-in-the-criteria) is built.
- **Ids of merged entities** are resolved to their survivors when the pattern is evaluated. The stored pattern is
  not rewritten: that would change the document outside a save.

**`Description`** is a document, described under [Shared descriptions](#shared-descriptions).

### Why a reified relation

A `MatchesCriteria[T]` stands between a relation and its target, has fields of its own, and has a `target: list[T]`.
That is a reified relation, and most of what is needed follows:

| Needed | Already there, for a reified relation |
|---|---|
| Stored in the document, written and read with it | A node below the head, with `head_node_id` |
| Linked to every candidate | `target: list[T]` is an edge pair to each one |
| Read with the document | `build_fetch_document_query` follows forward edges to entities |
| Each candidate's page lists the documents it may be in | `read_incoming` through wrappers |
| Shown as a head bar with chips | The reified-relation card, which `InterfaceMeta(view_card=…)` replaces |
| A search can pass through it or not | The search form's "Through" pills |
| What derived rules do with it | `DerivedMeta(derivation=…)` |
| Nested inside other wrappers | `InRole[Agent \| MatchesCriteria[Agent]]`, as `Identification[WeightedAlternative[Person]]` is today |

What a reified relation lacks, and so what is new: a target the user does not write
([`Computed()`](#computed-what-the-server-keeps-up-to-date)); being offered without being in the annotation
([stand-ins](#stand-ins-that-are-generic)); a field that holds a search pattern (`SearchPattern`); and running
again when other data changes ([the worker](#the-worker)).

The other way considered was a document stand-in, as `Unreconciled` is, with the candidates kept apart as derived
facts are. It keeps computed edges out of the document's tree, but the incoming lists, the search form, the derived
rules and the display would each need their own code.

## What the core gains

Each of these is general: none names `pangloss-criteria`.

### `Computed()`: what the server keeps up to date

A marker in `Annotated` (`pangloss_models.markers`), for a relation or a literal of any model. A computed field:

| | |
|---|---|
| **In the models** | In `View`, `HeadView` and `ReferenceView`, and in the export (`computed: true`: the form shows it and does not edit it). Not in `Create` or `Update`; a value sent back from a read is taken out before the check |
| **Written by** | **`operations.set_computed(node_id, values, based_on_version)`**, a new operation of the kit, so an add-on needs no Cypher of its own. It writes the node's computed edges and properties in one transaction, only if the head is still at `based_on_version`. Otherwise it changes nothing and says so |
| **No version** | No `PGUpdate`, no new `meta.version`, no history entry. One write event of a new kind, `computed`, which history ignores and the interface's live feeds use |
| **History** | Left out of diffs, comparisons and restores. (Snapshots are the `UpdateDB` payload, which has no computed fields, so this needs little.) |
| **No reference** | A computed relation does not keep its target from being deleted, is not listed by `/deletable`, and does not count for `Usage` |
| **Merges** | A merge neither moves nor records a computed edge. It removes those that lead to the absorbed entity and marks their heads as written (`pending.mark_written`), so that whoever computes them does so again. No new version of those heads, and they do not count against `MERGE_LIMIT`. An undo marks in the same way |
| **Updates** | An update deletes the subtree and writes it again. For a node whose id is in the new tree and whose other fields are unchanged, the computed edges and values are **carried over**: read from the old tree before it is deleted, written with the new one. A node that changed starts empty |
| **Stand-ins** | A computed relation takes none (`stand_in_options` leaves it out). Otherwise `MatchesCriteria[Person].target` would itself be offered a `MatchesCriteria[Person]` |
| **Visibility** | A computed edge may carry `seen_by: "everyone" \| "logged_in"`. One fragment, `fragments.edge_visible(edge)` (`$see_unpublished OR coalesce(edge.seen_by, "everyone") = "everyone"`), is applied where a computed relation is followed: in the document read, in `read_incoming` and in the search compiler. `fragments.visible` judges nodes only, so this is new |
| **Reads** | Otherwise followed like any relation, so a candidate's incoming lists see it |
| **Tools** | `make-stubs`, the generated TypeScript types and `pangloss check` know it: read-only, not in `Create`/`Update` |

### Stand-ins that are generic

`hooks.StandIn` names a document class today, offered where an entity of the classes it stands for goes. It is
extended so that a stand-in may be a **generic class**, given the relation's entity classes as its parameter: a
relation to `Agent` (Person or Group, each with `CriteriaMeta(allowed=True)`) gets `MatchesCriteria[Person | Group]`.
The option is made at `initialise()`, as the generic uses that are written out are, with its own generated models.

- `NoCriteria()` on a field opts it out, as `NoUnreconciled()` does.
- A `ViaEdge[Person, Certainty]` takes it with the same edge properties, so "perhaps (60%) the secretary" can be said.
- Written in the annotation (`Person | MatchesCriteria[Person]`), the class works without this hook.

### Smaller additions

| Addition | Where | For |
|---|---|---|
| `exclude_wrappers` | an option of a search (`Match`), applied where the compiler handles wrappers (`Dialect.through_wrappers`), and handed to search extensions | A search that does not pass through named wrappers |
| `before_refs` | `hooks.pending_work`: a kind may ask that an update record what the old tree referred to | [The worker](#1-marking-in-the-writes-transaction) |
| A mark on a change of review status | `pangloss_cypher.review.set_review_status` calls `mark_written` | Publishing changes what everyone sees |
| An app hook in `migrate` | An app is given each change as it is applied, and may rewrite its own stored data | [Migrations](#migrations-that-make-a-pattern-invalid) |
| `migrations.patterns` | The walk over a stored search pattern, one change at a time | Shared by migrations and history |
| Search from an anchor | A second way to compile a pattern | [Evaluating](#5-evaluating) |

## What is searched

The criteria are a structured search with the root type they name, under five rules:

1. **Not through other descriptions.** A path of the search never passes through a `MatchesCriteria`
   (`exclude_wrappers=["MatchesCriteria"]`). If it could, one description's result would depend on another's
   candidates, and two descriptions could keep changing each other's results.
2. **Not what the same document names.** "N. N. and Johann, both his secretaries" does not offer Johann for N. N.
   The entities the head refers to are taken out of the result.
3. **Two results, by what may be seen.** One is of what everyone sees (published documents), one of what a
   logged-in reader sees. Each candidate edge carries `seen_by`, and a read keeps the edges its reader may see
   (`fragments.edge_visible`). There are two counts.
4. **A cap.** At most `CRITERIA_MAX_CANDIDATES` (50) edges are written, the first by label. The count is of all.
   More than the cap is shown as "too broad", in the dialog before saving and on the card after. Saving is allowed.
5. **Merged ids resolved.** The structured search does not do this today (`{"is": id}` of a merged entity matches
   nothing), so evaluation rewrites the ids in the pattern first.

What others see of the candidates:

| Reader | Sees |
|---|---|
| An ordinary search | Through to the candidates by default, as through any wrapper: "activities carried out by Waldauf" finds those where he is a candidate. "Through" in the search form leaves them out |
| Derived rules | Through it (`qualify`), with "MatchesCriteria" in the context of the justification, so such facts can be filtered. **Only the candidates everyone may see**: a derived fact is shown by the documents it rests on, and the document behind a `logged_in` candidate is not among them |
| Identity clusters | Nothing: a cluster follows an edge from a claim straight to an entity |
| RDF, usage, deletion | Nothing, by default: [below](#other-parts-of-pangloss) |

## When it is evaluated

**A save does not evaluate. It marks.** The head that holds the description is left pending in the save's
transaction, and the worker evaluates a moment later. So the candidates are **eventually consistent** from the first
save, as they are for every later change.

| | Evaluating on save (rejected) | Marking on save |
|---|---|---|
| Save time | One search for each description before the transaction: 1 to 60 ms, more for a broad one | One `MERGE` |
| Bulk imports | Every N. N. evaluated in the upload's path | Saves stay fast, and identical criteria are evaluated once |
| Code | Two paths that must agree, and a race between them | One path: the worker |
| Right after the save | Candidates there | Candidates follow (derived's delay was 291 ms median, 444 ms p95) |

**What the page shows right after a save:**

- A description with `evaluated_when` unset, or older than its head's last write, is **pending**. The card shows
  "Finding candidates…" with a faint spinner, never "No candidates".
- A description that was saved again unchanged keeps its candidates meanwhile (they are carried over).
- The page listens for the `computed` event of its head on a `live()` feed, as the review panel does, and fills
  the card in when it comes.
- Until then the card may show **the dialog's preview** (the count and 5 chips, greyed, marked "preview"), which
  the form still holds. This is optional. It keeps the card from flashing empty.
- If the worker is not running, the pending state lasts. After a few seconds the card says "Not yet evaluated: the
  background worker may be stopped", and `pangloss criteria status` shows the queue.

**For scripts and tests:** `save()` returns before the candidates are there.
`await pangloss_criteria.settled(head_id, timeout=...)` waits until that head's mark is completed.

## The worker

It keeps every description's candidates right as data changes. It is built on the queue `pangloss-derived` uses
(`pangloss_cypher.pending`), with the same guarantees:

- **Nothing is forgotten.** A mark is part of the write's transaction, so a committed write is always followed by
  a run, however the server stops.
- **It is exact in the end.** When writes stop and the queue is empty, each description's candidates are what a
  fresh evaluation would give. (One stated exception: [the count over the cap](#why-it-is-exact).)
- **It does not loop.** Writing candidates can never change another description's result (rule 1).
- **Saves stay fast.** A save adds one `MERGE`, and an update one read more.

### A worked example

Three descriptions exist: *A* "secretary of Maximilian", *B* "secretary of Sigismund", *C* "courier of
Maximilian". Someone saves a new `HoldsOffice`: Waldauf, secretary, employer Maximilian.

1. The save's transaction leaves `(:PGPending {kind: "criteria", head_id: <the HoldsOffice>})`.
2. A moment later the worker claims it and reads the head: its labels (`HoldsOffice`, `Statement`, …) and the
   entities it refers to (Waldauf, Maximilian, the office Secretary).
3. All three descriptions depend on `HoldsOffice`. *B* needs a document that names Sigismund, and this one does not,
   so *B* is skipped. *A* and *C* stay.
4. *A* and *C* are evaluated **from Maximilian**: the query starts at him and walks back along the pattern to the
   people it reaches. That is a full evaluation, in about a millisecond, against 110 ms for testing every person. A
   hundred descriptions of the same shape ("secretary of X") would be one query. Waldauf matches *A*; nobody
   matches *C*.
5. *A*'s candidates gain Waldauf. One `set_computed` writes the edge, with *A*'s head still at the version read.
   *C* has not changed, so nothing is written for it.
6. The claim is completed. An open page of *A*'s document gets a `computed` event and shows Waldauf.

### 1. Marking, in the write's transaction

There is **one kind of mark, `criteria`**, on a head. `hooks.pending_work` gives it for a class if either holds
(both worked out once at `initialise()`):

- some `MatchesCriteria[T]` could reach the class: the classes that `T`'s fields and incoming relations reach;
- the class can hold a description.

In the demo that is nearly every class. A write of any other class marks nothing.

| Write | Marks |
|---|---|
| Create, update, delete, undelete (`write_functions`) | The head, today |
| Merge and unmerge (`merge.py`) | The survivor and the absorbed entity, today. **New:** the heads whose computed edges led to the absorbed entity |
| Typology's `move` and `merge` (`relink.py`) | The heads, today |
| A change of review status | **New** (one `mark_written` call): publishing changes the result for everyone |
| `set_computed` | **Never `criteria`.** No description searches through candidates, so writing them changes no other result. It does mark the head's other kinds (`derive`): derived rules read the candidates |
| A bulk load | Nothing: `pangloss criteria rebuild` afterwards |

**What an update took away (`before_refs`).** A mark holds the head's id and a token. An update that removes
Waldauf from an activity leaves no trace of him, so nothing would say that he may no longer match. So an update of a
class that marks `criteria` collects, in its transaction and before it deletes the old tree, the ids of the
entities the old tree referred to. They are stored on the mark, joined with any already there (a head may be written
twice before it is claimed). It costs one read of the old tree's edges to entities (1.8 ms from Python, measured).
A delete needs none of this: a deleted head keeps its edges.

### 2. Claiming

`pending.claim`, unchanged: up to 200 heads under a 30-second lease. One worker runs at a time, as a
`BackgroundTask` of the server or as `pangloss criteria worker`. A write wakes it. One worker is what makes the
result exact, as for derived: each head is processed after its last write, reading the data as it then is.

### 3. Reading what was written

One query for the batch reads, for each claimed head, deleted or not:

- the **labels** of its nodes;
- the **descriptions inside it**, if any;
- the **seeds**: the entities its tree refers to now, plus `before_refs`, plus the head itself if it is an entity.
  Merged ids are resolved to their survivors, and the seeds are then widened with the ids of the entities merged
  into each of them (`PGMerge` by survivor). A description's `anchors` are stored as written, so without this one
  that names an absorbed entity would never be chosen. Nothing stored is rewritten, so undoing a merge needs no
  repair.

### 4. Choosing the descriptions

What the worker needs to know of a description is worked out from its pattern when it is saved:

| Field | What it is |
|---|---|
| `depends_on` | The class labels the pattern touches |
| `anchors` | Entity ids that every match must reach: `is`/`is_any` conditions outside `$not` and `$any_of`. For *A*, Maximilian |
| `reach` | **`local`** if every condition is on the root itself, or on documents that refer to it directly (with their nested parts, and which entities those name). **`far`** if the pattern goes on through a second entity to that entity's documents ("an office held under someone who was born in Vienna"), or has a condition on a field of an entity other than the root ("a transfer from someone whose gender is…": a write of that entity has only itself as a seed) |
| `shape` | The pattern with its ids and values taken out: every "secretary of X" has one shape |
| `criteria_hash` | The pattern, normalised: identical descriptions are evaluated once |

A description is chosen for a batch in one of three ways:

| The description | Chosen when |
|---|---|
| **Inside a claimed head** | Always, and evaluated in full. Its head was saved, or what its head names changed (rule 2), or a merge removed one of its candidates |
| **Cites a shared `Description`** that is a claimed head | Always (found by the citation's `target_id`) |
| **Any other**, if `depends_on` shares a label with the batch | By the table below |

| | Chosen when | Why that is enough |
|---|---|---|
| Anchored, `local` | An anchor, or one of its current candidates, is among the seeds | A match of *A* is a person with a document that refers both to them and to Maximilian. A document that names (and named) neither cannot make or unmake one |
| Anchored, `far` | Always | A document between the anchor and the root may name neither. Cheap all the same: from the anchor, grouped by shape |
| Not anchored, `local` | Always, evaluated only for the seeds | The seeds are all the roots a write can change |
| Not anchored, `far` | Always, in full | Nothing narrows it. The dialog warns of these, and `status` counts them |

Choosing is a scan of the descriptions: 9.4 ms for 10,000 with anchors and candidates as lists on each node, 5 ms
with them as small index nodes. The scan is enough to begin with.

### 5. Evaluating

| The description | How | Measured |
|---|---|---|
| Anchored | **From the anchor**: the query starts at the anchor and walks back along the pattern to the root, with the other conditions on the way. A full evaluation. The descriptions of one shape are one query (`UNWIND $rows`, a row for each: its anchor and values) | 0.9 to 1.6 ms for one; 4 ms from an entity with 3,113 activities; 116 of one shape in 15 ms; 5,000 in 105 ms |
| Not anchored, `local` | Root first, as the compiler does now, restricted to the seeds (`root.id IN $seeds`). The new candidates are the old ones, less the seeds, plus the seeds that match now | 1.7 to 2.5 ms with the seeds of one head; 8 to 11 ms with those of 200; 28 ms for a broad pattern |
| Not anchored, `far` | A full search | 80 to 166 ms each, more for broad patterns |
| Over the cap | A full count, and the first 50 by label linked | As a full search |

- **"From the anchor" is new work in the search compiler**: a second way to compile a pattern, starting at an
  entity it names and inverting the path to the root. It needs `WITH *` between its clauses, so that Memgraph starts
  where it is told (without them the same query took 35 to 119 ms). The anchor used is the one with the fewest edges
  of the relation it is reached by.
- **Two results** (rule 3): each query runs once as everyone and once as a logged-in reader, or once with a flag
  for each row if that measures cheaper.
- **Identical criteria** are evaluated once: [below](#identical-criteria-evaluated-once).
- **Rule 2** is applied afterwards, for each description: the result less the entities its head names.

### 6. Writing

- **Only what changed** is written, through `set_computed`, in transactions of up to 500.
- **A head that changed in the meantime** is refused by the version check, and nothing more need be done. The save
  that changed it marked it, after this batch was claimed, so a later run evaluates its descriptions in full.
- **Completing the claims** (`pending.complete`) is in the last transaction. A head marked again while it was
  worked on has a new token, stays pending, and is done again.
- **Failures.** On a transient error or a timeout the batch is halved and the worker backs off. A description
  whose pattern no longer passes `check_match` is set `broken`, so it is not retried for ever.

### 7. Commands

| Command | Does |
|---|---|
| `pangloss criteria status` | What is pending and claimed, the oldest mark; how many descriptions are `far`, too broad, or broken |
| `pangloss criteria explain <id>` | `local` or `far`, the anchors, which writes trigger it, and the queries |
| `pangloss criteria rebuild [--type Person]` | Every description evaluated in full. After a bulk load, a migration that touches a class the patterns name, or a change of the cap. Also a job of `/admin` (`admin.py`), since it runs long |
| `pangloss criteria check` | Patterns that no longer pass `check_match`, or that name a deleted entity |
| `pangloss criteria worker` | The worker in its own process (`CRITERIA_WORKER_IN_SERVER = False`) |

### Why it is exact

Take a description *D* and a person *P* whose match changed because of a write *W*.

- *D* is inside *W*'s head: it is evaluated in full.
- *D* is anchored and `local`: *W*'s head names, or named (`before_refs`), one of *D*'s anchors, or *P*, who is then
  a current candidate. So *D* is chosen, and evaluated in full from the anchor.
- *D* is anchored and `far`, or has no anchor and is `far`: it is chosen whenever a class it depends on is written,
  and evaluated in full.
- *D* has no anchor and is `local`: *W*'s head refers, or referred, to *P*, so *P* is a seed.
- The run that processes *W* reads the data after *W* committed, and after any later write of the same head, since
  a head written again is done again.
- A result refused by the version check is made good by the mark of the save that caused the refusal.

So when the queue is empty, every description has been evaluated after the last write that could change it.

**The stated exception: over the cap, the count is approximate.** A write that unmakes a match that is not linked
(the person is deleted, or a condition on the person's own fields no longer holds) names neither an anchor nor a
linked candidate, so the description is not chosen. The card says "more than 50 (about N)", and `rebuild` makes the
count exact. Counting exactly would be a full search on every such write, for a description already called too
broad.

**The test** is a churn test, as derived's is: several writers create, update, delete, merge and publish while the
worker runs. Then `rebuild` must find nothing to change, on both backends.

### Measured, 2026-11-17, before building

On the identity scratch Memgraph (3.14.0, :7690): **792,907 nodes**, the bulk load of 2026-11-13 (60,000 people,
5,000 sources, 30,000 factoids of 2 or 3 statements: 82,355 activities, 22,307 transfers) and the leftovers of the
measuring then (some people with 3,000 references). Docker on a laptop (8 CPUs), one process, through the models'
connection, so every time includes a round trip from Python (1 to 1.5 ms). Medians of 7 runs after one to warm up.

Nothing is built, so these are **prototypes**: patterns compiled by today's search compiler, that compiler's query
with its first `MATCH` restricted to the seeds by hand, and hand-written Cypher for evaluating from the anchor. The
script is `pangloss-demo/criteria_benchmark.py`, to be run from a copy of the demo whose settings point at a scratch
database (its header says how).

The patterns, all of people:

| | Pattern | Found |
|---|---|---|
| P1 | received a transfer from X (`$incoming` `given_to` from a `Transfer` whose `given_by` is X) | 2 |
| P2 | witnessed an activity of X (through `InRole`) | 4 |
| P3 | P1 in a given year (the date's fuzzy bounds compared) | 1 |
| P4 | carried out a battle: no anchor, broad | 15,302 |
| P5 | received a transfer from someone who witnessed an activity of X: `far` | 2 |

**Evaluating one description:**

| | Root first, every person tested | Restricted to the seeds of 1 head (~11) | Of 200 heads (~1,226) | From the anchor |
|---|---|---|---|---|
| P1 | 118 ms | 2.5 ms | 10.8 ms | **0.9 ms** |
| P2 | 132 ms | 2.0 ms | 9.2 ms | **1.6 ms** (4.0 ms from the person with 3,113 activities) |
| P3 | 110 ms | 1.7 ms | 8.2 ms | **1.4 ms** |
| P4 | 81 ms | 2.5 ms | 27.6 ms | (no anchor) |
| P5 | 166 ms | 2.3 ms | 10.1 ms | (not prototyped: the same walk, two steps longer) |

Each restricted result was the full result less what is not a seed, and the anchored P1 was the compiler's full
result. Compiling a pattern in Python (`check_match` and `build_search_query`) takes 0.22 ms.

**A batch:**

| What | Measured |
|---|---|
| Reading the seeds and labels of 1 factoid / of 200, in one query | 1.8 ms (6 entities) / 27 ms (1,225 entities) |
| Choosing among 1,000 / 10,000 descriptions (lists on each node; 5% far, 5% unanchored) | 4.6 ms / 9.4 ms (148 / 1,349 chosen) |
| The same with index nodes for anchors and candidates | 4.1 ms / 5.0 ms |
| 200 written factoids against 5,000 descriptions "received a transfer from X" | 116 chosen |
| Those 116, compiled and evaluated in full, root first | about 12.8 s |
| Those 116, restricted to the seeds, one query each | 974 ms |
| Those 116, from the anchor, one query each | 86 ms |
| **Those 116, from the anchor, one query for the shape** | **15 ms** |
| All 5,000, from the anchor, one query (a rebuild of the shape) | 105 ms, 5,953 candidates |

**What the numbers decided:**

1. **Evaluate from the anchor**: exact and cheapest, and a hub costs little.
2. **Group by shape from the start**: 15 ms against 86 ms. The query's text stays the same, so its plan is kept.
3. **Seeds remain for descriptions with no anchor.** A few hundred of them would make a batch take seconds.
4. **Descriptions that are `far` and not anchored are the expensive case**: 80 to 166 ms each, on every write of a
   class they depend on. With anchored descriptions only, a batch of 200 heads is about 27 (seeds) + 10
   (choosing) + 15 (evaluating) ms before writing: several thousand heads a second, against 900 for derived. Not
   measured end to end.
5. **`WITH *` between the clauses** of the anchored query is necessary.

## Derived facts in the criteria

"Someone of the Medici household" may be a derived fact (`$derived`: the entity has a fact of a derived class,
fitting a filter). Plainly allowed, it would make a loop: candidates make derived facts (`qualify`), and a pattern
with `$derived` would read them back. It is allowed under three rules, each general:

1. **Criteria do not see facts that rest on a description.** A justification records the wrappers it passed through
   (`PGJustification.context_labels`, where `qualify` puts "MatchesCriteria"). Evaluated with
   `exclude_wrappers=["MatchesCriteria"]`, `$derived` counts a fact only if one of its justifications has none of
   the excluded labels. The compiler hands the option to the extension, and `pangloss-derived` adds the condition
   inside the comprehension of `derived_visible` that finds the justifications. This is rule 1 of
   [What is searched](#what-is-searched) again, so the worker still cannot loop. An ordinary search is unchanged.
2. **A change of facts marks.** When derived's worker writes or withdraws facts, it marks, in that transaction, the
   entities they relate for every other kind of work their class asks for (`hooks.pending_kinds`, less its own).
   `pangloss-derived` names no other package. The criteria worker finds those entities as claimed heads, and so as
   seeds.
3. **Choosing.** `$derived` gives no anchor in the first version. On the root it is `local`; on another entity,
   `far`.

What follows:

- **A limit.** A person whose membership of the household is itself derived only through a description is not
  matched. That is the price of not looping.
- **Two stages.** A write is followed by derived's run, then by this one. "When the queue is empty" means both
  queues, and the churn test runs both workers.
- **Visibility** needs nothing new: `$derived` is compiled with `derived_visible`, so each of the two results sees
  the facts its reader would.
- **A rule that is changed or switched off** changes facts without a write of a document. Derived's rebuild marks
  as in 2, and `pangloss criteria rebuild` is the fallback.
- **Without `pangloss-derived`** the key does not exist, and `check_match` refuses it as today.
- **Until this step is built**, `$derived` in a stored pattern is a 422 that says why.

## Conditions relative to the document

"N. N., Maximilian's secretary" in a factoid of 1495 means his secretary **in 1495**. So a value in a pattern may
come from the document that holds the description:

```json
{"type": "Person", "$incoming": [{"field": "holder", "from": {"type": "HoldsOffice", "where": {
    "employer": {"is": "…maximilian…"},
    "when": {"overlaps": {"$document": {"field": "date"}}}}}}]}
```

- **`{"$document": {"field": "date", "of": "Factoid"}}`** is the value of a field of the nearest document of that
  class that holds the description (by default, the head). A path may go through embedded objects
  (`"date.earliest"`). The field may be a literal, an embedded date, or a relation to an entity, which gives ids for
  `is`/`is_any` ("employer is the person this factoid is about").
- **Dates:** `overlaps`, `within` (with `days`), `during`, `before` and `after` compare the two dates' bounds as
  `pangloss_dates.rules` does for derived rules, fuzzy by default. They are no new search operators: a function of
  `pangloss-dates`, called when the pattern is resolved, expands them to conditions on the stored bounds. In
  Python: `pangloss_dates.criteria.overlaps(document("date"))`.
- **Checked on write:** the path must exist on the class named, with a type that fits the condition (a 422 that
  names the path). `POST /api/search` refuses `$document`: it has no document. The preview route resolves it from
  the form's current values, which the dialog sends.
- **A document with no value there:** the condition cannot hold, so there are no candidates, and the card says
  "This document has no date: the criteria need it". The condition is never dropped.
- **Evaluating:** `$document` values are resolved for each mention before it is hashed, so mentions with the same
  criteria and different dates are different groups. A change of the document's date is a write of its head, which
  marks it.
- **Migrations:** `$document` paths are field names, rewritten by renames and broken by removals, like the rest of
  a pattern.
- **In the dialog:** a value box has "from this document", listing the fields that fit by type. A date field gets
  "overlaps / within … days of / during / before / after *this document's date*". The summary reads: *holder of a
  HoldsOffice (employer: [Maximilian I], at the time of this factoid's date)*.

## The same one in several places of a document

"N. N., Maximilian's secretary, carried the letter (statement 1) and was paid for it (statement 2)." Both places
mean one person. A second, identical description does not say that: **two descriptions with equal criteria are not
one person** ("two of Maximilian's secretaries witnessed it"). Identity has to be said.

**"The same one as."** The first place holds the criteria. Every other place holds a `MatchesCriteria` with
`same_as: <the id of that part>` and no criteria of its own.

- **A property, not an edge**, as a citation's `target_id` is: an edge between two parts of one tree would make the
  read nest one under the other. Checked on every write: the part must exist in the same head, be a
  `MatchesCriteria`, and be a first place (no chains). It survives updates, since nested parts keep their ids.
- **Candidates:** the worker evaluates the first place and writes the same candidate edges to every place, so each
  field's lists on a candidate's page are right.
- **Removing the first place** while others point at it: the form moves the criteria to the next place. The API
  refuses a write that leaves a `same_as` pointing at nothing (a 422 that names the field).
- **In the form:** the relation's search box offers "The one described above: *Maximilian's secretary* (statement
  1)" for each first place in this form. Pasting a description into the same document asks "the same one, or
  another with the same criteria?".
- **On the card:** "the same one as in *statement 1*", with the summary and the candidates. Its pencil edits the
  first place.
- **Resolving** puts the chosen person in every place at once.

Rejected: a hidden list of the document's unknowns at the head, with places pointing into it (one node reached
along several edges of one tree, which the read does not allow, and close to an "inline entity"); and counting
equal criteria in one document as one person (wrong for "two secretaries").

## Shared descriptions

Building the same criteria by hand in 200 documents is slow, and gives 200 copies that a correction must each reach.

**`Description`** is a head document with a label ("Maximilian's secretary"), `criteria`, and a page of its own. A
mention cites it: `MatchesCriteria(description=Cites[Description], criteria=<optional extra conditions>)`. The
mention's criteria are the shared ones **and** its own (both must hold; the root type is the same).

| | |
|---|---|
| **One definition** | Evaluated once for its mentions (they group by hash), and fixed in one place |
| **Editing it** | Changes the candidates of every mention, and citations are built for this: the edit raises `PanglossCitedError` unless acknowledged, each mention shows `changed_since_cited`, history keeps both versions. The worker then chooses every mention that cites it |
| **Who may edit** | Anyone logged in, with the acknowledgement. Finer permissions are the open item in `TODO.md` |
| **Deleting it** | Refused while it is cited, unless an admin says `"removals"` |
| **Its page** | Says first: "A description used by 214 mentions. It does not say that they are one person." It lists its mentions and its candidates, and has no incoming lists of its own. A description with `$document` conditions has no single result: its page says "the candidates depend on each document" |
| **Not an entity** | It asserts nothing, and nothing is said about it. It is a document that is cited, which keeps "documents contain; entities are referred to" true. Listed under its own type, left out of search everything unless the project asks (`global_search`) |
| **Not reviewed** | No `ReviewMeta`: it is always published. Otherwise a published mention could cite an unpublished description |
| **`$document` in it** | Resolved against each citing document. A document that cites one must have the fields it names (checked when cited) |
| **Narrowing** | "Maximilian's secretary, *in 1495*": the summary shows both, *Maximilian's secretary* + date in 1495 |

**Copy beside Use.** The dialog's "Start from" menu lists the shared descriptions, each with **Use** (cite) and
**Copy** (the criteria become the mention's own, with no link).

## Identical criteria, evaluated once

This matters most for imported data, where hundreds of mentions have the same criteria.

- **The canonical form,** from which `criteria_hash` is made: snake_case keys, keys sorted, the members of `is_any`,
  `in` and `$all` sorted, empty conditions dropped, values in their stored form, the root type included. Two
  patterns that mean the same but are written differently (a `$not` of `ne` against `eq`) are not found equal. The
  result is still right, only evaluated twice.
- **The worker groups in memory** at each run, after resolving merged ids and `$document` values. The stored hash,
  of the pattern as written, is for finding duplicates.
- **A group is evaluated once**, without rule 2. Each mention's result is that result less the entities its own
  head names: a set difference in Python.
- **A new mention** whose group has a current result (none of its heads pending) is given a copy. If the copy is a
  moment stale, a later run corrects it, since the write that made it stale left a mark.
- **In the interface:** the dialog says "The same criteria are used in 12 other documents", and offers to make
  them one shared description, for the user to confirm.

## Migrations that make a pattern invalid

A stored pattern names classes, fields, enum values and wrappers, so a migration can make it wrong.
`pangloss_history.upgrade` already brings a stored version of a document forward through the migrations, one change
at a time. Patterns get the same treatment, with the walk in one shared place
(`pangloss_models.migrations.patterns`), used by migrations and by history (so that restoring an old version
upgrades the patterns in it).

**When:** in `pangloss migrate`, through the app hook: an app is given each change as it is applied, and rewrites
its own stored data. A migration is not a user's edit, so this writes no `PGUpdate`.

| Change | What happens to a pattern |
|---|---|
| `RenameModel` | `type` and the classes named in `$incoming`, `$somewhere` and `$spaces` are rewritten |
| `RenameField`, `RenameRelation` | The keys of `where` on that class and its subclasses, `field` in `$incoming`, `order_by` and `$document` paths are rewritten |
| `RenameEnumMember` | Nothing (the value is stored, not the name) |
| `AlterEnumMemberValue` | The values in `eq`/`in` conditions are rewritten |
| `AlterLiteralType` | The values compared are converted, as history converts them. One that cannot be converted makes the pattern **broken** |
| `AlterCardinality`, `AlterReverseName`, `AlterEdgeModel`, `WrapRelation`, `UnwrapRelation`, `ChangeWrapper` | Nothing, or the wrapper's name in "Through" rewritten |
| `RemoveField`, `RemoveRelation`, `DeleteModel`, `RemoveEnumMember`; `AlterRelationTarget` that leaves a nested type out | **Broken.** The condition is never dropped: dropping "employer is Maximilian" would widen the description to every secretary |
| `RunPython`, `RunCypher` | Unknown. Every pattern is checked again afterwards, and a migration may call `pangloss_criteria.rewrite(function)` |

After the migration every pattern is checked again with `check_match`, and every description whose classes the
migration touched is marked pending.

**A broken description** is no longer evaluated. It keeps its last candidates, marked "out of date since migration
*0021*". It is listed by `pangloss criteria check` and on a page of broken descriptions, and opens in the dialog
with the failed condition in red. Saving it again is an ordinary update. Reads never fail on one.

## The API

| Route | |
|---|---|
| `POST /api/criteria/preview` | `{criteria, document?, field?}` gives `{count, candidates: [5 ReferenceViews], tooBroad}`, under the rules of an evaluation (so not simply `/api/search`). Open to anyone who may write |
| `GET /api/criteria/{id}/candidates?page=` | All the candidates of one description, in pages |
| `GET /api/criteria?type=&q=&page=` | Descriptions, by the type they describe and their wording |
| `GET /api/criteria/similar/{id}` | Others with the same `criteria_hash` |

The SDK gets each (`pangloss_criteria.preview(...)` and so on), with `settled()`, and the contract tests its rules
ask for. A client never calls `set_computed`.

## The interface

A module of `pangloss-criteria` (`interface/`), with `view_card` and `edit_card` set by the class's
`InterfaceMeta`, as `Unreconciled`'s are. Every string is a `t()` slot, in English, German and French. Every entity
shown is a `ReferenceChip`.

### In a form

- **The relation's search box** offers "+ Describe instead…" under the results (where the buttons of reified
  relations are), and the field's type menu lists "Matches criteria".
- That opens a **dialog** (the pattern of `ReconcilePanel` and the create-entity type dialog), holding:
  - the **type** described: a `TypeGrid`/`TypeMenu` of the relation's classes that allow it, skipped when there is
    one;
  - "**Start from**": the shared descriptions, each with Use and Copy;
  - a **wording** box;
  - the **search form** of that type: `SearchPanel`'s `NodeFields`, taken out of the list page's sliding panel into
    a component both use, with no Order by and no saved searches. A value box has "from this document";
  - **the result**, run a moment after the last change, as the list's search is: up to 5 chips and "N candidates
    found", or "No candidates yet: it will update as data is added", or "Too broad: N found, at most 50 are
    linked". A `far` description with no anchor is warned of here;
  - Done / Cancel.
- **Closed**, the card is a head bar ("Matches criteria", the reified-relation tint) with the summary and a pencil,
  then the preview's 5 candidates, marked as not saved yet.
- **Editing a saved one** needs the pattern turned back into the form's state. The form keeps a richer state
  (`NodeSearch`, with the labels of the entities picked), and only the compiled `Where` is stored. So a decompiler,
  `whereToForm(match)`, is written beside `compileSearch`, and the labels come from `/api/references`. A pattern the
  form cannot show (written in Python with something the form lacks) opens read-only, with the JSON and a message.
  A round-trip test (`compileSearch ∘ whereToForm` is the identity on what the form makes) keeps the two in step.
- **Pasting** a description (the clipboard) drops its computed fields.

### In a view

- **The card:** a head bar with "Matches criteria", the wording in quotation marks, the summary; then the
  candidates as chips (5, then "and N more", which opens the paged list); and "N candidates · updated …" in small
  text. Too broad: the count and no chips. Pending: "Finding candidates…". Broken: "out of date since migration …".
  A deleted entity in the criteria: "names a deleted entity".
- **On a candidate's page** the document is in the ordinary lists of what refers to them, marked **"identified as
  candidate"**, followed by the summary in short form, so the reader sees by what it was matched: *carried out by ·
  identified as candidate · Person · holder of a HoldsOffice (office: [Secretary], employer: [Maximilian I])*.
- **The summary** is made by one function used everywhere (`describeCriteria`), from the pattern and the translated
  names of fields and types: a sentence, with entities as chips and nesting in brackets. Past about 120 characters
  it is cut with "…", with the full text on hover and in the dialog.
- **Resolving:** a button on the card, "This is…", shows the candidates. Choosing one puts it in the description's
  place, in every `same_as` place too, as reconciling an `Unreconciled` does (an update of the document). The
  criteria stay in the document's history.

## Other parts of Pangloss

| Part | What happens |
|---|---|
| History | Computed fields are in no diff, comparison or restore; `computed` events are not recorded. A restored version is evaluated again after it is saved. Patterns in old versions are upgraded with `migrations.patterns` |
| Search | Sees through to the candidates by default; "Through" leaves them out. Criteria never pass through descriptions |
| Derived rules | `qualify`, reading only the candidates everyone sees. A change of candidates marks `derive`. **Fan-out to watch:** a pair rule over an activity with a description of 50 candidates makes 50 times the facts, which change whenever the candidates do. `pangloss derive dry-run` before a rule is switched on |
| Review | An unresolved description is not a task of review: it is a finished statement of what the source says. A change of review status marks |
| Merges | Candidate edges are not moved. Those to the absorbed entity are removed and their heads marked; the worker evaluates again, since the survivor may now fit or not |
| Deletion | A candidate can be deleted. An entity the criteria **name** that is deleted makes them match nothing: the card says so, and `check` lists these. Nothing is shown on the named entity's page |
| Identity clusters | Candidates join none |
| Citations | `Cites` on a reified relation works today. A computed change is no new version, so it changes no `changed_since_cited` |
| Label templates | A placeholder that reaches through the relation gives the wording (or the summary), never the candidates' labels: a label is filled on save, and the candidates change without one |
| RDF | Candidates are left out of the dump by default (they are not assertions). `RDFMeta` can include them as `pangloss:candidate` |
| Usage | A person who is only a candidate is not "referred to" for `Usage(include_only_when_referenced=…)` |
| Bulk load | Writes the description and no candidates; `rebuild` afterwards |
| Stubs, TS types, language server | Know `Computed()` and the generic stand-in |
| Admin | `rebuild` as a job |

## Where the code goes

`pangloss-criteria` is a package of its own, since it has everything an app can have. (`pangloss-library` is for
ready-made models with no machinery.) It `requires` nothing: it goes through the models and the kit's operations.

| Where | What |
|---|---|
| `pangloss-criteria` | `MatchesCriteria`, `Description`, `CriteriaMeta`, `NoCriteria`, `SearchPattern` and its codec; hashing, `shape`, `reach`, `anchors`; the worker; `/api/criteria/…`; `pangloss criteria …` and the admin job; the migration rewrites; the interface module (dialog, cards, summary); translations |
| `pangloss-models` | `Computed()` in the generated models, the export, stubs and TS types; generic stand-ins; `before_refs` for a kind of pending work; the app hook in `migrate`; `migrations.patterns`; `exclude_wrappers` in `Match`, handed to extensions |
| `pangloss-cypher` | `operations.set_computed`; computed edges in an update (carried over), a merge (removed, heads marked), `delete_node` and usage (not counted); `fragments.edge_visible` in the document read, `read_incoming` and the search compiler; `exclude_wrappers` and compiling from an anchor in the search compiler; the mark on a change of review status; `before_refs` on update |
| `pangloss-derived` | Rules read only the candidates everyone sees. For `$derived` in criteria: the key honours `exclude_wrappers`, and the worker marks the entities whose facts change |
| `pangloss-dates` | The date conditions of `$document` (`pangloss_dates.criteria`) |
| `pangloss-history` | Computed fields left out of diffs and restores; patterns upgraded |
| `pangloss-testing` | Conformance tests of everything in the `Computed()` table and of `exclude_wrappers`, on both backends |
| `pangloss-sdk` | The criteria routes and `settled()` |
| `pangloss-lsp` | `Computed()` and the stand-in in `pangloss check` |
| `interface-core` | The search form's fields as a component a dialog can hold; `whereToForm`; computed fields read and not edited; a `live()` feed for a pending card |

## Steps, each working alone

1. **`Computed()` in the core.** Everything in [its table](#computed-what-the-server-keeps-up-to-date) but
   visibility: the marker, the models, export, stubs and TS types; `set_computed` with its version check; the
   `computed` event; history; no reference (deletion, usage); merges; carried over by an update; no stand-ins.
   Conformance tests on both backends.
2. **`SearchPattern`**: the codec, the check of a stored pattern and what it refuses, `exclude_wrappers` in the
   search compiler, resolving merged ids in a pattern.
3. **`pangloss-criteria`: the class, the mark on save, and a first worker** that evaluates in full every
   description inside a saved head (claiming, `set_computed`), with the cap, rule 2, and the two results with
   `fragments.edge_visible`. **The edge test is measured on the scratch database before it is kept.** `settled()`.
   Python and API tests, with the class written in the annotation.
4. **Generic stand-ins**, `CriteriaMeta` and `NoCriteria()`. The demo gets `CriteriaMeta` on `Person`, and a
   migration.
5. **Keeping up with other writes**, by full evaluation first: marking by class, the mark on a change of review
   status, `before_refs`, derived reading only what everyone sees, and the churn test.
6. **Evaluation from the anchor**, grouped by shape; seeded evaluation; `reach`, `anchors`, `shape`; choosing;
   `explain`, `rebuild`, `check`, `status`. Measured again on the scratch database, and on Neo4j.
7. **The interface**: the shared search form, the dialog, the preview, the cards, the summary, the decompiler,
   resolving. `e2e/COVERAGE.md`, the dev-mode test.
8. **`same_as`**, and grouping identical criteria.
9. **Migrations of stored patterns**: the shared upgrader, the app hook in `migrate`, broken descriptions and
   their page.
10. **Shared descriptions**: `Description`, cited, with extra conditions; "Start from", Use and Copy; the offer to
    share identical criteria.
11. **Conditions relative to the document**: `$document`, the date conditions, the write check, "from this
    document", the summary.
12. **`$derived` in the criteria**: the option handed to extensions, the condition on `context_labels`, derived's
    marks, the churn test with both workers. Measured first.
13. The RDF rule, the admin job, the docs (`status.md`, a guide page), the Pangloss skill.

## What is not yet known

These can only be settled by building and measuring. Each says where.

| Unknown | If it goes badly | Step |
|---|---|---|
| The cost of `edge_visible` in the document read, the incoming lists and the search | Fall back to one result of published documents only. Then a factoid in review makes nobody a candidate until it is published, and derived needs no special rule | 3 |
| Making a generic stand-in at `initialise()` (read, not prototyped) | The class written in the annotation, field by field | 4 |
| Carrying computed values over in an update, and merges leaving them out: both change core write paths | Candidates emptied on each save and refilled by the worker | 1 |
| Evaluating from the anchor through wrappers (the prototype had none), and everything on **Neo4j** | Seeded evaluation, at 8 to 28 ms a description | 6 |
| Whether a migration is one transaction on both backends, for the app hook | The rewrite of patterns as a step after the migration, with `check` as the guard | 9 |
| `$derived` restricted to seeds, and the extra marks in derived's writes | `$derived` stays refused | 12 |

Also not measured: the mark in a save (derived's was 0.1 to 0.9 ms), `before_refs` inside an update, writing
candidate edges, the delay from a save to the candidates on the page, and saves while the worker runs.

## Not in this plan

- **A lens** (reading under chosen authors, sources, certainty), from the discussion record.
- **Weights** for each candidate (1/k in a network export): `pangloss derive graph` could use the count later.
- **Turning existing singleton people into descriptions** in bulk: a script or an admin job, once the class exists.
- **A shared description as an entity** (the record's "hub"). A cited document is in the plan instead.
- **"The same N. N." across documents**: a claim that parts of two documents are one, like `SameEntity` for parts.
- **`$same_as` in criteria.** Later it could be allowed as `far`, depending on every class with an
  `IdentityClaim()` field.

## Decisions

The user's, 2026-11-17. The options of each question are in the
[draft](../notes/matches-criteria-draft-2026-11-17.md). Q23 to Q28 came from the check against the code.

| Q | Decided |
|---|---|
| Q1 | A field takes a description by a setting on the entity class (`CriteriaMeta(allowed=True)`), with `NoCriteria()` to opt a field out |
| Q2 | `MatchesCriteria`, shown as "Matches criteria" |
| Q3 | A reified relation whose `target` is computed |
| Q4 | Ordinary searches see through to the candidates by default; "Through" leaves them out |
| Q5 | `qualify`: derived rules read through descriptions, with "MatchesCriteria" in the context |
| Q6 | Two results: what everyone sees, what a logged-in reader sees |
| Q7 | At most 50 linked (a setting), the full count stored, "too broad" shown, saving allowed |
| Q8 | Entities the same document names are never candidates |
| Q9 | "This is…" puts the chosen entity in its place (in every `same_as` place); the criteria stay in history |
| Q10 | Not a task of review |
| Q11 | Conditions relative to the document are in the first version (`$document`) |
| Q12 | The ids the criteria name are kept for the worker only; nothing on the named entity's page |
| Q13 | A new package, `pangloss-criteria` |
| Q14 | In the ordinary lists of a candidate's page, marked "identified as candidate" (not "possibly"), with the criteria in short form |
| Q15 | The summary is a sentence, with entity chips and brackets |
| Q16 | The dialog's preview runs a moment after each change |
| Q17 | "The same one as" (`same_as`) |
| Q18 | A shared `Description`, cited, with the mention's own extra conditions; Copy beside Use |
| Q19 | Anyone logged in may change a shared description, with the citation's acknowledgement |
| Q20 | A migration that removes what a pattern needs makes it broken; its last candidates kept, marked out of date |
| Q21 | The dialog offers to make identical criteria one shared description |
| Q22 | A save only marks; the worker evaluates; the card shows "Finding candidates…" until the result arrives |
| Q23 | A merge leaves computed edges out: none moved or recorded, no new versions, not counted |
| Q24 | An entity that is only a candidate can be deleted |
| Q25 | `seen_by` on each computed edge, tested by one fragment in the read, the incoming lists and the search; two counts; to be measured |
| Q26 | Derived rules read only the candidates everyone may see |
| Q27 | An update carries the candidates over where the description is unchanged |
| Q28 | `$same_as` refused in criteria. `$derived` allowed, under three rules, in a step of its own |

Three smaller choices were made by the author under the user's "your recommendations", and are easy to reverse:
**one kind of pending mark** (not a second for "a head that holds a description"); **the count over the cap is
approximate** until a rebuild; **a `Description` is not reviewed**.
