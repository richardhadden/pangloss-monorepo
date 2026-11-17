# Matches criteria: someone described, not identified ⏳

**A plan, written 2026-11-17. Nothing is built.** Every question at the end was answered by the user on 2026-11-17
(see [Decisions](#decisions)); where an answer differs from what the plan first recommended, the plan has been
changed to follow it. It takes up [notes/descriptions-and-assertions.md](../notes/descriptions-and-assertions.md),
the record of a discussion of 2026-10-21/22, and follows the user's request of 2026-11-17 in its main
departure from that record: the description is **part of the document that mentions it**, not an entity of its own.

**Reviewed against the code, 2026-11-17:** see [Review](#review-2026-11-17-against-the-code). It found bad
interactions with merges, deletion, visibility and derived rules, and holes in the argument for exactness. What was
plainly a mistake has been corrected in place (each such place says "review"). What needed a decision was asked as
[Q23 to Q28](#questions), and **the user answered all six on 2026-11-17**: the recommendation each time, and for
Q28 `$derived` allowed in criteria, in [a step of its own](#derived-in-the-criteria-q28).

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

- A new generic class, **`MatchesCriteria[T]`**, a reified relation (`ReifiedRelation[T]`), shown as "Matches
  criteria". It holds the **criteria** (a structured-search pattern, the same JSON as `POST /api/search`), an
  optional **wording** (what the source says), and a **`target`** list that the server fills in: the candidates.
- A relation that takes a `Person` also takes a `MatchesCriteria[Person]`, offered in the same way as `Unreconciled`
  (a setting on the entity class, through the core's `stand_ins` hook, made general enough for a generic reified
  relation). See [Q1](#questions).
- **A save only marks** the description as pending (Q22). **In the background**, a worker runs the criteria, and
  runs them again when a write could change their result, through the queue of pending work that
  `pangloss-derived` already uses (`hooks.pending_work`, `pangloss_cypher.pending`).
- The candidates are **computed, not asserted**. They are not part of a version: no `PGUpdate`, no history entry and
  no new `meta.version` when they change. This needs one general hook in the core: a relation field marked
  **`Computed()`**.
- Because it is a reified relation, most of the interface comes from what is already there: a head bar and the
  target chips in a view, an entry on each candidate's page through the wrapper, "Through" in the search form, and
  `DerivedMeta`. The interface module adds a closed card with a **short summary of the criteria**, and a **dialog
  with the search form**. The dialog runs the criteria as they are edited and shows up to 5 candidates, or "N
  candidates found".
- A new app, **`pangloss-criteria`**, with the class, the worker, the routes, a command and the interface module.
  Two general additions go in the core: `Computed()` and stand-ins that are generic.

## What it looks like

```python
from pangloss_criteria import CriteriaMeta

class Person(Entity):
    _criteria_meta = CriteriaMeta(allowed=True)      # every relation that takes a Person takes a description too


class Activity(Statement):
    carried_out_by: list[InRole[Agent]]               # unchanged
```

Written from Python (or in a batch upload: the payload has the same shape):

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

JSON (as stored and as the API reads it):

```json
{"type": "MatchesCriteria",
 "wording": "N. N., secretarius Maximiliani",
 "criteria": {"type": "Person", "$incoming": [{"field": "holder",
              "from": {"type": "HoldsOffice", "where": {"office": {"is": "…"}, "employer": {"is": "…"}}}}]},
 "target": [{"type": "Person", "id": "…", "label": "Johann Waldauf"}, {"type": "Person", "id": "…", "label": "…"}],
 "candidateCount": 3,
 "evaluatedWhen": "2026-11-17T10:12:00Z"}
```

`target`, `candidateCount` and `evaluatedWhen` are read-only. They may be sent back in an `Update` unchanged (as
`DBField`s may), and they are ignored there.

## Reusing the reified relation: why it fits

A `MatchesCriteria[T]` is something between a relation and its target, with fields of its own, and with a
`target: list[T]`. That is what a reified relation is. Most of what the feature needs follows from that:

| Needed | Already there, for a reified relation |
|---|---|
| Stored in the document, written and read with it | Yes: a node below the head, `head_node_id` |
| Linked to every candidate | `target: list[T]` is an edge pair to each one |
| Read with the document | `build_fetch_document_query` follows forward edges to entities, so the candidates come back as `target` |
| Each candidate's page lists the documents it may be in | `read_incoming` through wrappers: the activity is listed under `carried_out_by_reverse` with the chain of wrappers |
| Shown as a head bar with chips | The interface's reified-relation card, which `InterfaceMeta(view_card=…)` can replace |
| A search can pass through it or not | The search form's "Through" pills (`throughChoicesOf`) |
| What derived rules do with it | `DerivedMeta(derivation="block" \| "qualify" \| "transparent")` |
| Nested inside other wrappers | `InRole[Agent \| MatchesCriteria[Agent]]`, as `Identification[WeightedAlternative[Person]]` is today |
| Merges | **Not as first written** (review, item 1): a merge must leave computed edges alone, not move them |

What a reified relation does **not** have, and so what is new:

1. A **target that the user does not write**: `Computed()`, below.
2. **Being offered in an entity's place without being written in the annotation**: stand-ins, below.
3. A field that holds **a search pattern**: a literal type with a codec.
4. **Running again when other data changes**: the worker.

The other way would be a document stand-in (as `Unreconciled` is), with the candidates kept apart as derived facts
are (`PGDerived`-like nodes and an `_criteria` extra in the API). It keeps the document's tree free of computed
edges, but the incoming lists, the search form, the derived rules and the display would each need their own code.
This plan recommends the reified relation ([Q3](#questions)).

## The model

```python
class MatchesCriteria[T](ReifiedRelation[T]):
    """Someone or something the source describes but does not name: whoever fits the criteria"""

    _meta = ReifiedRelation.Meta(label_index=True)        # the worker reads all of them by label
    _derived_meta = DerivedMeta(derivation="qualify")     # Q5: derived, with "MatchesCriteria" in the context
    locals().update(interface_meta())                     # view_card / edit_card of the module

    wording: str | None = None
    """What the source says ("N. N., Maximilian's secretary")"""
    criteria: SearchPattern | None = None
    """A pattern of structured search whose root is one of the classes T allows"""
    same_as: UUID | None = None
    """Another description of this document, of which this is the same one (Q17): then no criteria of its own"""
    description: Cites[Description] | None = None
    """A shared description (Q18), to which `criteria` adds conditions"""
    # (a write check: `same_as` alone, or at least one of `criteria` and `description`)

    target: Annotated[list[T], Computed()] = []
    candidate_count: Annotated[int, Computed()] = 0       # all of them, though only MAX are linked (Q7)
    candidate_count_everyone: Annotated[int, Computed()] = 0   # of what everyone sees (Q25); a view gives one count
    evaluated_when: Annotated[datetime | None, Computed()] = None

    # worked out on the server, for the worker
    criteria_hash: Annotated[str | None, DBField] = None  # identical criteria are evaluated once
    depends_on: Annotated[list[str], DBField] = []        # the class names the pattern touches
    names: Annotated[list[str], DBField] = []             # ids of every entity the pattern names (for `check`)
    anchors: Annotated[list[str], DBField] = []           # those of `names` every match must reach (step 4)
    reach: Annotated[str | None, DBField] = None          # "local" | "far" (step 4)
    shape: Annotated[str | None, DBField] = None          # the pattern without its ids and values (step 4)
```

- **`SearchPattern`** is a literal type that `pangloss-criteria` adds to the codec registry
  (`pangloss_models.literals`). It is stored as JSON text, since Neo4j cannot hold nested maps. It is checked by
  `check_match` against the models in a `@create_validator`/`@update_validator`: a field that does not exist is a
  422 that names the path in the pattern. The root type must be one the relation allows. The extension keys
  `$same_as` is refused in a stored pattern (review, item 8), and `$derived` is refused until
  [its step](#derived-in-the-criteria-q28) is built (Q28). In Python it takes a
  `Model.Where` as well as the JSON. It is exported with `format: "search-pattern"`, so the interface knows it.
- **No label.** A reified relation has none. Its summary is made from `wording` and the criteria (below).
- **The ids it names** are resolved to their survivors **when it is evaluated**. The structured search does not do
  this today (`{"is": id}` of a merged entity matches nothing), so evaluation rewrites the pattern first. The stored
  pattern is not rewritten: that would be a change of the document outside a save.

## The core: two general hooks

### `Computed()`: a relation or literal the server keeps up to date

This is a marker in `Annotated` (`pangloss_models.markers`), and it applies to any model, not only this one. A
computed field:

- is in `View`, `HeadView` and `ReferenceView`, and in the export (`computed: true`, so the form shows it and does not
  edit it);
- is not in `Create` or `Update`. A value sent back from a read is taken out before the check, as a `DBField`'s is;
- is filled on the server by the package that owns it: by a `@before_create`/`@before_update` in a save, and by
  **`operations.set_computed(node_id, values, based_on_version)`** between saves. That is a new operation of the kit
  (`pangloss_cypher`), so the add-on needs no Cypher of its own. It writes the edges and properties of the node, in
  one transaction, only if the head is still at `based_on_version`. Otherwise it changes nothing and says so, and the
  worker puts the head back in the queue;
- makes **no `PGUpdate`, no new version and no history entry**. It sends one write event of a new kind, `computed`,
  which history ignores and the interface's live feeds can use to refresh an open page;
- is left out of history's diffs and comparisons, and of a restore (a restored version is evaluated again after it is saved);
- is followed by reads like any other relation, so the incoming lists of a candidate see it.

Because of this, an update of the document is safe. The update deletes the subtree and writes it again, the save
marks the head for the worker (Q22), and any background result based on the old version is refused by its version
check. As first written the candidates went with the old node, so that every save emptied them until the worker
had run. Instead, **an update carries computed values over** (Q27): for a node whose id is in the new tree and
whose other fields are unchanged, the computed edges and values of the old tree are read before it is deleted and
written with the new one. A node that changed starts empty. The head is marked either way.

Two rules the first version of this section lacked (review, items 1, 2 and 6):

- **A computed relation is no reference.** It does not keep its target from being deleted, is not listed by
  `/deletable`, does not count for `Usage`, and a merge neither moves nor records it.
- **A computed relation takes no stand-ins.** `stand_in_options` leaves a `Computed()` field out. Without this,
  `MatchesCriteria[Person].target` would itself be offered a `MatchesCriteria[Person]` and an `Unreconciled`.

### Stand-ins that are generic

`hooks.StandIn` names a **document** class today, and offers it where an entity of the classes it stands in for goes
(`RelationToDocument.stands_in_for`). It is extended so a stand-in may be a **generic class**, given the entity
classes of the relation as its parameter: a relation to `Agent` (Person or Group, each with
`CriteriaMeta(allowed=True)`) gets `MatchesCriteria[Person | Group]`. The option is made at `initialise()` as the
generic uses that are written out are, with its own generated models. A marker opts a field out, as
`NoUnreconciled()` does (`NoCriteria()`). A `ViaEdge[Person, Certainty]` takes it with the same edge properties, so
"perhaps (60%) the secretary" can be said.

If [Q1](#questions) is answered "in the annotation", this hook is not needed: `Person | MatchesCriteria[Person]` works
today.

## Evaluating

### What is searched

The criteria are a structured search with the root type it names, and with these rules applied on top:

1. **Not through other descriptions.** A path of the search never passes through a `MatchesCriteria`. If it could,
   one description's result would depend on another's candidates, and two descriptions could keep changing each
   other's results. This becomes a general search option (`exclude_wrappers=["MatchesCriteria"]`), which the
   compiler applies where it already handles wrappers (`Dialect.through_wrappers`).
2. **Not what the same document already names** ([Q8](#questions)): "N. N. and Johann, both his secretaries" should
   not offer Johann for N. N.
3. **What may be seen** ([Q6](#questions)): by default, two results are stored. One is of what everyone sees
   (published documents), and one is of what a logged-in reader sees. Each candidate edge carries
   `seen_by: "everyone" | "logged_in"`, and a read keeps the edges its reader may see. `fragments.visible` judges
   nodes only, so this is a new, general part of `Computed()` (Q25): a fragment of the kit,
   `fragments.edge_visible(edge)` (`$see_unpublished OR coalesce(edge.seen_by, "everyone") = "everyone"`), applied
   where a computed relation is followed, in the document read, in `read_incoming` and in the search compiler. Two
   counts are stored (`candidate_count`, `candidate_count_everyone`), and a view gives its reader theirs. **Derived
   rules read only the edges everyone may see** (Q26), so that no derived fact shows what an unpublished document
   says. The cost of the new condition in those three queries is to be measured (step 3).
4. **A cap** ([Q7](#questions)): at most `CRITERIA_MAX_CANDIDATES` (50) edges are written, and `candidate_count` is
   the full count. More than the cap is shown as "too broad", in the dialog before saving and on the card after.

### On save: not evaluated, only marked (recommended 2026-11-17, Q22)

The first version of this plan evaluated in a `@before_create`/`@before_update`. That isn't needed, and the
recommendation now is that **a save only marks**. The head holding the description is left pending,
in the save's transaction (one kind of mark: see the review, "One kind of mark"), and the worker evaluates it a moment later. The candidates are then
**eventually consistent** from the first save, as they already were for every later change.

| | Evaluate on save | Mark on save (recommended) |
|---|---|---|
| Save time | One search per description before the transaction: 1 to 60 ms each, more for a `far` or broad one, and more again for a document with several | One `MERGE` |
| Bulk imports | Every N. N. evaluated in the upload's path | Saves stay fast. Identical criteria are evaluated once by the worker (they are grouped there) |
| Code | Two paths (save and worker) that must agree, plus a race between them (the `criteria-own` repair) | One path: the worker |
| Consistency | Already only eventual: the check runs outside the transaction, and later writes are the worker's | The same, from the first save |
| Right after the save | Candidates already there | Candidates follow, typically within the worker's delay (derived's median was 291 ms, p95 444 ms) |

**What the page shows right after a save.** The view page should not look as if the description found nothing:

- A description with `evaluated_when` unset, or older than its last write, is **pending**. The card shows
  "Finding candidates…" (a faint spinner) in place of the chips. It does not show "No candidates".
- The page listens for the `computed` event of its head on a `live()` feed, as the review panel stays up to date. When
  the event comes, the card fills in. The other way is a short poll, only while a description on the page is pending.
- Until then, the card may show **the dialog's preview** (the count, and the 5 chips, greyed and marked "preview"):
  the form still has it in hand when it saves, so the page need not wait. This is optional. It is what keeps the
  card from flashing empty and then full.
- If the worker is not running, the pending state lasts. After a few seconds the card says "Not yet evaluated: the
  background worker may be stopped", and `pangloss criteria status` shows the queue.

**For scripts:** `save()` returns with the candidates not yet there. `await pangloss_criteria.settled(head_id,
timeout=...)` waits for them, for scripts and tests that need them.

### In the background

The worker keeps every description's candidates right as other data changes. It is built on the queue that
`pangloss-derived` uses (`pangloss_cypher.pending`), and its rules are those of derived:

- **Nothing is forgotten.** The mark is part of the write's transaction, so a committed write is always followed by
  a run, even if the server stops.
- **It is exact in the end.** Once writes stop and the queue is empty, each description's candidates are what a
  fresh evaluation would give.
- **It does not loop.** Writing candidates can never change another description's result. (With `$derived` in
  criteria this rests on a second rule: [below](#derived-in-the-criteria-q28).)
- **Saves stay fast.** A save adds one `MERGE`, and a little more for an update (step 1).

#### A worked example

Three descriptions are saved: *A* "secretary of Maximilian", *B* "secretary of Sigismund", *C* "courier of
Maximilian". Someone saves a new `HoldsOffice`: Waldauf, secretary, employer Maximilian.

1. The save's transaction leaves `(:PGPending {kind: "criteria", head_id: <the HoldsOffice>})`.
2. A moment later the worker claims it, and reads the head: its labels (`HoldsOffice`, `Statement`, …) and the
   entities it refers to (Waldauf, Maximilian, the office Secretary).
3. All three descriptions depend on `HoldsOffice`. *B* needs a document that names Sigismund, and this one does not,
   so *B* is skipped. *A* and *C* stay.
4. *A* and *C* are evaluated again **from Maximilian**: the query starts at him and walks back along the pattern to
   the people it reaches. That is a full evaluation, and about a millisecond (measured, below), against 110 ms for
   one that tests every person. If there were a hundred descriptions of the same shape ("secretary of X"), they
   would be evaluated by one query. Waldauf matches *A*; nobody matches *C*.
5. *A*'s candidates gain Waldauf. One `set_computed` writes the edge, with *A*'s head still at the version read.
   *C* has not changed, so nothing is written for it.
6. The claim is completed. An open page of *A*'s document gets a `computed` event and shows Waldauf.

The steps in detail:

#### 1. Marking, in the write's transaction

- **Which writes mark.** `hooks.pending_work` gives the kind `criteria` for every class that some
  `MatchesCriteria[T]` could reach: the classes that `T`'s fields and incoming relations reach, worked out once at
  `initialise()`. In the demo that is nearly every class. A write of a class nothing reaches marks nothing.
- **What marks today.** Create, update, delete and undelete (`write_functions`), merge and unmerge (the survivor and
  the absorbed entity, `merge.py`), and typology's `move`/`merge` (`relink.py`).
- **What does not mark today, and must:** a change of review status (`pangloss_cypher.review.set_review_status`).
  Publishing a document changes what everyone sees, so it changes the result for everyone (rule 3). This is one
  `mark_written` call.
- **New: what an update took away** (needed to choose any description, step 4, and to evaluate those with no
  anchor, step 5). A mark holds only the
  head's id and a token. An update that **removes** Waldauf
  from an activity leaves no trace of him, so after the write nothing says he may no longer match. When the class
  marks `criteria`, the update therefore collects, in its transaction and **before** it deletes the old tree, the ids
  of the entities the old tree referred to. They are added to the mark as `before_refs`, joined with any already
  there, since a head may be written twice before it is claimed. This is a small, general extension of
  `hooks.pending_work`: a kind may ask for the previous references. It costs one read of the old tree's edges to
  entities: reading what a head refers to took 1.8 ms from Python, a round trip included (measured). A delete needs
  nothing of this, because a deleted head keeps its edges.
- **What never marks `criteria`:** `set_computed`. Rule 1 means no description ever searches through candidates, so
  writing them cannot change another result. This is what keeps the worker from looping. It **does** mark the
  other kinds of work for the head (`derive`): derived rules read through descriptions (Q5, `qualify`), so a change of
  candidates changes what they derive.

#### 2. Claiming

This is `pending.claim`, unchanged. Up to 200 heads are claimed under a 30-second lease. One worker runs at a time
(`PGWorkerLease`), either as a `BackgroundTask` of the server or as `pangloss criteria worker`. A write wakes it. One
worker is what makes the result exact, as it is for derived: each head is processed after its last write, reading
the data as it then is.

#### 3. Reading what was written

One query for the whole batch reads, for each claimed head, whether deleted or not:

- the labels of its nodes;
- the **seeds**: the entities its tree refers to now, plus `before_refs`, plus the head itself if it is an entity.
  Merged ids are resolved to their survivors here. The seeds are then **widened with the ids of the entities
  merged into each of them** (`PGMerge` by survivor). A description's stored `anchors` are the ids as written, so
  one that names an absorbed entity is otherwise never chosen after the merge (review). Nothing stored is rewritten,
  so undoing the merge needs no repair.

#### 4. Choosing the descriptions

When a description is saved, the server works out from its pattern how the worker should treat it:

| DBField | What it is |
|---|---|
| `depends_on` | The class labels the pattern touches |
| `anchors` | Entity ids that every match must reach: `is`/`is_any` conditions that are not inside `$not` or `$any_of`. For *A*, Maximilian. The worker evaluates from one of them (step 5) |
| `reach` | **`local`** if every condition is on the root itself, or on documents that refer to it directly (with their nested parts and which entities those name). **`far`** if the pattern goes on through a second entity to that entity's documents ("an office held under someone who was born in Vienna"), **or has a condition on a field of an entity other than the root** ("a transfer from someone whose gender is…": a write of that entity has only itself as a seed, so the roots it changes would never be tested; review) |
| `shape` | The pattern with its ids and values taken out: every "secretary of X" has one shape, and is evaluated with the others of it in one query |
| `criteria_hash` | The pattern, normalised, so that identical descriptions are evaluated once |

A description is chosen for a batch if `depends_on` shares a label with the batch, **and**:

| The description | Chosen when | Why that is enough |
|---|---|---|
| Anchored, `local` | an anchor, or one of its current candidates, is among the seeds | A match of *A* is a person with a document that refers both to them and to Maximilian. A document that names neither Maximilian nor a candidate cannot make or unmake one |
| Anchored, `far` | always | A document between the anchor and the root ("someone who witnessed for X" received a transfer) may name neither. Cheap all the same: from the anchor, and grouped by shape |
| Not anchored, `local` | always, evaluated only for the seeds (step 5) | The seeds are all the roots a write can change, with `before_refs` |
| Not anchored, `far` | always, in full | Nothing narrows it. The dialog warns of these, and `status` counts them |
| Cites a shared `Description` (Q18) | also when that `Description` is among the claimed heads | Its criteria are the shared ones plus its own. Found by the citation's `target_id` (review) |
| Inside a claimed head | always, in full | The head was saved (Q22), or its own named entities changed (Q8) |

Choosing is a scan of the descriptions: **9.4 ms for 10,000** with the anchors and candidates as lists on each node,
or **5 ms** with them as small index nodes (measured, below). The scan is enough to begin with.

#### 5. Evaluating

| The description | How | Measured (below) |
|---|---|---|
| Anchored | **From the anchor**: the query starts at the anchor and walks back along the pattern to the root, with the pattern's other conditions on the way. A full evaluation, so it needs no seeds and no `before_refs`. The descriptions of one shape are one query (`UNWIND $rows`, a row per description: its anchor and values) | 0.9 to 1.6 ms for one; 4 ms from an entity with 3,113 activities; 116 of one shape in 15 ms; 5,000 of one shape in 105 ms |
| Not anchored, `local` | Root first, as the search compiler does now, restricted to the seeds (`root.id IN $seeds`). The new candidates are the old ones, less the seeds, plus the seeds that match now | 1.7 to 2.5 ms with the seeds of one head; 8 to 11 ms with those of 200 (1,225 seeds), 28 ms for a broad pattern |
| Not anchored, `far` | A full search, as the compiler does now | 80 to 166 ms each, and more for broad patterns |
| Too broad (more than the cap) | A full count, and the first 50 by label linked. The seeds cannot say which of the unlinked many matched before | as a full search |

- **"From the anchor" is new work in the search compiler**: a second way to compile a pattern, starting at an entity
  it names and inverting the path to the root. It needs `WITH *` between its clauses, so that Memgraph starts where
  it is told (without them the same query took 35 to 119 ms, as the planner began elsewhere). The anchor chosen is
  the one with the fewest edges of the relation it is reached by.
- **Visibility.** With two result sets ([Q6](#questions)), each query runs twice, once as everyone and once as a
  logged-in reader, or once with a flag for each row if that measures cheaper.
- **Identical criteria** (`criteria_hash`) are evaluated once and written to each description that has them.

#### 6. Writing

- **Only what changed** is written, through `operations.set_computed(node_id, values, based_on_version)`, in
  transactions of up to 500, as derived writes justifications.
- **A head that changed in the meantime.** If a description's head is no longer at the version read, nothing is
  written for it, and nothing more need be done. The save that changed it marked it in its own transaction (Q22),
  after this batch was claimed, so a later run evaluates its descriptions in full, reading the data as it then is.
  (Before Q22 a second kind of mark, `criteria-own`, repaired this. See review, "One kind of mark".)
- **Completing the claims** (`pending.complete`) happens in the last transaction. A head marked again while it was
  worked on has a new token, so it stays pending and is done again.
- **Failures.** On a transient error or a timeout, the batch is halved and the worker backs off. A description whose
  pattern no longer passes `check_match` (the models changed) is set to broken, so it is not retried forever.

#### 7. Rebuilding and other commands

| Command | Does |
|---|---|
| `pangloss criteria status` | What is pending and claimed, the oldest mark, how many descriptions are `far` or too broad, and how many are broken |
| `pangloss criteria explain <id>` | The kind (`local`/`far`), the anchors, what writes trigger it, and the queries |
| `pangloss criteria rebuild [--type Person]` | Every description evaluated in full. Run after a bulk load (which marks nothing), after a migration that touches a class the patterns name, or after the cap is changed |
| `pangloss criteria check` | Patterns that no longer pass `check_match`, or that name a deleted entity |
| `pangloss criteria worker` | The worker in its own process (`CRITERIA_WORKER_IN_SERVER = False`) |

#### Why it is exact

Take a description *D* and a person *P* whose match changed because of a write *W*:

- If *D* is anchored and `local`, *W*'s head names one of its anchors, or *P* (then a current candidate, if *W*
  unmade the match). *D* is chosen, and evaluated in full from the anchor.
- If *D* is anchored and `far`, it is chosen whenever a class it depends on is written, and evaluated in full.
- If *D* has no anchor and is `local`, *W*'s head refers (or referred) to *P*, so *P* is a seed of *W*'s mark.
- The run that processes *W* reads the data after *W* committed, and after any later write to the same head, since
  a head written again is done again.
- If *D* has no anchor and is `far`, it is evaluated in full whenever a class it depends on is written.
- A run whose write is refused by the version check puts *D*'s head back in the queue.

So when the queue is empty, every description has been evaluated after the last write that could change it. The
test of this is a churn test, as derived's is: several writers create, update, delete, merge and publish while the
worker runs. Then `rebuild` must find nothing to change, on both backends.

#### Measured, 2026-11-17, before building

On the identity scratch Memgraph (3.14.0, :7690): **792,907 nodes**, the bulk load of 2026-11-13 (60,000 people,
5,000 sources, 30,000 factoids of 2 or 3 statements: 82,355 activities, 22,307 transfers) and the leftovers of the
measuring then (some people with 3,000 references). Docker on a laptop (8 CPUs given to it), one process, through the
models' connection, so every time includes a round trip from Python (about 1 to 1.5 ms). Medians of 7 runs after
one to warm up (and to cache the plan). Nothing is built, so these are **prototypes**: patterns compiled by today's
search compiler, that compiler's query with its first `MATCH` restricted to the seeds by hand, and hand-written
Cypher for evaluating from the anchor. The script is `pangloss-demo/criteria_benchmark.py`, to be run from a copy
of the demo whose settings point at a scratch database (its header says how). The scratch database was left as it
was and stopped.

The patterns, all of people (`Person`):

| | Pattern | Found |
|---|---|---|
| P1 | received a transfer from X (`$incoming` `given_to` from a `Transfer` whose `given_by` is X) | 2 |
| P2 | witnessed an activity of X (through `InRole`) | 4 |
| P3 | P1 in a given year (the date's fuzzy bounds compared, as a document-relative condition would be) | 1 |
| P4 | carried out a battle: no anchor, broad | 15,302 |
| P5 | received a transfer from someone who witnessed an activity of X: `far` | 2 |

**Evaluating one description:**

| | Root first, every person tested (today's compiler) | Restricted to the seeds of 1 head (~11) | Restricted to the seeds of 200 heads (~1,226) | From the anchor |
|---|---|---|---|---|
| P1 | 118 ms | 2.5 ms | 10.8 ms | **0.9 ms** |
| P2 | 132 ms | 2.0 ms | 9.2 ms | **1.6 ms** (4.0 ms from the person with 3,113 activities) |
| P3 | 110 ms | 1.7 ms | 8.2 ms | **1.4 ms** |
| P4 | 81 ms | 2.5 ms | 27.6 ms | (no anchor) |
| P5 | 166 ms | 2.3 ms | 10.1 ms | (not prototyped: the same walk, two steps longer) |

Each restricted result was the full result less what is not a seed, and the anchored P1 was the compiler's full
result: the prototypes find the same as the compiler. Compiling a pattern in Python (`check_match` and
`build_search_query`) takes 0.22 ms.

**A batch:**

| What | Measured |
|---|---|
| Reading the seeds and labels of 1 factoid / of 200, in one query | 1.8 ms (6 entities) / 27 ms (1,225 entities) |
| Choosing among 1,000 / 10,000 descriptions (lists on each node; 5% far and 5% unanchored) | 4.6 ms / 9.4 ms (148 / 1,349 chosen) |
| The same with index nodes for anchors and candidates | 4.1 ms / 5.0 ms (and 1.6 / 3.3 ms for the far and unanchored ones, read by label) |
| 200 written factoids against 5,000 descriptions "received a transfer from X": anchored on an entity the batch names | 116 of them |
| Those 116, compiled and evaluated in full, root first | about 12.8 s (2.2 s for 20) |
| Those 116, compiled and restricted to the seeds, one query each | 974 ms |
| Those 116, from the anchor, one query each | 86 ms |
| **Those 116, from the anchor, one query for the shape** | **15 ms** |
| All 5,000, from the anchor, one query (a rebuild of the shape) | 105 ms, 5,953 candidates |

**What it changed in the plan:**

1. **Evaluate from the anchor.** It is a full evaluation (exact, with no seeds and no `before_refs`), and the
   cheapest: 1 ms, against 110 to 166 ms for testing every person and 8 to 11 ms for testing a batch's seeds. A
   hub costs little (4 ms from 3,113 activities). This is new work in the search compiler, which today always starts
   at the root (step 5).
2. **Group by shape from the start**, not as a later step: 116 descriptions in one query took 15 ms, against 86 ms
   one by one. The text of the query stays the same, so its plan is kept.
3. **Seeds remain for descriptions with no anchor**, and they need `before_refs`. Restricted to a batch's seeds,
   one costs 8 to 28 ms, so a few hundred of them would make a batch take seconds.
4. **Descriptions that are neither anchored nor `local` are the expensive case**: 80 to 166 ms each, on every write
   of a class they depend on. The dialog should say so, and `status` count them. With anchored descriptions only,
   a batch of 200 heads is about 27 (seeds) + 10 (choosing) + 15 (evaluating) ms, plus the writes. That is several
   thousand heads a second before writing, against 900 for derived; it was not measured end to end.
5. **`WITH *` between clauses** of the anchored query is necessary. Without it, Memgraph planned the same walk from
   elsewhere: 35 to 119 ms.

**Not measured yet:** the mark itself in a save (derived's was 0.1 to 0.9 ms), `before_refs` inside an update's
transaction, writing candidate edges, the delay from a save to the candidates on the page, saves while the worker
runs, wrappers on the anchored path (the compiler handles semantic spaces and reified relations there, and the
prototype did not), two result sets for visibility, and **Neo4j**. These need the code.

### Derived in the criteria (Q28)

"Someone of the Medici household" may be a derived fact (`$derived`: the person has a fact of a derived class,
fitting a filter). As it stands it cannot be in criteria: with `qualify` (Q5), candidates make derived facts, a
pattern with `$derived` reads them back, and one description's candidates would depend on another's. It can be
allowed with three rules, each general:

1. **Criteria do not see facts that rest on a description.** This is rule 1 of "What is searched" once more. A
   justification already records the wrappers it passed through (`PGJustification.context_labels`, where `qualify`
   puts "MatchesCriteria"). Evaluated with `exclude_wrappers=["MatchesCriteria"]`, `$derived` counts a fact only if
   one of its justifications has none of the excluded labels. The search compiler hands the option to an
   extension's `cypher` (it is given the compiler), and `pangloss-derived` adds the condition inside the
   comprehension of `derived_visible` that finds the justifications. So no candidate ever feeds criteria, and the
   worker still cannot loop. An ordinary search is unchanged.
2. **A change of facts marks.** When derived's worker writes or withdraws facts, it marks, in that transaction, the
   entities those facts relate for every other kind of work their class asks for (`hooks.pending_kinds`, less its
   own). `pangloss-derived` names no other package, and the criteria worker finds those entities as claimed heads,
   and so as seeds. Marks for facts that only gained or lost a justification through a description could be left
   out. Leaving them in costs one round that finds nothing to change.
3. **How such a description is chosen.** `$derived` gives no anchor in the first version. On the root it is `local`
   (the root is a seed when its facts change), on another entity `far`, by the corrected rule of step 4.

What follows from it:

- **Two stages.** A write is followed by derived's run, then by this one. Exact "when the queues are empty" means
  both queues, and the churn test runs both workers.
- **Visibility** needs nothing new: `$derived` is compiled with `derived_visible`, so each of the two result sets
  (Q6) sees the facts its reader would.
- **A rule that is changed or switched off** changes facts without a write of a document. Derived's rebuild marks
  as in 2; `pangloss criteria rebuild` is the fallback.
- **Without `pangloss-derived`** the key does not exist, and `check_match` refuses it as it does today.
- **Not measured.** `$derived` in a search restricted to seeds, and the extra marks in derived's write (900 heads
  a second today), need numbers before this step is switched on.

`$same_as` stays refused (review, item 8).

### Conditions relative to the document (Q11: in the first version)

"N. N., Maximilian's secretary" in a factoid of 1495 means his secretary **in 1495**, not anyone who ever was. So a
value in a pattern may come from the document that holds the description, instead of being typed in:

```json
{"type": "Person", "$incoming": [{"field": "holder", "from": {"type": "HoldsOffice", "where": {
    "employer": {"is": "…maximilian…"},
    "when": {"overlaps": {"$document": {"field": "date"}}}}}}]}
```

- **`{"$document": {"field": "date", "of": "Factoid"}}`** is the value of a field of the nearest document of that
  class that holds the description (by default, the head). A path may go through embedded objects
  (`"date.earliest"`). The field may be a literal, an embedded date, or a relation to an entity, which gives ids for
  `is`/`is_any` ("employer is the person this factoid is about").
- **Dates:** `overlaps`, `within` (with `days`), `during` and `before`/`after` on a date field compare the two dates'
  bounds as `pangloss_dates.rules` does for derived rules, fuzzy by default. They are not new search operators: they
  expand to conditions on the stored bounds (`DBField`s that the search can already compare), by a function of
  `pangloss-dates` that `pangloss-criteria` calls when it resolves the pattern. In Python:
  `pangloss_dates.criteria.overlaps(document("date"))`.
- **Checked on write:** the path must exist on the class named (or on the head), with a type that fits the condition
  (a 422 naming the path otherwise). `POST /api/search` refuses `$document`, as it refuses a `$var`: it has no
  document. The preview route resolves it from the form's current values, which the dialog sends with it.
- **A document with no value there** (a factoid with no date): the condition cannot hold, so there are no candidates,
  and the card says "This document has no date: the criteria need it". The condition is never dropped, for the same
  reason as in migrations.
- **Evaluating:** `$document` values are resolved for each mention before it is hashed, so mentions with the same
  criteria but different dates are different groups. A change of the holding document's date is a write of its head,
  which marks it, so the descriptions inside it are evaluated again.
- **Shared descriptions** may hold `$document` references too, resolved against each citing document. So
  "Maximilian's secretary at the date of the document" is one shared description, with each mention having its own
  candidates. A document that cites one must have the fields it names (checked when cited).
- **Migrations:** `$document` paths are field names, rewritten by renames and broken by removals, as the rest of a
  pattern is.
- **In the dialog:** a value box of the search form has "from this document", which lists the fields of the
  documents holding the description that fit (by type). A date field gets "overlaps / within … days of / during /
  before / after *this document's date*". **The summary** says it as it reads: *holder of a HoldsOffice (employer:
  [Maximilian I], at the time of this factoid's date)*.

## The same one twice, shared descriptions, duplicates, migrations

Added 2026-11-17 after the user's second set of questions. **Decided by the user, 2026-11-17:** the
recommendations of this section stand ([Q17 to Q21](#questions), each answered (a)).

### The same unknown person in several places of one document

"N. N., Maximilian's secretary, carried the letter (statement 1) and was paid for it (statement 2)." Both places mean
one person, though nobody knows who. A second, identical description does not say that: **two descriptions with equal
criteria are not one person.** "Two of Maximilian's secretaries witnessed it" has two equal descriptions and two
people. So identity has to be said, and it cannot be inferred from equal criteria.

| Way | What it is | For | Against |
|---|---|---|---|
| **(a) "The same one as"** (recommended) | The first place holds the criteria. Every other place holds a `MatchesCriteria` with `same_as: <the id of that part>` and no criteria of its own | Uses what there is. It is one evaluation, and resolving one resolves all. Each place keeps its own candidate edges, so each field's lists on a candidate's page are right | The first place is special: removing it needs care (below) |
| (b) A list of the document's own unknowns | The head gets a hidden list of "people described here", each place points at one by a key | One node for one person, which is the cleanest identity | The package would add a field to every head class, and the node would be reached along several forward edges of one tree. The read (`build_tree`) assumes a tree, so this changes the core's read and update. Close to an "inline entity", which Pangloss rules out |
| (c) Equal criteria in one document are one person | Nothing to store | No work for the user | Wrong for "two secretaries". At most an opt-in tick box |

How (a) works:

- `same_as` is a property, not an edge, as a citation's `target_id` is. An edge between two parts of one tree would
  make the read nest one under the other. It is checked on every write: the part must exist in the same head, be a
  `MatchesCriteria`, and be a first place, never a chain. It survives updates, because nested parts keep their ids.
- **Candidates:** the worker evaluates the first place and writes the same candidate edges to every place.
  Excluding what the document already names (Q8) is done once for the whole head.
- **Removing the first place** while others point at it: the form moves the criteria to the next place, and the
  API refuses a write that leaves a `same_as` pointing at nothing (a 422 naming the field).
- **In the form:** the relation's search box offers "The one described above: *Maximilian's secretary* (statement 1)"
  for every first place already in this form, above "+ Describe instead…". Pasting a description into the same
  document asks "the same one, or another with the same criteria?".
- **On the card:** a place with `same_as` shows "the same one as in *statement 1*", with the summary and the
  candidates, and its pencil edits the first place.
- **Resolving** (Q9) puts the chosen person in every place at once.
- **Across documents** ("the same N. N. as in factoid X") is a claim about two parts of different documents. It is
  close to `SameEntity`, but for parts. Not in this plan.

### A description shared by many documents: "Maximilian's secretary"

Building the same criteria by hand in 200 documents is slow, gives 200 copies that a migration or a correction must
each reach, and makes it easy to get one slightly different. Two ways to share:

| Way | What it is | For | Against |
|---|---|---|---|
| **(a) A shared description, cited** (recommended) | A head document, `Description`, with a label ("Maximilian's secretary"), `criteria` and its own page. A mention is `MatchesCriteria(description=Cites[Description], criteria=<optional extra conditions>)`, so the mention's criteria are the shared ones plus its own | One definition, evaluated once, and fixed in one place by a migration. Its page lists its candidates and its mentions. A citation is how Pangloss already lets a document name another without containing it: a change to the shared description raises `PanglossCitedError` unless acknowledged, and each mention shows `changed_since_cited` | More to build. Editing it changes the meaning of mentions others wrote (below) |
| (b) Templates, copied | A named pattern, saved and shared (the saved searches of the list page, but in the database). "Start from: Maximilian's secretary" copies it into the mention | Simple, with no link to keep | A correction must be made in every copy, and the copies drift |

Problems with (a), and how each is met:

- **It looks like a person.** A page called "Maximilian's secretary" invites reading every mention as one man. That
  is the over-linking this feature exists to avoid. The page says so above all else: "A description used by 214
  mentions. It does not say that they are one person." It has no incoming lists of its own, only its mentions and its
  candidates. Identity is still `same_as` (above) or a later cross-document claim.
- **One person changes what many people wrote.** A shared description that is edited changes the candidates of every
  mention. Citations are built for exactly this. The edit is refused unless acknowledged, the mentions show
  "changed since cited", and history keeps both versions. Deleting it is refused while it is cited, unless an admin
  says `"removals"`. Finer permissions (who may edit a shared one) are the open item in `TODO.md`; this does not
  invent them.
- **Narrowing for one mention.** "Maximilian's secretary, *in 1495*": the mention's own criteria are added (AND) to
  the shared ones, and the summary shows both: *Maximilian's secretary* + date in 1495. Conditions relative to the
  document (Q11) fit here later.
- **Overlap with roles and offices.** If the project models offices as entities (the open question in
  `notes/modelling.md`), "holder of the office *Secretary to Maximilian*" is already a short pattern. A shared
  description is still the general tool: it can say anything a search says, offices or not.
- **Is it an entity?** No. It asserts nothing and nothing is said about it. It is a document that is cited, which
  keeps "documents contain; entities are referred to" true. It is listed under its own type and left out of search
  everything unless the project asks (`global_search`).

The two can be offered together: the dialog's "Start from" menu lists the shared descriptions, each with **Use**
(cite) and **Copy** (make the criteria its own).

### Identical criteria, evaluated once

Yes. This is cheap, and it matters most for imported data, where hundreds of mentions will have the same criteria.

- **The canonical form,** from which `criteria_hash` is made: snake_case keys, keys sorted, the members of `is_any`,
  `in` and `$all` sorted, empty conditions dropped, values in their stored form, and the root type included. Two
  patterns that mean the same but are written differently (a `$not` of `ne` against `eq`) are not found to be equal.
  That is acceptable: the result is still right, only evaluated twice.
- **Merged ids** are resolved before hashing, so the grouping is made by the worker in memory at each run.
  The stored hash, of the pattern as written, is for finding duplicates.
- **What differs between mentions with the same hash:** what their own document already names (Q8) and, with a shared
  description, their own extra conditions. So a group is evaluated once **without** the per-document exclusions, and
  each mention's result is that result less the entities its head names. That is a set difference in Python.
- **A new mention:** if another mention with the same hash has a current result (none of its heads pending), the
  worker copies the result instead of evaluating. If the copy is a moment stale, a later run corrects it, because the
  write that made it stale left a mark.
- **In the interface:** the dialog says "The same criteria are used in 12 other documents", and offers to make them
  one shared description (above), for the user to confirm. `GET /api/criteria/similar/{id}` lists them.

### Migrations that make a pattern invalid

A stored pattern names classes, fields, enum values and wrappers, so a migration can make it wrong. Pangloss already
has the machinery for this: `pangloss_history.upgrade` brings a stored version of a document forward through the
migrations since it was written, one change at a time, and reports what it cannot carry over as a `Problem`.
Patterns get the same treatment, with the pattern-walking put in one shared place (`pangloss_models.migrations.patterns`),
used both by migrations and by history (so that restoring an old version upgrades the patterns inside it too).

**When:** in `pangloss migrate`, through a new general hook for apps (an app is given each change as it is applied, in
the migration's transaction, and may rewrite its own stored data). A migration is not a user's edit, so this writes no
`PGUpdate`, as every other migration change does not.

| Change | What happens to a pattern |
|---|---|
| `RenameModel` | `type` and the classes named in `$incoming`, `$somewhere` and `$spaces` are rewritten |
| `RenameField`, `RenameRelation` | The keys of `where` on that class and its subclasses, `field` in `$incoming`, and `order_by` are rewritten |
| `RenameEnumMember` | Nothing (the value is stored, not the name) |
| `AlterEnumMemberValue` | The values in `eq`/`in` conditions are rewritten |
| `AlterLiteralType` | The values compared are converted, as history converts them (`convert_value`). One that cannot be converted makes the pattern **broken** |
| `AlterCardinality`, `AlterReverseName`, `AlterEdgeModel` (with its properties kept), `WrapRelation`, `UnwrapRelation`, `ChangeWrapper` | Nothing, or the wrapper's name in "Through" rewritten: a search already sees through wrappers |
| `RemoveField`, `RemoveRelation`, `DeleteModel`, `RemoveEnumMember`; `AlterRelationTarget` that leaves a nested type out | **Broken**. The condition is never dropped: dropping "employer is Maximilian" would widen the description to every secretary |
| A hand-written change (`RunPython`, `RunCypher`) | Unknown. Every pattern is checked again afterwards, and a migration may call `pangloss_criteria.rewrite(function)` to say what it does to patterns |

After the migration:

- every pattern is checked again with `check_match`, which is cheap;
- every description whose classes the migration touched is marked pending, since the data may have changed even if
  the pattern did not.

**A broken description:**

- is no longer evaluated;
- keeps its last candidates, marked "out of date since migration *0021*";
- is listed by `pangloss criteria check` and on a page of broken descriptions;
- opens in the dialog with the condition that failed in red, for a person to fix. Saving it again is an ordinary
  update.

Reads never fail on a broken one. With shared descriptions there is one place to fix instead of hundreds.

## The API

| Route | |
|---|---|
| `POST /api/criteria/preview` | `{criteria, document?, field?}` returns `{count, candidates: [5 ReferenceViews], tooBroad}`, under the same rules as an evaluation (so not simply `/api/search`). Open to anyone who may write |
| `GET /api/criteria/{id}/candidates?page=` | All the candidates of one description, paged (the card shows 5) |
| `GET /api/criteria?type=&q=&page=` | Descriptions, by the type they describe and their wording: for a page that lists them |
| `GET /api/criteria/similar/{id}` | Others with the same `criteria_hash` (the same description in other documents) |

The SDK gets each, as `pangloss_criteria.preview(...)` and so on, with the contract tests the SDK's rules ask for.

## The interface

A module of `pangloss-criteria` (`interface/`), with `view_card` and `edit_card` set by the class's `InterfaceMeta`,
as `Unreconciled`'s are. Every string is a `t()` slot, in English, German and French.

### In a form

- **The relation's search box** offers "+ Describe instead…" under the results (as the buttons of reified relations
  are, where `default_reified_type` puts them), and the type menu of the field lists "Matches criteria".
- That opens a **dialog** (the dialog pattern of `ReconcilePanel` and the create-entity type dialog). It holds:
  - the **type** being described, a `TypeGrid`/`TypeMenu` of the relation's classes that allow it, skipped when there
    is one;
  - a **wording** box;
  - the **search form** of that type (`SearchPanel`'s `NodeFields`, taken out of the list page's sliding panel into a
    component both can use), with no Order by and no saved searches;
  - **the result**, run a moment after the last change ([Q16](#questions)), as the list's search is: up to 5
    `ReferenceChip`s and "N candidates found", "No candidates yet: it will update as data is added", or "Too broad:
    N found, at most 50 are linked".
  - Done / Cancel.
- **Closed**, the card is a head bar ("Matches criteria", the reified-relation tint) with the **summary** and a pencil
  that opens the dialog again, then the 5 candidates of the preview, marked as not saved yet.
- **Editing a saved one** needs the pattern turned back into the form's state. The form keeps its own richer state
  (`NodeSearch`, with the labels of the entities picked), and only the compiled `Where` is stored. So a decompiler,
  `whereToForm(match)`, is written next to `compileSearch`, and the labels of the entities named come from
  `/api/references`. A pattern the form cannot show (written in Python with something the form lacks) opens
  read-only, with the JSON and a message that says so. A round-trip test (`compileSearch ∘ whereToForm` is the
  identity on what the form makes) keeps the two in step.

### In a view

- **The card:** a head bar with "Matches criteria", the wording in quotation marks, the summary, then the candidates
  as `ReferenceChip`s (5, then "and N more", which opens the paged list), and "N candidates · updated …" in small
  text. A "too broad" one shows the count and no chips.
- **On a candidate's page**, the document is listed with the relation's other references ([Q14](#questions)),
  marked **"identified as candidate"** (not "possibly"), followed by the summary of the criteria in its short form,
  so that the reader sees by what it was matched: *carried out by · identified as candidate · Person · holder of a
  HoldsOffice (office: [Secretary], employer: [Maximilian I])*. A long summary is cut, and shown in full on hover.
- **The summary** ([Q15](#questions)), from the pattern and the translated names of the fields and types, made by
  one function used everywhere (`describeCriteria`), for example:
  *Person · holder of a HoldsOffice (office: [Secretary], employer: [Maximilian I])*. Entities are chips inside it,
  and nesting is in brackets. Past about 120 characters it is cut with "…", and the full text is shown on hover and in
  the dialog.
- **Resolving** ([Q9](#questions)): a button on the card, "This is…", shows the candidates, and choosing one puts it
  in the description's place, as reconciling an `Unreconciled` does (an update of the document). The criteria stay
  in the document's history.

## Other parts of Pangloss it touches

| Part | What changes |
|---|---|
| History | Computed fields are not in diffs, comparisons or restores; `computed` events are not recorded |
| Search | Ordinary searches see through `MatchesCriteria` by default, as through any reified relation ([Q4](#questions)): "activities carried out by Waldauf" finds those where he is a candidate. The search form's "Through" leaves them out. The evaluation of criteria itself never passes through them (`exclude_wrappers`, rule 1) |
| Derived rules | `qualify` ([Q5](#questions)): rules derive through a description, with "MatchesCriteria" in the context of the justification, so `qualifiedOnly` facts can be filtered. A change of candidates marks `derive`. Fan-out to watch: a pair rule over an activity with a description of 50 candidates makes 50 times the facts, which changes whenever the candidates do; `pangloss derive dry-run` before a rule is switched on, as always |
| Review | Not a task of review by default ([Q10](#questions)) |
| Merges | **Changed by the review (item 1, Q23):** a merge leaves computed edges out: none moved, no `PGMergeMove`, no new version of the heads, not counted for `MERGE_LIMIT`. The edges to the absorbed entity are removed and their heads marked, and the worker evaluates again, since the survivor may now fit or not. Ids in the pattern are resolved when evaluated |
| Deletion | A named entity that is deleted makes the description match nothing. The card says "names a deleted entity", and `pangloss criteria check` lists these ([Q12](#questions)). **Being a candidate does not keep an entity from being deleted** (review, item 2, Q24) |
| Label templates | A placeholder that reaches through the relation gives the description's wording (or its summary), never the candidates' labels: a label is filled on save, and the candidates change without one (review) |
| Stubs, TypeScript types, language server | `make-stubs`, the generated TS types and `pangloss check` learn `Computed()` (read-only, not in `Create`/`Update`) and the generic stand-in (review) |
| Admin | `rebuild` is also a job of `/admin` (`admin.py`): it is long-running after a bulk load (review) |
| Migrations | Patterns are rewritten through the migration, or marked broken: see [above](#migrations-that-make-a-pattern-invalid) |
| RDF | Candidates are left out of the dump by default (they are not assertions). `RDFMeta` can include them as `pangloss:candidate` |
| Bulk load | Writes the description and no candidates; `pangloss criteria rebuild` afterwards |
| Usage | A person who is only a candidate is not "referred to" for `Usage(include_only_when_referenced=…)` |

## Where the code goes

A package of its own, **`pangloss-criteria`** (Q13). It has everything an app can have: models (`MatchesCriteria`,
`Description`), a worker, routes, commands, settings, migrations and an interface module. `pangloss-library` is for
ready-made models with no machinery of their own. What other packages need is put in the core as general hooks, each
of which could have a second user:

| Where | What |
|---|---|
| `pangloss-criteria` | `MatchesCriteria`, `Description`, `CriteriaMeta`, `NoCriteria`, `SearchPattern` and its codec, the hashing and the shapes (`reach`, `anchors`), the worker, `/api/criteria/…`, `pangloss criteria …`, the migration rewrites of patterns, the interface module (dialog, cards, summary), translations. `requires` nothing: it goes through the models and the kit's operations |
| `pangloss-models` | The `Computed()` marker; generic stand-ins (`hooks.StandIn`); `before_refs` for a kind of pending work; the app hook in `migrate`; `migrations.patterns` (the walk over a stored pattern, shared with history); `exclude_wrappers` in `Match` |
| `pangloss-cypher` | `operations.set_computed` with its version check; `exclude_wrappers` in the search compiler; the mark on a change of review status; collecting `before_refs` on update. From the review: computed edges left out of `delete_node`'s references, of the merge's moves and of usage; carried over by an update (Q27); the visibility of a computed edge in the document read, `read_incoming` and the search compiler (Q25) |
| `pangloss-derived` | From the review: rules read only the candidates everyone may see (Q26). For `$derived` in criteria (Q28): the key honours `exclude_wrappers`, and the worker marks the entities whose facts change for the other kinds of work |
| `pangloss-testing` | Conformance tests of `set_computed`, computed fields in reads and updates, and `exclude_wrappers`, on both backends |
| `pangloss-history` | Computed fields left out of diffs and restores; patterns upgraded with `migrations.patterns` |
| `pangloss-sdk` | The client side of `set_computed`'s absence (a client never calls it), of the criteria routes, and of `settled()` |
| `interface-core` | The search form's fields as a component that a dialog can hold (out of `SearchPanel`); `whereToForm`; the reading of `computed` fields; a `live()` feed or poll for a pending card |

## Plan, in steps that each work alone

1. **`Computed()` in the core**: the marker, the generated models, the export, `operations.set_computed` with its
   version check, the `computed` write event, and history leaving them out. A computed relation is no reference
   (deletion, usage, merges), takes no stand-ins, and is carried over by an update (Q27). Stubs and TS types.
   Conformance tests on both backends.
2. **`SearchPattern`**, a codec and check of a stored pattern, `exclude_wrappers` in the search compiler, and
   resolving merged ids in a pattern.
3. **`pangloss-criteria`: the class, the mark on save, and a first worker that evaluates in full every description
   of a saved head** (claiming, `set_computed` with the version check), with the cap, the visibility sets and the
   same-document rule, with `fragments.edge_visible` in the read, the incoming lists and the search (Q25,
   measured on the scratch database before it is kept). Python and API tests, with the class written in the
   annotation (`Person | MatchesCriteria[Person]`), which needs no stand-in.
4. **Generic stand-ins** (Q1), `CriteriaMeta` and `NoCriteria()`. The demo gets `CriteriaMeta` on `Person` and a
   migration.
5. **Keeping up with other writes**, first by full evaluation: marking by class (with publishing, and
   `before_refs` on update), merges and deletion leaving computed edges out, derived reading only what everyone
   sees (Q26), and the churn test for exactness.
6. **Evaluation from the anchor** in the search compiler, grouped by shape (`UNWIND $rows`), with `WITH *` between
   clauses; seeded evaluation for descriptions with no anchor; `reach`, `anchors`, `shape`, `explain`, `rebuild`,
   `check`, `status`. Measured again on the scratch database, and on Neo4j.
7. **The interface**: the shared search form, the dialog, the preview, the cards, the summary, the decompiler,
   resolving. `e2e/COVERAGE.md`, the dev-mode test.
8. **`same_as`** within a document (Q17), and grouping identical criteria for evaluation.
9. **Migrations of stored patterns**: the shared upgrader with history, the app hook in `migrate`, broken
   descriptions and their page.
10. **Shared descriptions** (Q18): `Description`, cited, with extra conditions; "Start from", Use and Copy.
11. **Conditions relative to the document** (Q11): `$document`, the date conditions through `pangloss-dates`, the
    write check, the dialog's "from this document", the summary.
12. **`$derived` in the criteria** (Q28): `exclude_wrappers` handed to search extensions, the condition on
    `context_labels`, derived's marks, the churn test with both workers. Measured first.
13. The RDF and usage rules, the docs (`status.md`, a guide page), and this skill.

## Not in this plan

- **A lens** (reading under chosen authors, sources, certainty), from the discussion record.
- **Weights** for each candidate (1/k in a network export): `pangloss derive graph` could use `candidate_count`
  later.
- **Turning existing singleton people into descriptions** in bulk (the old database's N. N. people): a script or an
  admin job once the class exists.
- **A shared description as an entity** (the record's "hub"). A shared description that is a cited document is in
  the plan instead ([above](#a-description-shared-by-many-documents-maximilians-secretary)).
- **"The same N. N." across documents**: a claim that parts of two documents are one, like `SameEntity` for parts.

## Review, 2026-11-17: against the code

The plan was read against the code as it is (nothing was run). The design stands. What follows is what it did not
take care of. Each item has a recommendation. Those marked with a question were for the user
([Q23 to Q28](#questions)), who **took each recommendation** (2026-11-17), and asked for `$derived` in criteria
(item 7). The others are corrections, already made in the text above.

### Bad interactions

**1. Merges treat candidate edges as asserted ones (Q23).** `pangloss_cypher.merge` moves every forward edge to the
absorbed entity, records each as a `PGMergeMove`, gives every head touched a `PGUpdate` and a new version, and counts
those heads against `MERGE_LIMIT`. Merging a person who is a candidate of 2,000 mentions would write 2,000 versions
(against "candidates are not part of a version"), could be refused as too large, and an undo would put back edges
the worker has since replaced.
*Recommended:* a merge leaves `Computed()` relations out. It removes the computed edges to the absorbed entity,
without a record, a version or a count, and marks their heads for the worker (one `MERGE` each, in the merge's
transaction). The merge preview does not list them. An undo marks the same way. Step 5 of the merge ("what is left
on B is an error") does not count computed edges.

**2. A candidate cannot be deleted (Q24).** `REFERENCES_QUERY` of `delete_node.py` counts every reverse edge, so a
person who is only a candidate is "referred to": marked, not deleted, with the documents listed by `/deletable`.
*Recommended:* computed edges are no references, there and in `Usage` (one rule, in the core). A deleted candidate
drops out on the next evaluation (a delete marks), and reads leave a deleted entity out meanwhile, as they do now.

**3. `seen_by` on an edge has nothing to read it (Q25).** `fragments.visible` judges nodes, never edges. For Q6
(two result sets) the edge would have to be tested in the document read, in `read_incoming`, in the search compiler
(Q4: searches see through to candidates) and in derived. And `candidate_count` is one number for two results, so
a reader who is not logged in would see the count of the other.
*Recommended:* make it a general part of `Computed()`: a computed edge may carry `seen_by`, and one fragment of the
kit (`fragments.edge_visible(edge)`: `$see_unpublished OR coalesce(edge.seen_by, "everyone") = "everyone"`) is
applied at those three places of the core, where a computed relation is followed. Two counts are stored
(`candidate_count`, `candidate_count_everyone`), and the view gives the reader theirs. This must be measured: it is
a new condition in the three hottest queries. *The cheaper way* is Q6 (b) after all: published documents only, one
result, no edge test, no leak. Its cost is that a factoid in review makes nobody a candidate until it is published.

**4. Derived facts would show what unpublished documents say (Q26).** `derived_visible` shows a fact when the heads
of its evidence are visible. A fact derived through a candidate that is there only because of an unpublished
`HoldsOffice` has the published activity as its evidence, so everyone sees it.
*Recommended:* derived rules read only the candidates everyone may see. One rule, no new evidence to keep, and what
is derived from a guess rests on published data only. (The other way, the matching documents as evidence, would have
the worker keep which documents made each match: much more to store and to keep right.) With Q6 (b) this item goes
away.

**5. Every save of a document empties its candidates (Q27).** An update deletes the subtree. Since Q22 nothing fills
it again until the worker has run. Correcting a typo makes the card say "Finding candidates…", takes the row off
each candidate's page for a moment, and makes derived withdraw its facts and derive them again.
*Recommended:* an update carries the computed edges and values over, for a node whose id is in the new tree and
whose other fields are unchanged (for a description: the same criteria, `same_as` and `description`). The head is
still marked, so the result is checked. A description whose criteria changed starts empty, which is right. This is
part of `Computed()` in the core: the update reads the computed edges of the old tree before it deletes it (as it
will read `before_refs`), and writes them with the new one.

**6. Stand-ins would be offered on `target` itself.** Corrected above: a `Computed()` field takes no stand-ins.

**7. `$derived` in a pattern makes a loop (Q28).** With `qualify` (Q5), candidates make derived facts. A pattern
with `$derived` reads them back, and derived's writes mark no `criteria`. "It does not loop" would be false.
*First recommended:* refused in a stored pattern. *The user asked for a way to have it:* there is one, in
[Derived in the criteria](#derived-in-the-criteria-q28), as a later step; refused (a 422 that says why) until then.

**8. `$same_as` in a pattern is not kept exact (Q28).** It stands for a cluster, read when the pattern is compiled.
A new `SameEntity` changes the result, but its class is not in the pattern's `depends_on`, and the anchor is no
longer one id.
*Recommended:* refused in the first version. Later it can be allowed as `far`, depending on every class with an
`IdentityClaim()` field.

### Holes in "Why it is exact" (corrected above)

- **`local` was too wide.** A condition on a field of an entity other than the root makes a pattern `far` (step 4).
- **Anchors that name a merged entity** were never chosen. The seeds are widened with the entities merged into them
  (step 3).
- **A shared `Description` that is edited** now chooses the mentions that cite it (step 4).
- **`before_refs`** is needed to choose anchored descriptions too (an update that takes both the anchor and the
  candidate out of a document), not only for those with no anchor (step 1).
- **Over the cap, the count is approximate.** A write that unmakes a match that is not linked (the person is
  deleted, or a condition on the person's own fields no longer holds) does not choose the description. The card says
  "more than 50 (about N)", and `rebuild` makes the count exact. Counting exactly would mean a full search on every
  such write, which is not worth it for a description already called too broad.

### One kind of mark

`hooks.pending_work` is given only the class written. With Q22, `criteria-own` ("a head that holds a description
was saved") would be asked for by every class that can hold one, which is nearly every class, beside `criteria`: two
`MERGE`s for each save. One kind is enough. The worker already reads each claimed head, and reads with it whether
descriptions lie inside (`MatchesCriteria` nodes by `head_node_id`); those it evaluates in full. `settled(head_id)`
waits for that head's mark to be completed. Where the text above still says `criteria-own`, read it as "the
mark of a head that holds a description".

### Smaller things

- **A `Description` with `$document` conditions has no result of its own**: its page lists its mentions, and says
  "the candidates depend on each document" in place of a list.
- **A `Description` is not reviewed** (no `ReviewMeta`): it asserts nothing. Otherwise a published mention could cite
  an unpublished description, and a reader who is not logged in would see candidates of criteria they may not read.
- **Label templates, stubs, TS types, the language server, an admin job for `rebuild`**: rows added to "Other
  parts of Pangloss it touches".

### Checked, and fine

- History's snapshots are the `UpdateDB` payload, so computed fields are not in them without further work.
- Identity clusters follow only an edge from a claim straight to an entity, so candidates join no cluster.
- `Cites` is allowed on a reified relation, and `ReifiedRelation.Meta(label_index=…)` exists.
- No read is cached by version (the `ETag` is only for `If-Match`), so a computed change with no new version is seen.
- A change of review status marks no pending work today, as step 1 says.

## Decisions

The user's, 2026-11-17. Where an answer is not what the plan first recommended, it is in bold.

| Q | Answer |
|---|---|
| Q1 | A setting on the entity class (`CriteriaMeta(allowed=True)`), with `NoCriteria()` to opt a field out |
| Q2 | `MatchesCriteria`, shown as "Matches criteria" |
| Q3 | A reified relation whose `target` is computed |
| Q4 | **Ordinary searches see through to the candidates by default**, as for any wrapper; "Through" leaves them out |
| Q5 | **`qualify`**: derived rules read through descriptions, with "MatchesCriteria" in the context |
| Q6 | Two result sets: what everyone sees, what a logged-in reader sees |
| Q7 | At most 50 linked (a setting), the full count stored, "too broad" shown, saving allowed |
| Q8 | Entities the same document names are never candidates |
| Q9 | "This is…" puts the chosen entity in its place (in every `same_as` place), the criteria kept in history |
| Q10 | Not a task of review |
| Q11 | **Conditions relative to the document in the first version** (`$document`, above) |
| Q12 | The ids named are kept for the worker only; nothing on the named entity's page |
| Q13 | A new package, `pangloss-criteria` |
| Q14 | In the ordinary lists of a candidate's page, **marked "identified as candidate" (not "possibly"), with the criteria in short form** |
| Q15 | A sentence, with entity chips and brackets |
| Q16 | The dialog's preview runs a moment after each change |
| Q17 | "The same one as" (`same_as`) |
| Q18 | A shared `Description`, cited, with the mention's own extra conditions; Copy beside Use |
| Q19 | Anyone logged in may change a shared description, with the citation's acknowledgement |
| Q20 | A migration that removes what a pattern needs makes it broken; its last candidates kept, marked out of date |
| Q21 | The dialog offers to make identical criteria one shared description |
| Q22 | A save only marks; the worker evaluates; the card shows "Finding candidates…" (with the preview) until the result arrives |
| Q23 | A merge leaves computed edges out: none moved or recorded, no new versions, not counted; the worker evaluates again |
| Q24 | An entity that is only a candidate can be deleted: a candidate is no reference |
| Q25 | `seen_by` on each computed edge, tested by one fragment in the read, the incoming lists and the search; two counts; to be measured |
| Q26 | Derived rules read only the candidates everyone may see |
| Q27 | An update carries the candidates over where the description is unchanged; the worker checks afterwards |
| Q28 | `$same_as` refused. **`$derived` allowed** (the user asked for a way), by the three rules of "Derived in the criteria", in a step of its own; refused until that is built |

## Questions

Each has the first recommendation first. **Q1 to Q22 answered by the user, 2026-11-17** (see
[Decisions](#decisions)). Q23 to Q28, at the end, come from the
[review](#review-2026-11-17-against-the-code), and were answered the same day.

**Q1. How does a field come to take a description?**
- (a) **Recommended:** a setting on the entity class (`CriteriaMeta(allowed=True)`), offered on every relation to it
  automatically, with `NoCriteria()` to opt a field out. This is how `Unreconciled` works.
- (b) Written in each annotation: `Person | MatchesCriteria[Person]`. Explicit, and it works without the
  generic-stand-in hook, but it is long, and the demo has many fields.
- (c) On for every entity class.

**Q2. What is it called?**
- (a) **Recommended:** the class `MatchesCriteria`, shown as "Matches criteria".
- (b) `Described` / "Described as".
- (c) `Someone` / "Someone who…" (reads well for people, badly for places and things).
- (d) Something else.

**Q3. What is it?**
- (a) **Recommended:** a `ReifiedRelation[T]` whose `target` is computed: reads, incoming lists, search, derived and
  the display come with it.
- (b) A document stand-in, with its candidates kept apart like derived facts, so the document's tree has no computed
  edges. Each of those uses needs its own code.

**Q4. Does an ordinary search see through to the candidates?** (For example, "activities carried out by Waldauf"
when Waldauf is a candidate of one.)
- (a) **Recommended:** no by default, but "Through: Matches criteria" in the search form includes them. The
  candidate's own page lists them either way.
- (b) Yes, as for any reified relation; "Through" can leave them out.

**Q5. What do derived rules do with a description?**
- (a) **Recommended:** `block` (derive nothing from a guess).
- (b) `qualify` (derive, with "Matches criteria" in the context, which can be filtered on).

**Q6. Unpublished documents.**
- (a) **Recommended:** two results, one of what everyone sees and one of what a logged-in reader sees, chosen when
  read.
- (b) Published documents only: one result, but a factoid in review cannot make anyone a candidate.
- (c) Everything not deleted, shown to everyone: one result, but an anonymous reader learns from unpublished
  documents.

**Q7. A description that fits too many.**
- (a) **Recommended:** link at most 50 (a setting), store the full count, and say "too broad" in the dialog and on
  the card. Saving is still allowed.
- (b) The same, but refuse to save it until it is narrowed.
- (c) Link all of them, however many.

**Q8. Entities the same document already names.**
- (a) **Recommended:** never candidates.
- (b) Allowed.

**Q9. Saying "it was this one".**
- (a) **Recommended:** "This is…" on the card puts the chosen person in its place (an update), as reconciling does;
  the criteria stay in history.
- (b) The person goes in, and the criteria are kept beside them as the evidence (for example in an
  `Identification`, which would need a field for them).
- (c) No such action for now.

**Q10. Is an unresolved description a task of review?**
- (a) **Recommended:** no: it is a finished statement of what the source says.
- (b) Yes, as an `Unreconciled` is, until it is resolved.

**Q11. Criteria relative to the document holding them** ("at the date of this factoid"):
- (a) **Recommended:** later, a step of its own, with dates typed into the pattern by hand meanwhile.
- (b) In the first version.

**Q12. Entities that the criteria name** (Maximilian):
- (a) **Recommended:** kept as ids (`names`) for the worker. Nothing on Maximilian's page, and a deleted one is
  reported by `check`.
- (b) Also as computed edges, so Maximilian's page lists "named in the criteria of …", and he counts as referred to
  (protected from deletion).

**Q13. Where it lives.**
- (a) **Recommended:** a new app, `pangloss-criteria`, plus the two general hooks in the core.
- (b) In `pangloss-library`, beside `Identification`.

**Q14. On a candidate's page.**
- (a) **Recommended:** in the ordinary lists of what refers to them, with the "Matches criteria" chip on the way.
- (b) In a section of its own, "May be the one in…", apart from what documents say outright.

**Q15. The short summary of the criteria.**
- (a) **Recommended:** a sentence of field and type names, with entity chips inside it and brackets for nesting.
- (b) A row of small chips, one for each condition ("office = Secretary", "employer = Maximilian").
- (c) The wording only, with the criteria shown on hover.

**Q16. When the dialog runs the criteria.**
- (a) **Recommended:** a moment after each change, as the list's search form does.
- (b) Only when a "Find candidates" button is pressed.

**Q17 (decided: a). The same unknown person in several places of one document.**
- (a) **Recommended:** "the same one as": the other places point at the first by `same_as`.
- (b) A list of the document's own unknowns, at the head, with places pointing into it.
- (c) Equal criteria in one document count as one person (perhaps as a tick box).

**Q18 (decided: a). Sharing a description ("Maximilian's secretary").**
- (a) **Recommended:** a shared `Description` document, cited by mentions, which may add conditions of their own;
  and "Copy" beside "Use" for those who want the criteria as their own.
- (b) Templates only: copied, never linked.
- (c) Neither, for now.

**Q19 (decided: a). Who may change a shared description?**
- (a) **Recommended:** anyone logged in, with the citation's acknowledgement, until finer permissions exist.
- (b) Only its author and admins (this would be the first rule of its kind, made for this alone).

**Q20 (decided: a). A migration that removes what a pattern needs.**
- (a) **Recommended:** the description is broken. It keeps its last candidates, marked out of date, until someone
  fixes it.
- (b) The same, but its candidates are cleared.
- (c) The condition is dropped and the description re-run (it gets wider).

**Q21 (decided: a). Offering to share identical criteria.**
- (a) **Recommended:** the dialog says how many other documents use the same criteria, and offers to make them one
  shared description.
- (b) Grouped for evaluation only, with nothing shown.

**Q22. When is a new description first evaluated?**
- (a) **Recommended:** by the worker, a moment after the save; the card shows "Finding candidates…" (with the
  preview) until the result arrives on the page's live feed.
- (b) On save, before the write, as first planned.

**Q23 (decided: a). A merge of an entity that is a candidate** (review, item 1).
- (a) **Recommended:** the merge leaves computed edges out: none moved or recorded, no new version of their
  documents, not counted for `MERGE_LIMIT`. The worker evaluates again.
- (b) As for any edge (moved, recorded, a version each), with `allow_large` for the big ones.

**Q24 (decided: a). Deleting an entity that is only a candidate** (review, item 2).
- (a) **Recommended:** allowed. Being a candidate is no reference, for deletion as for `Usage`.
- (b) Marked for deletion, as an entity that is referred to is, and listed by `/deletable`.

**Q25 (decided: a). How the two result sets of Q6 are kept apart** (review, item 3).
- (a) **Recommended:** `seen_by` on each computed edge, tested by one fragment in the document read, the incoming
  lists and the search; two counts. To be measured.
- (b) Go back on Q6: published documents only, one result. Nothing to test, and items 3 and 4 go away. A factoid in
  review makes nobody a candidate until it is published.

**Q26 (decided: a). What derived rules read of the candidates** (review, item 4; not needed with Q25 (b)).
- (a) **Recommended:** only the candidates everyone may see.
- (b) All of them, with the documents that made each match kept as evidence, so `derived_visible` hides what it
  should.

**Q27 (decided: a). The candidates of a document that is saved again** (review, item 5).
- (a) **Recommended:** carried over by the update where the description is unchanged, and checked by the worker
  afterwards.
- (b) Emptied on every save, and filled again by the worker a moment later.

**Q28 (decided: `$same_as` refused; `$derived` allowed, in its own step). `$derived` and `$same_as` in the criteria** (review, items 7 and 8).
- (a) **Recommended:** both refused in the first version.
- (b) `$derived` refused; `$same_as` allowed, evaluated as `far` on every write of a class with an identity claim.
- (c) Added after the user's question: `$derived` allowed, seeing only facts that do not rest on a description,
  with derived's worker marking the entities whose facts change.
