# Matches criteria: someone described, not identified 🚧

**A specification, 2026-11-17, being built since 2026-11-19: what is built, step by step, and where it differs
from what is written here, is in [As built](#as-built) at the end.** It follows the user's request of 2026-11-17 and their answers to
28 questions (the [Decisions](#decisions) at the end), and it was checked against the code the same day. It takes up
[notes/descriptions-and-assertions.md](../notes/descriptions-and-assertions.md), and departs from that record in one
main point: the description is **part of the document that mentions it**, not an entity of its own.

This page says what is to be built. How it came to be (each question with its options, the first plan, the review
of it against the code) is in [notes/matches-criteria-draft-2026-11-17.md](../notes/matches-criteria-draft-2026-11-17.md).

**Reviewed 2026-11-19** against `pangloss-derived` as it now is (derived edges, edges declared on documents, derived
documents: [derived-edges-and-documents.md](derived-edges-and-documents.md), built 2026-11-18), and corrected in
place. Still nothing of this plan is built. What changed:

- A new section, [With derived edges and documents](#with-derived-edges-and-documents), and a new
  [step 6](#steps-each-working-alone) for it. The later steps are one number higher (`$derived` is now step 13).
- `MatchesCriteria` is **`exclusive`** for rules: one justification takes at most one candidate of a description.
  The plan had missed this, and an edge declared on a document (`CoParticipants`) makes it matter at once.
- A rule that derives a **document** does not read through a description unless it says so, and criteria do not read
  a document derived through one (decided in the other plan, D10 and D19; how it is done is now said here).
- The mark on a change of review status, and `hooks.work_marked`, are **built** (by the other plan). `set_computed`
  uses them.
- Search patterns have gained `Through` steps with conditions, conditions on an edge, and flags
  (`$derived_document`). What a stored pattern may hold, the migrations of patterns and the form's decompiler take
  them into account.
- Four calls of the author, listed at the end of [Decisions](#decisions), for the user to confirm.

## Contents

- [The problem](#the-problem) and the feature [in short](#in-short)
- [What it looks like](#what-it-looks-like)
- [The model](#the-model)
- [What the core gains](#what-the-core-gains)
- [What is searched](#what-is-searched)
- [When it is evaluated](#when-it-is-evaluated)
- [The worker](#the-worker), [why it is exact](#why-it-is-exact), [measured](#measured-2026-11-17-before-building)
- [Derived facts in the criteria](#derived-facts-in-the-criteria)
- [With derived edges and documents](#with-derived-edges-and-documents)
- [Conditions relative to the document](#conditions-relative-to-the-document)
- [The same one in several places of a document](#the-same-one-in-several-places-of-a-document)
- [Shared descriptions](#shared-descriptions)
- [Identical criteria](#identical-criteria-evaluated-once)
- [Migrations](#migrations-that-make-a-pattern-invalid)
- [The API](#the-api), [the interface](#the-interface)
- [Other parts of Pangloss](#other-parts-of-pangloss), [where the code goes](#where-the-code-goes)
- [Steps](#steps-each-working-alone), [who builds each](#who-builds-each-step), [what is not yet known](#what-is-not-yet-known), [not in this plan](#not-in-this-plan)
- [Decisions](#decisions)
- [As built](#as-built)

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
  derived rules work with it as they do with any other. For rules its candidates are alternatives: a derived edge
  through one is qualified, and a derived document is made through one only by a rule that says so.
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
    # rules derive through it and say so; its candidates are alternatives (one of them for each justification)
    _derived_meta = DerivedMeta(derivation="qualify", exclusive=True)
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
  compiled, which the worker could not keep exact), a `$var`, `$derived` until
  [its step](#derived-facts-in-the-criteria) is built, and a `through` that names `MatchesCriteria` (rule 1 of
  [What is searched](#what-is-searched)).
- **Allowed, as in any search:** a `through` step with conditions (`Through(WeightedAlternative,
  edge=Likelihood.Where(...))`), a condition on a relation's edge (`Rel(edge=...)`), and a flag of an extension
  (`$derived_document`: "said by a document a person wrote"). For the worker a `through` with conditions is part of
  the pattern's `shape`, and the classes it names are in `depends_on`.
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
| **In the models** | In `View`, `HeadView` and `ReferenceView`, and in the export (`computed: true`: the form shows it and does not edit it). Not in `Create` or `Update`; a value sent back from a read is taken out before the check. A computed literal is in the class's `Where` (a wrapper has one of its own values since 2026-11-17), so a search or a rule can ask "a description with at most three candidates" |
| **Written by** | **`operations.set_computed(node_id, values, based_on_version)`**, a new operation of the kit, so an add-on needs no Cypher of its own. It writes the node's computed edges and properties in one transaction, only if the head is still at `based_on_version`. Otherwise it changes nothing and says so. In that transaction it marks the head with the pending work of its class, less the kinds its caller names (`pending.mark_written(..., less=)`, new), and after the commit it tells `hooks.work_marked` (built), so that another app's worker wakes |
| **No version** | No `PGUpdate`, no new `meta.version`, no history entry. One write event of a new kind, `computed`, which history ignores and the interface's live feeds use |
| **History** | Left out of diffs, comparisons and restores. (Snapshots are the `UpdateDB` payload, which has no computed fields, so this needs little.) |
| **No reference** | A computed relation does not keep its target from being deleted, is not listed by `/deletable`, and does not count for `Usage`. The edge pair carries `computed: true`, and one fragment (`fragments.asserted(edge)`) leaves it out of `uses_of`, the check before a delete and the merge's relinking. This is by edge, where `hooks.references_not_counted` (built for derived documents) is by class. In the three queries that count every edge of every item of a class the test is made only if some model has a computed relation: that is what the same test cost for shortcut edges (a fifth more, measured 2026-11-18) |
| **Merges** | A merge neither moves nor records a computed edge. It removes those that lead to the absorbed entity and marks their heads as written (`pending.mark_written`), so that whoever computes them does so again. No new version of those heads, and they do not count against `MERGE_LIMIT`. An undo marks in the same way |
| **Updates** | An update deletes the subtree and writes it again. For a node whose id is in the new tree and whose other fields are unchanged, the computed edges and values are **carried over**: read from the old tree before it is deleted, written with the new one. A node that changed starts empty |
| **Stand-ins** | A computed relation takes none (`stand_in_options` leaves it out). Otherwise `MatchesCriteria[Person].target` would itself be offered a `MatchesCriteria[Person]` |
| **Visibility** | A computed edge may carry `seen_by: "everyone" \| "logged_in"`. One fragment, `fragments.edge_visible(edge)` (`$see_unpublished OR coalesce(edge.seen_by, "everyone") = "everyone"`), is applied where a computed relation is followed: in the document read, in `read_incoming` and in the search compiler. `fragments.visible` judges nodes only, so this is new |
| **Reads** | Otherwise followed like any relation, so a candidate's incoming lists see it |
| **A change of class** | A document whose class is changed in place (`changing_class_from`, built 2026-11-18) is an update: carried over under the same rule |
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
| A mark on a change of review status ✅ | **Built 2026-11-18** for derived documents: `review.mark_status_changed` (a change of status, and `set_published` of a class that is not reviewed) marks the head for every kind its class asks for, and `hooks.work_marked` wakes the workers | Publishing changes what everyone sees |
| Conditions on the head of each document of a pattern | `pangloss_models.search.head_conditions`: for a search with `exclude_wrappers`, an app gives a condition that the compiler puts where it tests whether the reader sees the head. An ordinary search has none | [Documents derived through a description](#with-derived-edges-and-documents) |
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
| Rules that derive edges | Through it (`qualify`), with "MatchesCriteria" in the context of the justification, so such facts are not plain and can be filtered. **One candidate of a description for each justification** (`exclusive`), so its candidates are never related to each other. **Only the candidates everyone may see**: a derived fact is shown by the documents it rests on, and the document behind a `logged_in` candidate is not among them |
| Rules that derive documents | Not through it, unless the rule says `allow=[MatchesCriteria]`. Then the document records it (`derived_context`), and criteria do not read that document: [below](#with-derived-edges-and-documents) |
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
`await pangloss_criteria.settled(head_id, timeout=...)` waits until that head's mark is completed. That is the
description's first result. With `pangloss-derived` a later one may follow (a derived document that the criteria
read is written by its own worker, after the save): `await pangloss_criteria.idle(timeout=...)` waits until no work
of any kind is pending (`pending.count` of every kind the apps ask for), which is what a test of the two together
needs.

## The worker

It keeps every description's candidates right as data changes. It is built on the queue `pangloss-derived` uses
(`pangloss_cypher.pending`), with the same guarantees:

- **Nothing is forgotten.** A mark is part of the write's transaction, so a committed write is always followed by
  a run, however the server stops.
- **It is exact in the end.** When writes stop and the queue is empty, each description's candidates are what a
  fresh evaluation would give. (One stated exception: [the count over the cap](#why-it-is-exact).)
- **It does not loop.** Writing candidates can never change another description's result (rule 1), nor, by way
  of a derived rule, its own ([with derived edges and documents](#with-derived-edges-and-documents)).
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
| A change of review status | The head, today (built 2026-11-18): publishing changes the result for everyone |
| The derived worker writes, changes, deletes or publishes a derived document | The head, today: each is an ordinary write, or a change of whether it is published |
| The author of a converted document clears its `derived_context` | The head, today (`convert.clear_context`): criteria may read it from then on |
| `set_computed` | **Never `criteria`** (`less=["criteria"]`). No description searches through candidates, so writing them changes no other result. It does mark the head's other kinds (`derive`), and wakes their workers: derived rules read the candidates |
| A bulk load | Nothing: `pangloss criteria rebuild` afterwards |

**What an update took away (`before_refs`).** A mark holds the head's id and a token. An update that removes
Waldauf from an activity leaves no trace of him, so nothing would say that he may no longer match. So an update of a
class that marks `criteria` collects, in its transaction and before it deletes the old tree, the ids of the
entities the old tree referred to. They are stored on the mark, joined with any already there (a head may be written
twice before it is claimed). It costs one read of the old tree's edges to entities (1.8 ms from Python, measured).
A delete needs none of this: a deleted head keeps its edges. (`pending.mark` sets a mark's properties today; a list
that is joined is new in it, and is given only for a kind that asks.)

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
- **It takes edges as the compiler does**: through `fragments.forward` and the dialect's wrapper paths (which
  followed reverse edges until 2026-11-17), with the path's tests (`Compiler.path_tests`, `edge_tests`) for
  `through` steps and edge conditions, and with `edge_visible` and the head conditions. So a shortcut of a derived
  edge (an edge between two entities that is of no field) is never walked. A pattern it cannot invert (a `through`
  with a condition on the way to the anchor, at first) is evaluated by seeds.
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
- *W* is the derived worker's: a derived document is a head like any other, with labels and the entities it names,
  so each case above holds for it. Whether criteria read it at all (`derived_context`) is on its head, and changes
  only by a write of it or by `clear_context`, which both mark.

So when the queue is empty, every description has been evaluated after the last write that could change it. With
`pangloss-derived`, "the queue" is every kind of both packages.

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

(2026-11-19: that database has since been migrated to the demo's `0022` and holds about 1.03 million nodes, 33,000
derived factoids among them. The numbers below are of the day they were taken. When they are taken again in steps
6 and 7, the derived factoids are there to measure the head condition against.)

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
   entities they relate for every other kind of work their class asks for (`hooks.pending_kinds`, less its own
   three: `derive`, `derive-retractions`, `derive-documents`), and tells `hooks.work_marked`. The entities are the
   two ends **and every qualifier entity** (the group of a `SameGroup`): a `$derived` filter can name any of them.
   `pangloss-derived` names no other package. The criteria worker finds those entities as claimed heads, and so as
   seeds. Edges declared on a document (`DerivesEdge`) are ordinary derived edges, and are covered. Derived
   documents need none of this: they are written by saves.
3. **Choosing.** `$derived` gives no anchor in the first version (an end that the filter names is the *other* end
   of the edge, as built: it could be an anchor later). On the root it is `local`; on another entity, `far`. The
   ids its filter names are in `names`, so that merged ones are resolved.

What follows:

- **A limit.** A person whose membership of the household is itself derived only through a description is not
  matched. That is the price of not looping.
- **Two stages.** A write is followed by derived's run, then by this one. "When the queue is empty" means every
  queue of both, and the churn test runs both workers ([the order of things](#the-order-of-things)).
- **A derived class that is renamed or removed** is no migration of the models. A pattern that names it no longer
  passes `check_match`: `pangloss criteria check` lists it, and the worker sets it `broken`.
- **Visibility** needs nothing new: `$derived` is compiled with `derived_visible`, so each of the two results sees
  the facts its reader would.
- **A rule that is changed or switched off** changes facts without a write of a document. Derived's rebuild marks
  as in 2, and `pangloss criteria rebuild` is the fallback.
- **Without `pangloss-derived`** the key does not exist, and `check_match` refuses it as today.
- **Until this step is built**, `$derived` in a stored pattern is a 422 that says why.

## With derived edges and documents

Added 2026-11-19. `pangloss-derived` now has derived edges (`DerivedEdge`, and `DerivesEdge` declared on a document
class) and **derived documents**: a rule whose head is a document, written by the worker through the ordinary
saves ([derived.md](derived.md)). The decisions that touch this plan were taken there (D8, D10, D17, D19). This
section says what follows for descriptions, and [step 6](#steps-each-working-alone) builds it.

| | What holds | What it needs |
|---|---|---|
| **A rule that derives an edge** | Reads through a description (Q5). The edge is not plain: "MatchesCriteria" is in the context of the justification | `derivation="qualify"` on the class. It has to be said: since 2026-11-17 a reified relation with no `DerivedMeta` is transparent |
| **Candidates are alternatives** | One justification takes at most one candidate of a description. Otherwise `CoParticipants`, declared on `Activity` as `participants` × `participants`, would relate every two candidates of one "N. N." to each other: 1,225 edges from 50 candidates, all of them wrong | `exclusive=True` on the class. `store.one_of_each` goes by the wrapper's id and the next node of the path, so by the code it holds for a reified relation with a list of targets. It has only been used on conjunctions: tested in step 6 |
| **Only the candidates everyone may see** (Q26) | For edges and for documents alike. A derived document is published when every document it rests on is, and the document behind a `logged_in` candidate is not among them | One condition in the rule compiler, on the edge that leaves a wrapper (where `Through(..., edge=)` is tested): a computed edge is followed only if `seen_by` is "everyone". General: it names no class |
| **A rule that derives a document** | Does not read through a description. A document would say plainly what is only one of several candidates | Nothing: for a document rule `qualify` is `block`, unless the rule says `allow=[MatchesCriteria]` (built) |
| **A document rule that allows it** | The document has "MatchesCriteria" in its `derived_context`. So has a document further down a chain, and one a person has made their own, until its author clears it (D19) | Built |
| **Criteria read derived documents** (D10) | "Someone said by a derived factoid to be a sibling of X" is a criterion like any other. The worker's writes are saves, so they mark `criteria`; the status the worker gives a document makes the two results | Nothing |
| **But not one derived through a description** | Such a document names a candidate plainly, outside any `MatchesCriteria`, so rule 1 of [What is searched](#what-is-searched) does not stop a search reading it. Criteria do not read inside a document whose `derived_context` names an excluded wrapper | `search.head_conditions` ([Smaller additions](#smaller-additions)). `pangloss-derived` gives, for a search with `exclude_wrappers`, `NOT any(l IN coalesce(head.derived_context, []) WHERE l IN $excluded)`. It is on the head property, not the class, because a converted document is a `Factoid` that still has it. Measured in step 6 |
| **A filter of the user's own** | "Said by a document a person wrote": the flag `$derived_document: false` on a document of the pattern | Built. A flag is allowed in a stored pattern |
| **No description in a template** | A derived document says what follows. It does not describe someone anew | A stand-in is not offered in a `Template`, and a class with a computed relation has none. General: `pangloss-derived` reads `Computed()`, and names no class |
| **Asking something of the description** | A rule or a search can pass only through descriptions that are narrow: `Through(MatchesCriteria, where=...)` on `candidate_count_everyone` | Computed literals in the wrapper's `Where`. A change of the count is a `set_computed`, which marks `derive` |
| **Shortcut edges** (`Meta(shortcut=True)`) | No criteria follow one. It is of no field, so no pattern can name it | The compiler from an anchor takes edges through `fragments.forward`. The conformance test of shortcuts (`test_shortcut_edges.py`) gains the anchored search |
| **A shared `Description`** | Never a derived class. Its mentions cite it with `Cites`, which protects | Nothing. Where a project has derived documents, every `Cites` field also takes a `PGCitedBasis`; for this field none is ever made, since a `Description` is not derived |
| **`_derived` on a candidate's page** | Edges derived through a description are listed with their context, as those through a `Negative` are | Nothing |

### The order of things

One save can now be followed by several runs, each marking the next through `hooks.pending_work`:

1. A person saves a document. It is marked `derive` and `criteria`.
2. **Derived:** edges are written. Derived documents are queued (`derive-retractions`, then `derive-documents`) and
   saved one by one. Each such save is marked `criteria`, and `derive` if a rule reads it.
3. **Criteria:** the descriptions are evaluated, reading what people wrote and what step 2 wrote. `set_computed`
   marks the changed heads `derive`, never `criteria`.
4. **Derived again:** rules read the new candidates. Edges through them are written, qualified. Documents through
   them are written only by a rule that allows it, and carry the context. Each such save is marked `criteria`.
5. **Criteria again:** the descriptions chosen are evaluated, and nothing has changed for them. So nothing is
   written, nothing is marked, and it ends.

**Why the last run finds nothing.** A description's result is made from three things: documents people wrote; derived
documents with no "MatchesCriteria" in their `derived_context`; and, with `$derived`, edges that have a
justification with none in its context. None of the three depends on any candidate. (Rules read documents, never
derived edges, and their chains have no cycle, so there is no other way round.) What the fourth run writes is, for the
criteria, not there.

**What it costs.** The last run is work with no result: a description is chosen when a document just written names
one of its anchors or candidates. It is the price of a rule that allows `MatchesCriteria`, and it is in what step 6
measures. The fan-out is the other cost: a document rule over an activity with a description of 50 candidates
writes 50 documents (17 ms each, measured), and writes them again as the candidates change. `pangloss derive
dry-run` before such a rule is switched on.

**The delay** is the sum of the stages. A candidate that rests on a derived document appears after derived's run
(0.95 s median behind a save, measured 2026-11-18) and then this worker's.

**The test** is the churn test with both workers, and a rule of each kind: an edge rule through descriptions, a
document rule that allows them, and criteria that read derived documents. When every queue is empty, a rebuild of
either package finds nothing to change, and no history has gained a version.

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
- **For derived rules the places are one alternative.** `exclusive` goes by the wrapper's node, so two places would
  let one justification take Waldauf for the first and another candidate for the second, and relate the two. So
  `DerivedMeta(exclusive="same_as")`: the wrapper is exclusive together with the one its field names. A small
  addition to `pangloss-derived` (the rule query returns that property, and `one_of_each` groups by it), which names
  no class.
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
| `RenameModel` | `type` and the classes named in `$incoming`, `$somewhere` and `$spaces` are rewritten; so are a wrapper named in `through` and an edge model named in an `edge` condition |
| `RenameField`, `RenameRelation` | The keys of `where` on that class and its subclasses, `field` in `$incoming`, `order_by` and `$document` paths are rewritten; so are the keys of the `where` of a `through` step (the wrapper's own values) and of an `edge` condition (the edge model's) |
| `RenameEnumMember` | Nothing (the value is stored, not the name) |
| `AlterEnumMemberValue` | The values in `eq`/`in` conditions are rewritten |
| `AlterLiteralType` | The values compared are converted, as history converts them. One that cannot be converted makes the pattern **broken** |
| `AlterCardinality`, `AlterReverseName`, `AlterEdgeModel`, `WrapRelation`, `UnwrapRelation`, `ChangeWrapper` | Nothing, or the wrapper's name in "Through" rewritten |
| `RemoveField`, `RemoveRelation`, `DeleteModel`, `RemoveEnumMember`; `AlterRelationTarget` that leaves a nested type out | **Broken.** The condition is never dropped: dropping "employer is Maximilian" would widen the description to every secretary |
| `RunPython`, `RunCypher` | Unknown. Every pattern is checked again afterwards, and a migration may call `pangloss_criteria.rewrite(function)` |

After the migration every pattern is checked again with `check_match`, and every description whose classes the
migration touched is marked pending.

A key of an extension (`$derived`, `$derived_document`) is the extension's own: the walk leaves it as it is, and the
check afterwards finds one that no longer holds.

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
  The form's state has flags since 2026-11-18 (`NodeSearch.flags`: "derived: yes / no"), which the decompiler
  gives back. A `through` step with conditions and a condition on an edge are not in the form, so a pattern with
  one opens read-only.
- **Pasting** a description (the clipboard) drops its computed fields.

### In a view

- **The card:** a head bar with "Matches criteria", the wording in quotation marks, the summary; then the
  candidates as chips (5, then "and N more", which opens the paged list); and "N candidates · updated …" in small
  text. Too broad: the count and no chips. Pending: "Finding candidates…". Broken: "out of date since migration …".
  A deleted entity in the criteria: "names a deleted entity".
- **A derived document never holds one** (no description in a template), so its page, which has no editing, needs
  nothing. It can be among what makes someone a candidate: the short summary on the candidate's page is the same.
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
| Derived edges | `qualify` and `exclusive`, reading only the candidates everyone sees. A change of candidates marks `derive`. **Fan-out to watch:** a pair rule over an activity with a description of 50 candidates makes 50 times the facts, which change whenever the candidates do. `pangloss derive dry-run` before a rule is switched on |
| Derived documents | Made through a description only by a rule that allows it, and then not read by criteria. Read by criteria otherwise. Hold no description. [Above](#with-derived-edges-and-documents) |
| Review | An unresolved description is not a task of review: it is a finished statement of what the source says. A change of review status marks |
| Merges | Candidate edges are not moved. Those to the absorbed entity are removed and their heads marked; the worker evaluates again, since the survivor may now fit or not |
| Deletion | A candidate can be deleted. An entity the criteria **name** that is deleted makes them match nothing: the card says so, and `check` lists these. Nothing is shown on the named entity's page |
| Identity clusters | Candidates join none |
| Citations | `Cites` on a reified relation works today. A computed change is no new version, so it changes no `changed_since_cited` |
| Label templates | A placeholder that reaches through the relation gives the wording (or the summary), never the candidates' labels: a label is filled on save, and the candidates change without one |
| RDF | Candidates are left out of the dump by default (they are not assertions). `RDFMeta` can include them as `pangloss:candidate` |
| Usage | A person who is only a candidate is not "referred to" for `Usage(include_only_when_referenced=…)`. Nor is one named only by derived documents (built, by class) |
| Bulk load | Writes the description and no candidates; `rebuild` afterwards |
| Stubs, TS types, language server | Know `Computed()` and the generic stand-in |
| Admin | `rebuild` as a job |

## Where the code goes

`pangloss-criteria` is a package of its own, since it has everything an app can have. (`pangloss-library` is for
ready-made models with no machinery.) It `requires` nothing: it goes through the models and the kit's operations.

| Where | What |
|---|---|
| `pangloss-criteria` | `MatchesCriteria`, `Description`, `CriteriaMeta`, `NoCriteria`, `SearchPattern` and its codec; hashing, `shape`, `reach`, `anchors`; the worker; `/api/criteria/…`; `pangloss criteria …` and the admin job; the migration rewrites; the interface module (dialog, cards, summary); translations |
| `pangloss-models` | `Computed()` in the generated models (`Where` too), the export, stubs and TS types; generic stand-ins; `before_refs` for a kind of pending work; the app hook in `migrate`; `migrations.patterns`; `exclude_wrappers` in `Match`, handed to extensions and to `search.head_conditions` |
| `pangloss-cypher` | `operations.set_computed`; computed edges in an update (carried over), a merge (removed, heads marked), `delete_node` and usage (not counted: `fragments.asserted`); `fragments.edge_visible` in the document read, `read_incoming` and the search compiler; `exclude_wrappers`, the head conditions and compiling from an anchor in the search compiler; `pending.mark_written(less=)`; `before_refs` on update. (The mark on a change of review status is built) |
| `pangloss-derived` | Rules follow a computed edge only if everyone may see it; `exclusive` tested on a reified relation, and by a field (`exclusive="same_as"`); the head condition on `derived_context`; no stand-in and no class with a computed relation in a `Template`. For `$derived` in criteria: the key honours `exclude_wrappers`, and the worker marks the entities whose facts change (ends and qualifiers) |
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
   migration (after `0022_derived_factoid`). The stand-in is offered in the fields of `Factoid`'s statements, and
   not in a `Template`.
5. **Keeping up with other writes**, by full evaluation first: marking by class, `before_refs`, a test that a
   change of review status is followed (the mark is built), and the churn test.
6. **With `pangloss-derived`** ([above](#with-derived-edges-and-documents)): rules follow only the computed edges
   everyone sees; `exclusive` on a reified relation, tested with `CoParticipants`; a document rule with and without
   `allow=[MatchesCriteria]`; no description in a `Template`; `search.head_conditions` and derived's condition on
   `derived_context`, **measured on the scratch database before it is kept**; `idle()`; the churn test with both
   workers. The demo's rules are run against a description (`siblings`, `GaveTo`, `CoParticipants`).
7. **Evaluation from the anchor**, grouped by shape; seeded evaluation; `reach`, `anchors`, `shape`; choosing;
   `explain`, `rebuild`, `check`, `status`. Measured again on the scratch database, and on Neo4j.
8. **The interface**: the shared search form, the dialog, the preview, the cards, the summary, the decompiler,
   resolving. `e2e/COVERAGE.md`, the dev-mode test.
9. **`same_as`** (with `exclusive="same_as"` for rules), and grouping identical criteria.
10. **Migrations of stored patterns**: the shared upgrader, the app hook in `migrate`, broken descriptions and
    their page.
11. **Shared descriptions**: `Description`, cited, with extra conditions; "Start from", Use and Copy; the offer to
    share identical criteria.
12. **Conditions relative to the document**: `$document`, the date conditions, the write check, "from this
    document", the summary.
13. **`$derived` in the criteria**: the option handed to extensions, the condition on `context_labels`, derived's
    marks (ends and qualifiers), the churn test with both workers. Measured first.
14. The RDF rule, the admin job, the docs (`status.md`, a guide page, the "Matches criteria" table of
    `derived-edges-and-documents.md` as built), the Pangloss skill.

## Who builds each step

Added 2026-11-19, at the user's request, after step 4: which agent suits each of the steps that are left. The agents
are those of `.claude/agents/`: **`builder`** (Opus: builds decided work from a written brief, with its tests, and
does not commit) and **`test-runner`** (Sonnet: runs tests and reports what failed). **Main** is the session that
holds the plan (Fable).

The same division holds for every step:

- **Main** settles what the plan leaves open, makes any change to a core write or read path, takes the measurements
  the plan asks for "before it is kept" and decides on them, writes the briefs, reads each diff that comes back,
  writes the step's "As built" section, and commits.
- **`builder`** builds what is decided: the package's own code from a brief, the tests, the demo's changes with
  their migration and stubs, the guide, `status.md` and the skill.
- **`test-runner`** makes every run: a file while building, and `./run_tests.sh` before the commit.
- **`Explore`** (on Sonnet or Haiku) answers "where is this done, and what reads it" before a brief is written.

A step is for `builder` when a brief can say all of it. It stays with main when what to build depends on what is
found on the way, or on a number.

| Step | Mostly | Main keeps | To `builder` |
|---|---|---|---|
| 5. Keeping up with other writes | Main, then `builder` | `before_refs` inside an update, and marking by class reached: both are core write paths, and the marks decide whether the worker is exact | The churn test from a brief; the test that a change of review status is followed |
| 6. With `pangloss-derived` | Main | `search.head_conditions` and derived's condition, measured on the scratch database, and what to do if it measures badly (the user's choice); `exclusive` on a reified relation, which was read and never run | The demo's rules run against a description; the document rule with and without `allow=`; `idle()` and its tests |
| 7. Evaluation from the anchor | Main | The second way to compile a pattern, `reach`, `anchors`, `shape`, and why the result is still exact; the measurements on Memgraph and Neo4j | `explain`, `rebuild`, `check`, `status` as commands with their tests and `guide/cli.md`, once the functions under them exist |
| 8. The interface | `builder`, in parts | The split into parts and the order; the review of each against the interface's rules (Solid 2.0, Tailwind, chips, the styling rules in memory); what the dialog and the cards show, with the user | Each part from its own brief: the search form's fields as a component a dialog can hold; `whereToForm` (the decompiler); the dialog with its preview; the cards and the summary; resolving ("This is…"); translations; the browser tests, `e2e/COVERAGE.md` and the dev-mode test |
| 9. `same_as`, and grouping identical criteria | `builder` | The write check of the three forms; `exclusive="same_as"` in derived's store | The field, its validator and tests; grouping by `criteria_hash` in the worker, with a test that the result is the same as without it |
| 10. Migrations of stored patterns | Main, then `builder` | The app hook in `migrate`, and whether a migration is one transaction on both backends (not yet known) | `migrations.patterns` (the walk over a pattern, one change at a time) with a test for each kind of change; broken descriptions and their page |
| 11. Shared descriptions | `builder` | How a citation's acknowledgement meets the carry-over of step 1 (a changed `Description` starts its citers empty) | `Description`, the citation with extra conditions, "Start from", Use and Copy, the offer to share identical criteria: model, API and interface as separate briefs |
| 12. Conditions relative to the document | Main, then `builder` | `$document` in the compiler and in the stored pattern's check; what it does to `shape` and to the marks (a document's own change now changes its descriptions' results) | The date conditions in `pangloss_dates.criteria`, the write check, "from this document" in the dialog, the summary |
| 13. `$derived` in the criteria | Main | All of it but the tests: it is measured first, it adds marks to derived's writes, and "`$derived` stays refused" is its fallback | The churn test with both workers, from a brief |
| 14. RDF rule, admin job, docs, skill | `builder` | A reading of the docs against the code | All of it. The session that runs this step could itself be on a cheaper model |

What this is worth is not known: no step has been built this way yet. Steps 1 to 4 were built by main alone. Two
cautions from that: a brief costs something to write and its result has to be read, so a small change that touches
several core files is cheaper done directly; and a report from an agent is a claim, checked against the diff and a
run of the tests.

## What is not yet known

These can only be settled by building and measuring. Each says where.

| Unknown | If it goes badly | Step |
|---|---|---|
| The cost of `edge_visible` in the document read, the incoming lists and the search | Fall back to one result of published documents only. Then a factoid in review makes nobody a candidate until it is published, and derived needs no special rule | 3 |
| Making a generic stand-in at `initialise()` (read, not prototyped) | The class written in the annotation, field by field | 4 |
| Carrying computed values over in an update, and merges leaving them out: both change core write paths | Candidates emptied on each save and refilled by the worker | 1 |
| The head condition on `derived_context`: a test of a list on the head of every document a criteria search passes | Criteria read no derived document at all (a test of the head's labels, as `block=` by head class, which measured as free). That goes against D10, so it is the user's to decide. A converted document would then be read, context or not | 6 |
| `exclusive` on a reified relation with a list of targets (read in the code, never run) | The exclusive test written for it in `store.one_of_each` | 6 |
| The runs with no result after a document rule that allows descriptions | Such rules are warned of at `initialise()` | 6 |
| Evaluating from the anchor through wrappers (the prototype had none), and everything on **Neo4j** | Seeded evaluation, at 8 to 28 ms a description | 7 |
| Whether a migration is one transaction on both backends, for the app hook | The rewrite of patterns as a step after the migration, with `check` as the guard | 10 |
| `$derived` restricted to seeds, and the extra marks in derived's writes | `$derived` stays refused | 13 |

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

Taken in the other plan ([derived-edges-and-documents.md](derived-edges-and-documents.md)), 2026-11-17, and
followed here:

| | Decided |
|---|---|
| D8, D17 | A reified relation is transparent for rules unless its class says otherwise. `MatchesCriteria` says `qualify` |
| D10 | Criteria read derived documents, except those resting on a description |
| D19 | A converted document keeps its `derived_context`, and the exclusion still applies to it until its author clears it |
| Rule 2 there | A document rule reads through a description only with `allow=[MatchesCriteria]`. No `MatchesCriteria` in a `Template` |

**Calls of the author in the review of 2026-11-19, to confirm:**

1. **`exclusive=True`**: the candidates of one description are never related to each other by a rule. (And
   `exclusive="same_as"`, so that the places of one description are one alternative.)
2. **The exclusion is a condition on the head's `derived_context`**, given by `pangloss-derived` through a general
   hook of the search, not a test of the class. If it measures badly, the choice is the user's (the first row added
   to [What is not yet known](#what-is-not-yet-known)).
3. **Computed literals are in `Where`**, so a rule or a search can ask for descriptions with few candidates.
4. **`settled()` waits for the head's own mark**, and `idle()` for every queue.

## As built

The plan above stays as it was written. This says what of it is built, and where the code differs.

### Step 1: `Computed()` in the core ✅ (2026-11-19)

Everything in [its table](#computed-what-the-server-keeps-up-to-date) but visibility (step 3). On both backends.

| What | Where |
|---|---|
| The marker `Computed()`, and `is_computed(definition)` | `pangloss_models.markers`. Exported from the root with `ComputedTarget` and `ComputedWrite` |
| Which fields of which models; `has_computed()`, `has_computed_relations()` | `pangloss_models.computed` |
| Not in `Create`, `Update`, `CreateDB`, `UpdateDB`; a value sent back is taken out before the check | `ModelKind.skip_computed` (`kinds.py`), `without_server_keys` |
| The export says `computed: true`, and the interface's export `readOnly: true` (a form leaves a read-only field out, the item's page shows it) | `export.py`, `pangloss_interface.meta` |
| `set_computed(node_id, values, based_on_version=None, *, less=())` and `set_computed_batch(writes, *, less=(), then=None)` | `pangloss_cypher.computed`, in `operations` |
| An update carries what was computed over | `computed.before_replace`, `carry_over`, called by `replace_head_in` |
| A merge and a delete take the computed edges to the entity away, and mark their heads | `computed.drop_edges_to`; an undo of a merge marks with `mark_heads_with_edges_to` |
| No reference | `fragments.asserted(edge)`; `fragments.reference(edge)` and `counted_edge` apply it only if some model has a computed relation |
| `pending.mark_written(..., less=)` | `pangloss_cypher.pending` |
| The event `computed` | `WriteEvent.op`; `pangloss-history`'s listener leaves it out |

**How the code differs from the plan, or says more than it:**

- **"Unchanged" is decided by a basis.** A node whose class has computed fields is written with `pg_computed_basis`: a
  hash of its class, its own values and everything below it (what it refers to by id; a nested node by what it says,
  not by its id). An update carries over what was computed for a node of the new tree that has the same id and the
  same basis. The plan said "whose other fields are unchanged": the basis also covers what is below the node, so a
  description whose citation of a shared `Description` changes starts empty. A project with no computed field writes
  no such property and reads nothing more in an update.
- **A head's own computed fields** are kept by the same rule, and the head's basis is of the whole document: any
  change to the document starts them again.
- **A delete of an entity takes its computed edges away too**, as a merge does, and marks their heads. The plan said
  only that a candidate can be deleted. Without this a read would show a deleted entity as a candidate until the
  worker had run.
- **`set_computed` leaves a deleted or merged entity out** of what it writes (the worker's result may be a moment
  old), and refuses a target that is not an entity or is not there (`PanglossWriteError`, nothing written). It writes
  nothing to a deleted head, and says so (`False`).
- **A relation is given as a list of ids**, or of `ComputedTarget(id, seen_by=)`, which says who may see the edge
  (`everyone`, the default, is not stored; `logged_in` is). Reads do not test `seen_by` yet: that is step 3.
- **The batch form** is for a worker: several writes in one transaction, and `then(tx)` awaited in it (to complete
  its claims).
- **Two writers of one head.** `set_computed` writes to the head node (`SET head.id = head.id`) after taking its lock
  (`Dialect.before_replace`), so that it and an update cannot both go ahead: on Memgraph the second is run again, on
  Neo4j it waits. The version is read after that.
- **A computed field must be able to be empty**: a relation that is a list or optional, a value with a default or
  optional. Anything else, or `Computed()` on an embedded object or an annotated value, is a `PanglossModelError`.
- **A computed relation is to entities.** The document read follows forward edges to entities only, so one to a
  document would not be read: `set_computed` refuses it.
- **Marking a field `Computed()` is no migration** (`computed` is not in the snapshot's data).
- **The merge's own queries** (what refers to the absorbed entity, the counts of a preview, stray references) test
  `asserted` always: they are of one entity's edges, and are made when the module is loaded, before the models are
  known.

Tests: `pangloss-models/tests/test_computed_fields.py` (31), the conformance suite's `test_computed.py` (36, on both
backends), one in `pangloss-interface/tests/test_interface_meta.py`.

Not measured yet: what `set_computed` costs (the plan's "writing candidate edges"), and the one read more in an
update of a document whose classes have computed fields.

### Step 2: `SearchPattern`, and a search that leaves wrappers out ✅ (2026-11-19)

| What | Where |
|---|---|
| `Match.exclude_wrappers`, checked (`check_excluded`) and compiled (`Compiler.path_allowed`, `node_allowed`), on both backends, through the API and the SDK | `pangloss_models.search`, `pangloss_cypher.search_query`, Neo4j's `search.py`; [structured-search.md](structured-search.md), "A search that leaves wrappers out" |
| `conditions_of(checked)`: every condition of a checked search, at any depth | `pangloss_models.search` |
| `operations.survivors_of(ids)`: the survivor of each id that is a merged entity | `pangloss_cypher.read_functions` |
| The package `pangloss-criteria`, with `SearchPattern` and its codec (`format: "search-pattern"`, stored as JSON text with its keys in order) | `pangloss_criteria.pattern` |
| `check_stored(pattern, allowed, exclude_wrappers)`: the check of a pattern that is to be stored | the same |
| `ids_named`, `with_ids`, `resolve_merged` | the same |

**How the code differs from the plan, or says more than it:**

- **A stored pattern is `{"type", "where"}` and nothing else.** `order_by`, `exclude_wrappers` and a page are of a
  search that is run, and are refused in one that is kept (the evaluation says which wrappers are left out).
- **In Python it takes a `Model.Where`, a `Match`, the JSON, or its own text.** With the typed search as built,
  what refers to an entity is written `IncomingFrom(where=HoldsOffice.Where(...), field="holder")`, not the
  `Incoming(field=, from_=)` of the example at the top.
- **The root type** must be one of the classes allowed or a class below one. A class above them (an abstract
  `Agent` where a `Person` is described) is refused: it would find what cannot be put in that place.
- **Refused in a stored pattern**, each with the path of the key and why: `$same_as`, `$var`, `$is`, and for now
  `$derived` (step 13) and `$document` (step 12). An id that is no UUID is refused with its path too.
- **`exclude_wrappers` also covers the classes below a wrapper**, `$mentions` and `$somewhere`, and `exists`. The
  plan named only where the compiler handles wrapper paths.
- **Handing the option to search extensions** is `compiler.excluded`. No extension reads it yet (step 13 does), and
  `search.head_conditions` is step 6.
- **`resolve_merged` asks the backend** (`survivors_of`), and gives the pattern as it is on a storage that has no
  such operation (the SDK, where nothing is evaluated).

Tests: `pangloss-criteria/tests/test_criteria_pattern.py` (33), `tests/live/test_criteria_pattern_live.py` (5, both
backends), seven more in the conformance suite's `test_search_wrappers_live.py`, five in
`pangloss-models/tests/test_search_match.py`, one each of the API route and the SDK's request.

### Step 3: the class, the mark on save, and a first worker ✅ (2026-11-19)

| What | Where |
|---|---|
| `MatchesCriteria[T]`, with its migration (`0001_initial`: the class, and its label index) and stub | `pangloss_criteria.models` |
| Which heads can hold a description, and the mark (`hooks.pending_work`, kind `criteria`) | `pangloss_criteria.holders` |
| Evaluating criteria in full, under the five rules | `pangloss_criteria.evaluate` |
| The worker; `run_pending()`, `settled(head_id, timeout)`, `pending_status()` | `pangloss_criteria.worker` |
| The worker as a background task of the server (`CRITERIA_WORKER_IN_SERVER`); `pangloss criteria status`, `worker` | `api.py`, `cli.py` |
| `operations.search_ids(cls, pattern, *, limit, see_unpublished, without, among)` | `pangloss_cypher.read_functions`, `search_query.build_search_ids_query` |
| `fragments.edge_visible(edge)`, and `seen(edge)`, which is nothing unless some model has a computed relation | the document read, what refers to an entity, what wrappers hold, the search compilers (both backends), the facets of a list |
| `@read_validator`: what a class says of a read, run on the data its `View` is made from | `pangloss_models.write_checks` |
| `classes_stood_for(model, "T")`: what a generic's type variable stands for in the use a generated model was made for | `pangloss_models.initialise_models.builder` |

**How the code differs from the plan, or says more than it:**

- **The package needs a backend that runs Cypher** (`requires = {"cypher"}`), and depends on `pangloss-cypher`. The
  plan said it would require nothing. Writing goes through `set_computed` and searching through `search_ids`, but
  the worker claims from the kit's queue and reads the descriptions of the heads it claims with three queries of its
  own, through `pangloss_core.backend`, as derived's worker does.
- **Not yet in the class:** `same_as` (step 9), `description` (step 11), `DerivedMeta` (step 6), the interface's
  cards (step 8). So for now a description must have `criteria`. `anchors`, `reach` and `shape` are declared and
  empty until step 7; `criteria_hash`, `names` and `depends_on` are filled.
- **`candidate_count_everyone` is `Computed()` and a `DBField`**: stored, and in no model a client reads. A view has
  `candidate_count` only, which a `@read_validator` of the class makes the reader's own. That decorator is new in
  the core (the plan did not say how a view would give one count).
- **A validator of what is written that refuses is now a 422.** A `ValueError` raised by a `@create_validator` or
  `@update_validator` reached the API as a 500. `write_functions.to_db_model` makes it a `PanglossWriteRefused`
  with the path of the part it is about (`["body", "carriedOutBy", 0]`), for every class, not only this one. In
  Python `save()` raises that, where it raised pydantic's `ValidationError`.
- **A mark of a head that is claimed takes the claim off it** (`pending.mark`). A description whose result was
  refused because its document was saved meanwhile was pending again, but still under the old claim, and so waited
  for the lease to run out (30 s). This holds for derived's queue too.
- **Evaluation asks for ids** (`search_ids`): the count, and the first by label with id, type and label, as rows.
  Rule 2 is `without=` in the query, so the counts leave out what the document names. The two results are two
  searches, one as each reader.
- **A pattern's keys are kept in order** (`SearchPattern`), so that what is worked out of it (`names`, the hash) is
  the same before and after it is read back from the database. Without this an unchanged description lost its
  candidates on its first update: its basis had changed.
- **Which classes are marked:** those that can hold a description, through nested documents, wrappers and embedded
  objects, not through a citation. The classes the criteria can reach are step 5.
- **Only the descriptions inside a written head are evaluated**, each in full. A deleted head is not evaluated; it
  is when it is brought back.
- **Broken:** criteria that no longer pass the check are given `broken` (the reason) and keep their candidates.
- **The plan's Memgraph trap again:** a list of maps made by a comprehension over collected nodes gave the first
  node for each of them. `search_ids` returns rows.

**Measured: `edge_visible`** (2026-11-19, the scratch Memgraph on :7690, 1,026,342 nodes, the demo's models; medians
of 5 to 9 runs after one to warm up; `pangloss-demo/edge_visible_benchmark.py`). Each read with the test in its
query, against the query as it was:

| | Logged in | Not logged in |
|---|---|---|
| 50 factoids read | 87.2 → 86.2 ms | 71.3 → 75.8 ms |
| A person with 6,234 edges read | 380 → 452 ms (+19%) | 12.4 → 14.9 ms (+20%) |
| 25 people read | 67.5 → 68.4 ms | 109 → 99 ms |
| Activities carried out by one person | 7.1 → 7.3 ms | 7.9 → 7.7 ms |
| Factoids that mention one person | 484 → 489 ms | 21.6 → 21.5 ms |
| People referred to by an activity of one person | 207 → 214 ms | 210 → 253 ms |
| Activities that anyone carries out | 7.6 → 8.4 ms | 7.7 → 7.8 ms |

Most of it is within what the runs vary by. It costs something only where one entity's thousands of edges are each
tested (a fifth more). **Kept**, and applied only when some model has a computed relation, so a project without
descriptions has the queries it had. That database has no computed edges: this is the cost of the test, not of
candidates.

Tests: `pangloss-criteria/tests/test_criteria_models.py` (18), `tests/live/test_criteria_worker_live.py` (23) and
`test_criteria_api_live.py` (3), on both backends; the conformance suite's `test_search_ids_live.py` (6);
`pangloss-models/tests/test_read_validator.py` (7).

Not measured: the mark in a save, a batch of the worker, and the delay from a save to the candidates.

### Step 4: generic stand-ins, `CriteriaMeta` and `NoCriteria()` ✅ (2026-11-19)

| What | Where |
|---|---|
| A `hooks.StandIn` may name a generic wrapper with one type variable: the relation takes its use with the entity classes it stands for | `pangloss_models.hooks`; `stand_in_options`, `generic_stand_in_use`, `computed_only_type_vars` in `initialise_field_definitions.py` |
| A use of a generic first made while the fields are analysed is given what the others have had (rebuilt, its fields defined, in the order of the models) | `ModelRegistry._initialise_models` |
| `CriteriaMeta(allowed=True)` (the slot `_criteria_meta`), `NoCriteria()`, and the check that the app is installed | `pangloss_criteria.meta`, exported from the root |
| No template of a derived document writes a stand-in or a wrapper with a computed relation | `pangloss_derived.templates.left_to_people` |
| The demo: `CriteriaMeta(allowed=True)` on `Person`, `pangloss_criteria` installed, migration `0023_describable_person`, stubs | `pangloss-demo` |

**How the code differs from the plan, or says more than it:**

- **The use is made of the topmost classes that allow it**, by name: a relation to `Agent` takes
  `MatchesCriteria[Group | Person]`, and one to `Person` (with a subclass `Monk`) takes `MatchesCriteria[Person]`,
  the same class wherever the same classes meet. Its parameter then stands for every class below them, as the
  parameter of a use that is written out does.
- **A subclass that says `allowed=False`** is not described where a relation takes it alone. Where the relation
  takes its parent, a description of the parent still finds it: a search for a person finds a saint.
- **Nothing stands in inside a stand-in.** What a generic stand-in holds takes no stand-in at all (a description of
  a description would never end), and neither does what a type variable stands for that only computed relations are
  of. So the candidates of a `MatchesCriteria[Person]` are no longer offered an `Unreconciled`: in step 3 its `View`
  had that class among the types of `target`, though nothing could put one there.
- **A use that the annotation writes out is the only one of the field**: `list[Agent | MatchesCriteria[Person]]`
  takes a description of a person, and none of a group, though `Group` allows it.
- **There is no `standsInFor` and no `check`** for a generic stand-in. Its option is the reified relation's, as the
  export and a migration have it for one written out (`reifiedRelation:MatchesCriteria[T=entity:Person]`), and the
  class's own validator checks the criteria against what its parameter stands for (step 3).
- **Allowing descriptions is a migration** of every field that takes the class (`AlterRelationTarget`, safe:
  nothing in the database changes). The demo's is 18 changes.
- **In a template, the rule is general**: derived leaves out any stand-in (`Unreconciled` too, which a template
  could name before) and any wrapper with a computed relation, offered by a hook or written in the annotation. No
  `Template` class is made for one, and a rule that gives one all the same is refused as anything a field does not
  take. That a *rule's body* may not read through a description without `allow=` is step 6.
- **A stub named an incoming class with brackets** (`Person._SameEntity[Person]_target_reverse_incoming`), which is
  no name: a description inside the library's `SameEntity[Person]` was the first wrapper read back through a use of
  a generic. Fixed in `typestubs.incoming_classes`.
- **`pangloss_criteria.models` imported `pangloss_users` when loaded**, which a client of the SDK does not have. It
  is imported where the reader's count is chosen, which only a server does.

**Calls of the author in this step, to confirm:**

1. **The demo's `SamePerson.people` says `NoCriteria()`**: a claim of identity is between two people who are named.
   The library's `SameEntity[Person]` does take a description among its two (its `target` is `list[T]`, and the
   parameter takes what a person's place takes), as it takes an `Unreconciled` today. Whether a claim of identity
   should refuse stand-ins in general is open: "This is…" (Q9) is the planned way to say who a description is.
2. **`Naming.named` and `Gendering.gendered` take a description** ("the secretary was called Hans"). They are also
   the fields of `Person`'s companion, which is only ever filled with the new person.

Tests: `pangloss-models/tests/test_stand_ins.py` (10 more: the generic stand-in, and the stub's name),
`pangloss-criteria/tests/test_criteria_meta.py` (11), `tests/live/test_criteria_meta_live.py` (3, on both backends),
two in `pangloss-derived/tests/test_derived_documents.py`.

Not built: anything of the interface. A form of the demo now lists "MatchesCriteria" among what a person's place
takes, with the generic card of a reified relation, which has no editor for the criteria (step 8).

