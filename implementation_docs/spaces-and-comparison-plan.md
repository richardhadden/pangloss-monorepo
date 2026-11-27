# Semantic spaces and comparison: the build plan ⏳

Written 2026-11-24, at the user's word: **one plan** for the fields of a semantic space and for the comparison of
statements, with every feature they change. It takes the place of two plans, both kept as they were written with a
note at their head: [semantic-spaces-plan.md](semantic-spaces-plan.md) (its phases 0 to 8), and the steps of phase 12
of [the similarity build plan](similarity-build-plan.md#phase-12-pangloss-compare) (12.1 to 12.10, rewritten here as
phase 6). **Nothing here is built.** The user gave the word to start on 2026-11-25, which lifts phase 12's hold: the work
begins in a new session, from [Where the work stands](#where-the-work-stands).

The design is in [the fields of a semantic space](semantic-space-fields.md) (the four fields, the walk, similarity,
negatives that record a relation, derived edges, the manmax exercise), [the report](semantic-spaces-formalisation.md)
and [the summary](semantic-spaces-summary.md); for comparison, in [similarity-plan.md](similarity-plan.md) (stages 11
and 12) and [graph-embeddings.md](graph-embeddings.md) ("Judgements at lookup"). The numbering of phases 0 to 4 and 8
is that of the plan it replaces, so that the design pages' references to them still hold.

## Contents

- What is taken as settled
- What was found before the steps
- The review of 2026-11-25, and what it changed
- The degree of a statement's contents
- The ground of a head class (added 2026-11-26; not phase 0, whose title uses the word otherwise)
- The features this plan changes
- The order, and the order from here (2026-11-26)
- How the work is run
- Who builds each step
- Phase 0: the ground
- Phase 1: the fault in recording spaces
- Phase 2: the four fields in the core
- Phase 3: the walk
- Phase 4: the packages that read spaces
- Phase 5: the vector parts
- Phase 6: `pangloss-compare`
- Phase 7: the interface
- Phase 8: negatives that record a relation
- Phase 9: the demo, the guide, the measurements, the end
- Decisions for the user
- Calls taken
- Not in this plan
- What can go wrong
- Where the work stands

## What is taken as settled

| | Settled | By |
|---|---|---|
| The fields of a space | `veridical`, `fit`, `logical`, `unary` on `SemanticSpaceMeta`; not ChatGPT's four, and not both | The user, 2026-11-24 |
| What is asserted | A statement on its own, or nested in another with no space, is asserted | Pangloss already |
| Relations, not distances | The spaces decide the relation of two statements, never their distance: no "context" part of the vectors | [semantic-space-fields.md](semantic-space-fields.md#how-it-works-with-similarity) |
| Virtual relations | A source's "X did not meet Y" records a virtual relation when the positive was live in the structure; an empty negative (Zarglqwargl) records none | The user, agreed 2026-11-24 |
| `EventJudgement` | In `pangloss-compare` | The user's answer 1 for phase 12 |
| Comparison's scope | Verdicts at lookup, `EventJudgement`, the route; the side-by-side view, recording a judgement from it, learning from judgements. Asking people about the least sure pairs stays later | Answer 2 |
| Pairs | By rule and by vectors from the start, never through what is not reconciled: a stand-in or an unconfirmed suggestion never pairs two statements | Answer 3 |
| No list across the database | Verdicts are worked out when a statement is shown, never written | Answer 4 |
| The core knows no package | Each package reads the fields through the core | The skill |

## What was found before the steps

- **Phase 12's ten findings hold** ([similarity-build-plan.md](similarity-build-plan.md#what-was-found-before-the-steps-2026-11-24)):
  stand-ins are walked by the graph part; statements have vectors; `pangloss-learn` has `compare_calls`; meta slots
  and their checks; dates' `Bounds`; negation is the demo's; the demo's once-per and recurring classes; the planted
  world's gaps; the interface's `itemSections`, and history's side by side not exported; `Cites[T]` of a nested
  statement.
- **The fault in recording spaces, and its narrower fix**, tried and measured on the demo, read only
  ([semantic-space-fields.md](semantic-space-fields.md#derived-edges-through-spaces)): the demo's models allow one
  leaking shape, its data has none; the fix leaves all 154 of its nested nodes as they are stored.
- **The demo's derived facts**: 4 of its 34 `GaveTo` edges come from orders, one of them a "gave to" made of a
  forbidden gift.
- **Every reader of the stored lists** (`meta.semantic_spaces`, `meta.context_labels`), read on 2026-11-24 (step 0.3
  below): the table that follows. Three that do not read them: the RDF export walks the tree itself (`convert.py`);
  history leaves the lists out of its diffs (`diff.py`, `summary.py`); label templates skip them.

## The review of 2026-11-25, and what it changed

The plan was read against the design pages and the code, and the user answered. Where a step below still says
otherwise, this section is right. The trial is `/tmp/plan-review/t.py` (the algorithm of `context.py` on plain
objects; nothing stored was read).

**What was found.**

- **The walk cannot be worked out from `context_labels`.** A label's `contents` is one flat list of the documents a
  node is nested in, the node itself, and its siblings under single relations, with nothing to tell them apart (the
  interface's `contextPath` already has to take the node itself out by its id). `Not[p]` gives p `Not: [p]`;
  `Not[Service(parts=[p])]` gives `Not: [Service, p]`, and the same as `Not[p]` when `Service` has
  `use_in_semantic_space_label=False`; in `Not[Causes(cause=A, result=B)]`, A and B are in each other's list. So "a
  statement between two spaces stops it" cannot be decided, with or without the fix of the old 1.1.
- **The fault is wider than "two single relations".** One single relation that holds a space, followed by a list
  relation, leaks too: in `Order(thing=Ordered[p], witnesses=[w])`, w is recorded as inside `Ordered`.
- **The degree made the pure walk read the database** (an `Expectation`, a rule's proposal), made fastrp, derived and
  the time part read `pangloss-library`'s document with no hook for it, and made derived depend on itself (the rules
  of authority are derived rules, and "likely" is a status of derived). What derived and the vector parts keep (a
  status on each justification, weights in the vectors) goes stale when a degree or a space's field changes; derived's
  `rule_hash` and the parts' signatures do not cover that today.
- **Smaller**: `veridical` defaulting to `0` refused the design page's own `Meta(logical="not")`; nothing checked
  stored spaces against a new `unary`; `EventJudgement`'s seven verdicts against the table's fifteen relations, with
  no word of which overrides which; "after it" with undated statements (6.3); the order said 4, 5 and 6 did not
  depend on each other, while 6.2, 6.4 and 6.6 need 5.1's world; `/tmp/space-trial/` is empty; `solidjs-v2-reviewer`
  is a skill, not an agent.

**What the user decided (2026-11-25).**

| | Decided | Changes |
|---|---|---|
| R1 | **A true path is stored**, and the walk reads it. The user, who wrote `context.py`, is not happy with how it works: improvements are asked for, and proposed in phase 1 | Phase 1 rewritten; 3.1, 3.2 |
| R2 | **The degree is out of the walk**: `signature` gives the sign and the class's default; a statement's own degree is given to it by the caller, who gets it through a hook of the core, built with phase 8 | 3.1; 4.1 ("likely" and (e) wait for phase 8); 5.2 to 5.4; 8 |
| R3 | **Two axes** (the user's suggestion): below | The degree's section |
| R4 | **Stored data is mended by a migration**, so that a server with it pending does not start (D1) | 1.3 |
| R5 | **A first build, then the rest**: [the order](#the-order) | The order |
| R6 | **`veridical` defaults to `None`**: what `logical` implies (`-1` for `"not"`), else `0` | 2.1, 2.2 |
| R7 | **`EventJudgement` names its two statements** by two fields with roles, not a list of two | 6.5 |
| R8 | **One branch for phases 0 to 3**, then one for each line (confirmed) | How the work is run |
| R9 | **The degree is in the entry, and outside it as a fallback** (both: the user sees the good of each): below | 2.7 (new), 1.1, 3.1, 8 |

**Two axes (R3).** In a factoid model everything recorded is what the interpreter of the source commits to, so "the
source's commitment against the historian's inference" is not the line. The two axes are:

1. **`veridical`: what the entry says.** A property of the space classes and of where a statement sits: whether its
   contents are given as so, as not so, or as neither. It is structure, it carries the logic (the rewrites, the kind
   of relation), and it is never a matter of more or less.
2. **The degree: how far the contents count as having happened.** A judgement about one statement, with grounds, made
   by someone (a rule's proposal, a person's `Expectation`, else the class's default), that can change without the
   statement being edited. It is never worked out by the walk.

Where nobody has judged, the degree follows `veridical` (`1`: in full; `-1`: not at all; `0`: the class's default).
Each reader says which axis it follows, and **it need not be the same everywhere**: what is asserted (the RDF export's
direct triples, derived's `plain`, identity claims, the marks in the interface) follows `veridical` only; what
weighs (the actual network, the time part, comparison's strength, derived's "likely") follows the degree, each as
its own decision (D4, D9), and a project can turn each off. A denial's liveness stays a third thing, the strength of
a virtual relation, and is not the degree. **Decided** (D15, 2026-11-25): this split; the degree runs from `0` to
`1`, and its sign is the walk's lean.

**Where a statement's degree comes from (R9)**, the first that there is:

1. **The entry**: a value on the space that holds the statement, set by the person who enters it, saved and versioned
   with the document, in its history, and seen by what cites it (step 2.7). It is written into the space's entry of
   the path (1.1), so the walk reads it with no database, and a change of it is an ordinary write: nothing goes stale
   that a write does not already make due. A project that wants only this installs no rules.
2. **A person's later judgement**: an `Expectation` citing the statement (8.1).
3. **A rule's proposal** (8.3).
4. **The class's default** (D5).

2 and 3 come through the core's hook, with phase 8; that an `Expectation` comes before a rule and after the entry
is main's call. The first build has 1 and 4 only.

**Other changes to steps** (the rows below are as first written unless marked):

- **2.7 (new), a degree in the entry** (**Done** 2026-11-25, [as built](#27-as-built-2026-11-25)): a field marker `Degree()` (`markers.py`, as `Holder()` in 2.5) on a field of
  a space class that the project declares, so that no space gains a field it did not ask for and a project without
  it has no migration; at most one on a class; its value in five steps (as an `Expectation`'s `how_expected`) or a
  number from `0` to `1`, read as `0` to `1` (**decide**, D16: the marker against a field every space has; steps
  against a number); refused at `initialise()` on a space whose `veridical` is not `0`; exported, and drawn in the
  form beside the space's head. Pure: the checks, the export; conformance: written, in the path, read back; built by
  `builder` after 2.5.
- **1.1**: a space's entry of the path has its `degree` when one was entered.
- **3.1**: `signature` gives the degree of the entry where the path has one, else the class's default.
- **2.3**: the migration of 1.3 also counts, by class, the stored spaces of a `unary` class that hold two or more
  items (`pangloss check` reads no database); `unary` is at most one, and at least one as any `contents` is today.
- **4.1**: the fields of the spaces a rule can pass through go into its `rule_hash`, so a change of `veridical` makes
  its facts due again; "likely" and (e) are built with phase 8.
- **6.3**: an undated statement is never left out by "after it"; it answers with the date as a target not judged.
- **6.5**: each relation of 6.2's table has the verdicts that may override it, written into 6.2's brief (D7 is asked
  with that table).
- **6.6**: learning the class defaults of the degree from how often orders were carried out is left out of the first
  version: only orders whose outcome a source recorded are seen.

## The degree of a statement's contents

(Changed 2026-11-25: the degree is an axis of its own, beside `veridical`, and no part of the walk: [the review](#the-review-of-2026-11-25-and-what-it-changed), R2 and R3. What follows is as first written.)

Added 2026-11-24, from the user's point: an order is asserted (`1`); its contents are `0` by default, since the source
does not say they were carried out; but an order from the king makes them likely to have happened, and **often the
order is the only evidence that something happened at all**.

- **A degree, on the veridical axis, for each statement whose contents the source does not assert**: from `-1` to `1`,
  how far its contents count for (or against) having happened. The class's `veridical` (`-1`, `0`, `1`) stays the
  default and keeps the logic (the rewrites, and the kind of relation: an order and "it was done" is a fulfilment,
  not two sources agreeing); only the degree is per statement.
- **Proposed by rules, confirmed by a person**: rules of the project over who has authority over whom propose it (an
  order from the addressee's superior higher; a request to a superior, or an order from someone with no standing,
  lower); with no data it is the class's default; a person confirms or moves it (an `Expectation`, 8.1). It replaces
  the "lean" of the walk, which was its sign without a size.
- **It composes along the path**: a king's order *not* to buy counts against the buying, at the same degree; a
  statement between two spaces still stops it (that the order was not given says nothing of the buying).
- **For prescriptions it is evidence**: the contents of an order, a promise or an intention count as having happened
  at their degree wherever nothing else tells what happened; once another statement does, that decides (comparison,
  phase 6). **For a denial it is not**: the expectation is the virtual relation's strength (how live the positive
  was), and the contents stay at `-1`, the denial being the evidence. (Reports could be treated as prescriptions are,
  as how far to trust them; that is source criticism of its own, and not proposed here.)
- **What it changes**: derived gains a status "likely" between asserted and prescribed, and a fact from a royal order
  is a weighted fact, not only a virtual "was to give to" (4.1); the time part dates by it (5.2); the graph part's
  actual network is weighted by it, asserted contents in full, a royal order's as likely, a stranger's hardly at all
  (5.3, 5.4); comparison weighs by it (an order with no other evidence still supports a later report; a failure to
  carry it out is the more notable, the higher the degree: 6.2), and learns the class defaults from how often orders
  of each kind were carried out (6.6); `Expectation` covers prescriptions as well as negatives (8.1); the rules of
  authority are 8.3's.
- **The class's default** (strength: an order above a request above a recommendation) is D5's answer: a fifth field
  on `SemanticSpaceMeta`, since derived, the graph and time parts, comparison and the interface would all read it, or
  each package's own slot (**decide**).

## The ground of a head class

Added 2026-11-26, from the user: "it would be very useful to be able to describe the semantics of the 'ground'
space", since an entity may have relations that are certain, "kind of definitionally true", which is a different
semantics from that of the documents (factoids) it appears in. **Nothing of it is built.** It is steps 3.4 to 3.6,
4.5 and 5.1b below, and is built **first of what is outstanding** ([the order from here](#the-order-from-here)).

**What the ground is.** Until now the walk started every path as asserted, by no one: a statement directly in a
factoid and a relation an entity holds itself read the same. The ground is what a head class says of everything it
holds outside any space: the walk starts from it instead.

**Decided by the user (2026-11-26):**

| | Decision |
|---|---|
| G1 | The difference between "definitionally true" and "a source says" is **not on the truth axis** (both are asserted): it is **whose commitment it is, and whether it can be contradicted**. |
| G2 | **By class only.** No field on an item changes its ground (a forged charter is said by a space, or by a class of its own). |
| G3 | Built when main thinks best, the outstanding steps put in the most efficient order: [below](#the-order-from-here). |

**Main's proposal for the shape** (the names are main's, and the user may change them):

```python
class Factoid(Document):
    _meta = Document.Meta(ground=Ground(by="source"))      # a claim, the source's
    source: Source
    statements: list[Statement | Negative[Statement]]


class Person(Entity):
    born: Date | None = None                               # the record: Entity's default ground


class Rumour(Document):
    _meta = Document.Meta(ground=Ground(veridical=0, degree="possible"))
```

- `Ground(veridical=1, fit="describes", degree=None, by=None, standing=None)`, frozen and checked as `Modal` is,
  exported from `pangloss_models`; `ground=` on `Document.Meta` and `Entity.Meta`, inherited.
- **`veridical`** `1` or `0` (a ground does not deny: `-1` is refused), **`fit`**, **`degree`** (only with `0`): as
  a space's, so that the walk treats the ground as the outermost thing said.
- **`by`**: the field of the head that says whose commitment it is (a factoid's source), as `Attribution(by=)` does
  for a space; checked as that is (a relation of the class that reaches an entity).
- **`standing`**: `"claim"` (it can be contradicted by another claim) or `"record"` (what claims are held against).
  Left out: `"claim"` for a document, `"record"` for an entity. A record has no `by` (refused).
- **Left out altogether**, a class reads as today (asserted) with its kind's standing, so a project that says
  nothing sees no change but the new values of the signature.
- **A nested document has its head's ground**: `ground=` on a class counts only where an item of it is the head.
- **Not data**: no migration, out of the snapshot, as a space's options are. A path already begins with its head's
  entry, so the walk finds the ground by that entry's class; for what a head holds itself (an empty path) the
  caller gives the head's class.

**What it changes in what is built**: the walk in Python and in TypeScript (3.5) and the shared cases; derived and
the RDF export (4.5); the planted world, whose `Factoid.source` becomes the factoid's ground (5.1b). The time part
(5.2) and the identity claims (4.3) do not change. **What uses it later**: comparison (a source against another
source is a disagreement, a source against the record another relation; "the same source" comes from the ground,
6.2), the guard of feasibility (8.2: "impossible" only against the record), the actual network (5.4: the record
joins in full). **In the interface**: how a ground is shown is open (the user: "not sure how this would be
represented"); the first form would be the head of a page saying "according to" its source, or "record".

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **3.4 `Ground` and its checks** | `Ground`, `ground=` on the two metas, inherited; the defaults by kind; refused at `initialise()` with a fix where one is plain: `veridical=-1`; `degree` with `veridical=1`; `by` that is not a relation of the class reaching an entity; a record with `by`. Exported on a model (`ground`: what holds, never null) and in the TypeScript types; out of the snapshot | Pure: defaults, inheritance, every refusal by its message; the export; no migration from a change | Main | **Done** 2026-11-26, [as built](#34-as-built-2026-11-26) |
| **3.5 The walk starts from the ground** | `signature(path, spaces, head=None)`: the sign, the lean and the degree start from the ground of the path's first entry's class (of `head` where the path is empty); `Signature` gains `standing` and `grounded_by` (the head's id and the field named by `by`, for the caller to read whose it is). `registered_grounds()` in the export's shape. `space_cases.json` gains cases; the TypeScript port (`schema/spaces.ts`) passes them | Pure: the cases (a claim, a record, a ground of 0 with and without spaces inside, a denial inside a ground of 0, an entity's own relation); Vitest on the same file; conformance: a stored signature | Main ★ | **Done** 2026-11-26, [as built](#35-as-built-2026-11-26) |
| **3.6 Docs and the skill** | [semantic-spaces.md](semantic-spaces.md) (a section "The ground"), `imports.md`, the guide's statements page, the skill's `references/modelling.md` | The skill's check | `builder`, read by main | **Done** 2026-11-26, [as built](#36-as-built-2026-11-26) |
| **4.5 The readers** | Derived: a justification says its standing, and a fact all of whose justifications are of the record is told apart from one a source says (`status.py`, the Derived section's mark). RDF: the record has its direct triples as today; a claim with `by` names whose it is (**decide** the predicate with the user if the mixins do not give one) | The packages' tests; live on both backends for derived | `builder` ★ | **Done** 2026-11-26, [as built](#45-as-built-2026-11-26) |
| **5.1b The planted world** | `similar_models.declare(compared=True)`: `Factoid` has `Ground(by="source")`; `planted`'s truth of "the same source" is then what the ground says | `test_planted_compared.py`: the walk gives each added statement its source | Main | **Done** 2026-11-26, [as built](#51b-as-built-2026-11-26) |

### 3.4 as built (2026-11-26)

On `spaces-ground`. `pangloss_models.model_bases.ground` (`Ground`, `ground_of`, `has_ground`), exported as
`pangloss_models.Ground`; `ground: Ground | None = None` on `DocumentMeta` and `EntityMeta`, inherited.

- **`Ground`** is a frozen pydantic dataclass, keywords only, so a value of the wrong type is refused where it is
  written. `veridical=-1` is of its type and refused at `initialise()`, so that the refusal can say what to write.
- **`ground_of(model)`** is the ground as it holds, never None: what the class sets or inherits, else asserted, the
  standing filled in by kind. The meta keeps what was written (`None` where nothing was).
- **The checks** (`initialise_models/check_grounds.py`), after the degree fields': `veridical=-1`; a degree with
  `veridical=1` (fix `ground_degree`: `degree` left out of the `Ground(...)` written in the class's own `_meta`,
  the one refusal whose fix is plain); `by` on a record, the message saying which made it a record (`standing`, or
  being an entity); `by` that is no field (with the nearest name), not a relation, or a relation reaching only
  documents (`check_attributions.reaches_an_entity`, so through a wrapper too).
- **Settled by main**: a class is refused for the values only where its ground is not its parent's; **`by` is
  checked on every class that is not abstract**, the inheriting ones too, so an abstract base may name a field its
  subclasses declare, and a subclass without it is refused in its own name. A `ground` on a class that can never be
  a head (`create_directly=False`) is allowed and says nothing: no warning (a subclass's ground may come from an
  abstract base above both).
- **The export**: `ground` on every model of kind `Document` or `Entity` (`export.export_ground`): `veridical`,
  `fit`, `degree`, `by` (`{name, key}` or null), `standing`. `GroundDefinition` and `Standing` in the interface's
  `types/models.ts`. `migrations.snapshot.HEAD_KEYS` leaves it out of what is compared: no migration from a change.
- Tests: `tests/test_ground.py` (17). The whole of `pangloss-models` (1779), ruff and `ty` pass.

### 3.5 as built (2026-11-26)

- **`signature(path, spaces=None, grounds=None, head=None)`** (`pangloss_models.spaces`). `grounds` is the ground of
  each head class in the export's shape (`GroundFacts`), read from the models where it is not given
  (`registered_grounds()`: every document and entity class, as `ground_of` has it). `ground_at(path, grounds, head)`
  is the ground a path starts from.
- **`Signature` gains `standing`** (`"claim"`, `"record"`, or None where the path has no ground) **and
  `grounded_by`** (`GroundedBy(head, field, key)`: the head's id, the field the ground's `by` names, and its key in
  the API's JSON; None where the ground names no one). In `as_json()`: `standing`, `groundedBy`.
- **A ground of `veridical=0`** starts the walk as the first space that leaves its contents neither would: leaning
  for, at the ground's degree. The rest is the walk as it was, so a denial inside leans against at the ground's
  degree, and a space inside that leaves its contents neither has its own degree, the ground's never taken in its
  place (as an outer space's is not). A ground is no operator: nothing is normalised with it (the head's entry is a
  statement, which ends any run).
- **A ground that prescribes** (`fit="prescribes"`) makes everything the head holds prescribed, by the head
  (`prescribed_by` is the head's id; None for the head itself); a space further in that prescribes takes its place.
- **Settled by main, where the brief was silent**:
  - *A head class the table does not have* reads as its kind's default (`DEFAULT_GROUNDS`: a document a claim, an
    entity the record), which is what a class that says nothing says: a table may leave such classes out, and a
    path of a form whose head the models do not know still walks. *A `head` named that the table does not have* is
    refused (`UnknownHeadError`): the caller named it.
  - *A path that begins with neither a document nor an entity* (a part of one made by hand: derived's ways of
    wrappers) has no ground: asserted, `standing` None. So has an empty path with no `head`.
  - *The path given must be whole*: the first entry is taken to be the head. Every caller gives stored paths, or the
    part of one that starts at its head.
- **The cases**: `space_cases.json` has `grounds` beside `spaces`, a case of the head itself has `head`, and every
  expectation has the two new keys; 24 cases of the ground (81 in all). `tests/test_spaces_walk.py`.
- **TypeScript** (`schema/spaces.ts`): `signature(path, spaces, grounds = {}, head?)`, `signatureOf` the same,
  `groundFacts(definitions)` (a model exported before the field reads as its kind), `groundAt`, `DEFAULT_GROUNDS`,
  `UnknownHeadError` (which `signatureOf` does not swallow). Passes the same file. The two callers give the grounds:
  the mark of a list's row (`SpaceBands.tsx`) and the library's reading of claims (`identity.ts`).
- **Conformance** (`test_stored_signature.py`, both backends): the signature of statements of a charter and of a
  rumour from the paths a query reads; whose a statement is, read of the head by `grounded_by`; the head itself and
  an entity by `head=`.
- **The callers in other packages**, each by what it is for:
  - *The library's clusters* (`clusters.py`) give the grounds, as its interface does: a claim of identity in a
    document whose class leaves what it holds neither asserted nor denied joins nothing. The brief said the
    identity claims do not change: this is the one way they do, and only for a project that declares such a ground.
  - *The time part* gives no grounds (`{}`), on purpose: what a rumour says did not happen is denied as what a
    charter says did not. Its rule (5.2) and its signature are unchanged.
  - *Derived and the RDF export* give `{}` for now, so that nothing of theirs changes before 4.5.
- **The second reading (★)** found the walk right on every combination it traced, and the two ports agreeing.
  Mended by main after it:
  - *a claim that is itself a head* (a project's own statement of identity, a head document) has no path, and was
    read with no ground: the clusters and the library's interface now name its class as `head`
    (`test_identity_clusters.py`: a claim in a rumour, and a rumour that is itself the claim, join nothing);
  - an entry with no `id` (a form's new node) no longer fails in Python, as it did not in TypeScript;
  - cases added (85 in all): a nested document of a class with a ground of its own has its head's; a "not" and a
    space inside a ground of 0, in both orders; a denial inside a ground that prescribes; a first entry that is a
    wrapper; a `head` named that a partial table leaves out (refused);
  - the docstrings of `fit`, `prescribed_by` and `degree`, which now also come from the ground.
- **Found and left, to know**:
  - *a ground of 0 with no degree marks nothing in a list*: `markOf` leaves out "reported" with no degree because
    the bands round it say so already, and a ground has no band. With a degree every item inside is marked. It goes
    with how a ground is shown, which is open with the user (7.x);
  - `Ground(veridical=1, fit="prescribes")` is allowed, as the same pairing is on a space;
  - Python reads the models' grounds where none are given, TypeScript reads `{}` (it has no registry): each says so.
- **Green**: `pangloss-models` (1812), the conformance files of the stored signature and the clusters on Memgraph
  and Neo4j (27 each), Vitest of the core (366), `tsc`, and the whole of the library, the time part, RDF (312) and
  derived (467) on Memgraph. The library module's own Vitest was not run (it needs a built project): e2e covers it.

### 3.6 as built (2026-11-26)

`builder` from main's brief, read by main. [semantic-spaces.md](semantic-spaces.md#the-ground-what-a-head-says-of-what-it-holds-):
a section "The ground" (the options, the refusals, the export), and in "The walk" the two new values, "From the
ground", and who reads the ground and who does not yet. `models.md`, `imports.md`, `status.md`; the tutorial's part 4
("Whose claims they are": its `Factoid` now has `Ground(by="source")`, and part 6's copy of the class with it); the
skill's `modelling.md` and `interface.md`. The skill's check passes.

### 5.1b as built (2026-11-26)

`similar_models.declare(compared=True)`: `Factoid` has `Ground(by="source")` (its `source` stays optional: a factoid
of the world before comparison has none). `tests/test_planted_compared.py` (14): for every statement the world added,
the walk gives standing `"claim"` and `grounded_by` the factoid and `source`; the source read of the factoid by it is
one of the world's, and "the same source" by the ground is the truth's `same_source` for every verdict. The ground
asserts, so nothing else read of the world changes.

### 4.5 as built (2026-11-26)

Derived by `builder` from main's brief; the RDF export by main; a second reading (★) of both, whose findings main
mended. [derived.md](derived.md) ("From the ground"), [rdf.md](rdf.md) ("Shape of the data").

- **Derived.** A checked rule keeps the grounds (`CheckedRule.grounds`, in its hash). Each part is walked from the
  ground of its head; a node that is itself a head by its class **as stored** (the query's `walks` gives each
  node's `type`). `status.standing`: a justification is `"record"` where no part is a claim and one is of the
  record, a relation that starts at an entity having that entity's class's standing (the query's `starts`).
  Stored on the justification and summed on the fact (`"record"` only where every justification is:
  `SUMMARY_QUERY`, `status.summed_standing`); given wherever `status` is (views, `_derived`, `why`, the graph,
  GraphML, the CSV, derived's RDF as `pgo:derivedStanding "record"`). The Derived section marks a fact "Of the
  record"; a claim has no mark. `standing` is a reserved field name of a `DerivedEdge`.
- **The RDF export.** `Context` has `grounds` and `head_type`; the walk of each node starts from the head's ground.
  `convert.grounded`: of the graph, in the default graph, `pgo:standing` (every head) and `pgo:accordingTo` for each
  entity the ground's `by` reaches (through a reified relation). Both in the ontology's core.
- **Decided by main, the user to confirm**: the two predicates are Pangloss's own (`pgo:standing`,
  `pgo:accordingTo`). The plan said to decide the predicate with the user if the mixins give none: they give none
  that says "this graph is this agent's claim", and the field's own triple (aligned to whatever the project aligns
  it to) is there as before. The names can be changed at no cost (nothing stored).
- **Mended after the second reading**:
  - *what rests on a rumour was "reported" and yet plain* (a ground is no space, so no label): the head's class is
    now among the justification's labels (`status.under_grounds`), so the fact is not `plain` and has no direct
    triple in derived's RDF;
  - *a rule that derives a document made one from a rumour's statement*: it does not, unless it names its
    statuses;
  - *a rule over entities alone with no relation* was a claim: it has the standing of its entities' classes (the
    pattern's classes: the query returns no stored class for them);
  - *RDF: the head itself under a ground of 0* lost its outside classes and the triple of its `by` field: a node
    is asserted or not (`Context.asserted`: the head always is), what it holds in a field is another question
    (`Context.holds(field)`: by the ground, and always for the `by` field);
  - *RDF: `pgo:accordingTo` was written from a field the export leaves out* (`RDFField(exclude=True)`): not now.
- **Found and left, to know**:
  - under a ground of 0 the head's own literal fields lose their outside properties (a title aligned to
    `dcterms:title`), as everything it holds does;
  - a fact or justification stored before this step has no `standing`, and a read of it fails until its rule is
    derived again, which the changed hash forces (D18: nothing stored is carried over);
  - no browser test of "Of the record" (the e2e project's facts rest on documents); Vitest only;
  - no filter by standing (`Where`, `?standing=`): not asked for;
  - derived does not read `grounded_by` (whose a claim is): comparison will (6.2).
- Tests: derived's `tests/test_derived_status.py` and `tests/live/test_derived_ground_live.py`; RDF's
  `tests/test_rdf_converters.py`, `tests/test_rdf_ontology.py` and `tests/live/test_rdf_ground_live.py`.

## The features this plan changes

| Package | Feature | What changes | Phase |
|---|---|---|---|
| `pangloss-models` | `propagate_context` (`context.py`), `_InstanceContext` (`model_bases/instance_context.py`) | The fault's fix | 1 |
| | `SemanticSpaceMeta`, `Modal`, the checks, the export, field markers (`Holder()`, `Addressee()`) | The four fields | 2 |
| | `pangloss_models.spaces` (new) | The walk | 3 |
| `pangloss-cypher` | `StoredContext`, `recompute_contexts` (`migrations/operations.py`) | The fault's fix; mending stored data | 1 |
| | The reads that give the lists to views (`read_query.py`, `list_query.py`, `read_incoming.py`), citations (`citations.py`), search's `$spaces` (`search_query.py`) | Right lists once mended; `$asserted` later | 1, 4 |
| `pangloss-cli` | `pangloss contexts check \| fix` | New | 1 |
| `pangloss-lsp` | Diagnostics | The new refusals, with their fixes | 2 |
| `pangloss-derived` | Justifications and facts (`compile.py`, `store.py`, `read.py`), document rules, `why`, `export`, its RDF, `graph`, the views, its interface section | A status from the walk; denials blocking positive classes; virtual edge classes; liveness on each justification | 4 |
| `pangloss-criteria` | `$derived` (filters facts by their justifications' context labels) | Follows derived's status | 4 |
| `pangloss-library` | Identity clusters (`clusters.py`, `in_spaces`; `identity.ts`); `Expectation[T]` (new) | Claims by the walk; the judgement of a negative | 4, 8 |
| `pangloss-rdf` | What is asserted inside a space (`convert.py`, its own walk) | By the four fields | 4 |
| `pangloss-dates-vectors` | `counts_for` | The date of what is not asserted | 5 |
| `pangloss-fastrp` | `FastRPMeta(stop=...)` on spaces; weights | The `stop` question; weights by the walk and by liveness; the actual network as a second part | 5, 8 |
| `pangloss-vectors` | Profiles (`VECTORS_PROFILES`); the "Similar" section | Two networks' profiles; labels by relation | 5, 7 |
| `pangloss-reconcile` | `RECONCILE_PROFILE`; its "named with" reason | Stays on the structural network; a claim that two are different, later | 5 |
| `pangloss-learn` | Unchanged | Used by comparison's learning, and by link prediction's calibration | 6, 8 |
| `pangloss-compare` (new) | `CompareMeta`, pairs, the verdict, `EventJudgement`, the route, learning | Phase 12, rewritten on the four fields | 6 |
| `pangloss-review` | Suggestions | A suggestion of a statement (suggested grounds), later | 8 |
| `pangloss-history` | Its side by side (`align.ts`, `AlignedCell.tsx`) | Moved into `interface-core` and shared | 7 |
| `pangloss-interface` | Forms (`schema/headless.ts`, `ModelFields.tsx`, `TypeMenu`); bands (`Item.tsx`, `List.tsx`, `ItemContents.tsx`); the search form (`$spaces`) | Spaces with no choice drawn headless; "not" as a toggle; what is not asserted marked; the walk in TypeScript | 7 |
| `pangloss-testing` | The planted world; conformance; the parts' suite | Spaces, orders, denials and reports in the world; the fix's conformance tests | 1, 5, 6 |
| `pangloss-demo` | Its spaces, its `CompareMeta`, its judgement class | The fields (no migration); comparison | 9 |
| Docs, guide, skill, `e2e` | | Each phase's pages; `COVERAGE.md` | each |

## The order

```
0 the ground ─► 1 the fault ─► 2 the fields ─► 3 the walk ─┬─► 4 the packages that read spaces ─┐
                                                           ├─► 5 the vector parts ───────────────┤
                                                           ├─► 6 pangloss-compare ───────────────┼─► 7 the interface ─► 9 the end
                                                           └─► 8.1-8.3 negatives ─► 8.4-8.6 ─────┘
```

- **0 to 3 are the foundation**, in the core; 1 is worth doing alone, since it mends a fault.
- **4, 5 and 6 depend on 3**, and 6 on 5.1 (the planted world) and on 2.5 (the addressee): 4 can go beside the
  others, 6 not before 5.1.
- **7.1 and 7.2 need only 2.4** (the export), and **7.3 only 3**: they do not wait for phase 6.
- **Built in three parts** (the user, 2026-11-25). *First*: phases 0 to 3, 4.1 to 4.4, 7.1 to 7.3, and the fields on
  the demo's spaces (9.1's first sentence). *Then comparison*: 5.1, phase 6 (less 6.7), 7.4 to 7.6. *Then negatives
  and the degree*: phase 8 with the core's hook for a degree, the weights of 5.2 to 5.4, 4.1's "likely" and (e), 6.7,
  7.7. Phase 9's guide, measurements and end close each part.
- **8.1 to 8.3** need 3 (and 0.5); their uses (8.4 to 8.6) need 5 and 6.
- **7** needs 3 (the walk in TypeScript), 6 (the comparison's sections) and 4 (derived's status shown).
- A pause for the user's word **after each phase**, and inside one wherever a step says **decide**.

### The order from here

Set 2026-11-26, at the user's word to put what is outstanding in the most efficient order. It overrides the list
above where they differ.

1. **The ground: 3.4, 3.5, 3.6**, on a branch `spaces-ground` made from `spaces-5-vectors`. First, because 6.2's
   verdict reads the signature and would otherwise be written twice, and because it is small and in the core.
2. **5.1b and 4.5** on the same branch (the world, then the two readers); the whole suite; pause for the user
   (`spaces-ground` and what it stands on into `dev`).
3. **Phase 6, the comparison**: 6.1 (`builder`) beside 6.2 (main), then 6.3, 6.5, 6.4, 6.6, on `compare-6`. 6.4
   (pairs by vectors) needs the user's answer on 5.3, and goes after 6.5 so that the rest does not wait for it.
4. **5.4 and 5.5**, when the user has answered 5.3 (one network or two): they depend on nothing else here, and can
   go between any two steps above once the answer is there. 5.4's costs are measured on both backends first.
5. **7.4 to 7.6** (the comparison in the interface), with how a ground is shown, talked through with the user first.
6. **Phase 8** (negatives, the degree from outside, the weights of 5.2 to 5.4, 6.7, 7.7), then **phase 9**.
7. **4.2** whenever criteria's step 13 is built (another plan).

**Done (2026-11-26)**: steps 1 and 2. **5.3 answered by the user (2026-11-26): two networks**, as main recommended
([the figures](#53-measured-2026-11-26-waiting-for-the-user)), so 5.4, 5.5 and 6.4 wait for nothing.

**Still open with the user**: `spaces-7-bands` and
`spaces-5-vectors` into `dev`; the band's look (left by the user for later); the names `Ground` and `standing`.

## How the work is run

As in [the similarity build plan](similarity-build-plan.md#how-the-work-is-run):

- **Branches** (changed 2026-11-25): one branch for phases 0 to 3, `spaces-foundation`, made from
  `formalise-semantic-spaces` (which holds this plan and is `dev` with the design pages; it reaches `dev` when
  `spaces-foundation` is merged), and one for each line after it (`spaces-4-readers`,
  `spaces-7-forms`, `spaces-5-vectors`, `compare-6`, `spaces-8-negatives`), each merged into `dev` when its last step
  is green and the user says.
- **Commits**: one for each step, pushed as soon as it is green; "Where the work stands" at the foot of this page and
  the memory note brought up to date in the same commit, so that a session that stops costs at most the step in hand.
- **Three kinds of test**, named in every step: *pure* (no database), *live* (on Memgraph and on Neo4j, with
  `pangloss_testing.live`), *conformance* (`pangloss_testing/conformance/`, for what storage does). A new package's
  `tests/live` is added to the Neo4j list of `run_tests.sh` in the step that makes it (`pangloss-compare`, 6.1).
- **Docs with the code**: a step that changes what a modeller or a package author types changes its page in the same
  commit, and the skill when it would otherwise be wrong; "As built" sections here where the code differs.
- **Databases**: never `:7687` (the tests) or `:7688` (the demo) for scratch work; the planted world on its own
  containers (`:7702`, `:7706`, `:7707`, as the similarity plan has them); a migration of the demo is written and
  read, not applied, unless the user says. Measuring at size is one run each, bounded: ask before anything longer.

## Who builds each step

Rewritten 2026-11-25.

- **Main**, the session holding this plan: settles what a step leaves open; makes every change to a core read or
  write path (the path and `context.py`, the meta and its checks, the walk, the verdict's maths); takes the
  measurements; writes the briefs, reads each diff, writes "As built" and commits.
- **`builder`** (`.claude/agents/`): decided work from a written brief, with its tests; it does not commit. **One at
  a time on the shared working tree.** Two lines side by side only with a worktree each (`isolation: "worktree"`) and
  `PANGLOSS_TEST_DATABASE_PER_WORKER=1`: a builder may not switch branch, and the tests empty `:7687`.
- **`test-runner`** (`.claude/agents/`): every run; the whole suite before each merge; never two database runs, or a
  database run and an e2e run, at once.
- **`Explore`**: reads the code for a question (0.4, 0.5), several at once.
- **A second reading** (★, and every interface diff): a fresh `general-purpose` agent given the diff and the brief,
  not main's reading of it; for an interface diff it loads the `solidjs-v2-reviewer` skill (a skill, not an agent).
- `.claude/agents/` is committed with the first step, so that a later session has the same agents.

## Phase 0: the ground

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **0.1 Why single relations share their lists** | Answered on the demo, read only: the sharing gives a document its place in the context of what follows it (the result of the demo's `Causes` has its cause in its context); a copy of the lists would lose it, and the narrower fix keeps it ([as found](semantic-spaces-plan.md#phase-0-as-found-2026-11-24)) | — | Main | **Done** 2026-11-24 |
| **0.2 What `stop` does, as a test** | Whether a statement inside `Negative` (`FastRPMeta(stop=True)`) is still joined to its own people, on a graph in memory (`pangloss_fastrp.maths.joins`): factoid → `Negative` → statement → person. Read so far: it is | Pure, in `pangloss-fastrp`'s unit tests, kept as a test of what the code does | Main | **Done** 2026-11-25 ([as found](#phase-0-as-found-2026-11-25)) |
| **0.3 Who reads the spaces** | Every reader of the stored lists, by file: [the table above](#the-features-this-plan-changes) | — | Main | **Done** 2026-11-24 |
| **0.4 What a derived rule can read** | Whether a rule can read another rule's edges (a notable absence from an expectation and its denial, 8.3). Known already, from [derived.md](derived.md): a rule cannot say "unless" (no negation across documents, decided); its date conditions (`overlaps`, `within`) are generous by a date's uncertainty unless `strict=True`; and its facts are derived again when a write touches what it reads (`DerivedRegistry.triggers`). No arithmetic on dates is asked of a rule (the user, 2026-11-24): what an expectation needs of the data is in 8.2 and 8.3 | A written finding in 8.3's brief | `Explore`, read by main | **Done** 2026-11-25 ([as found](#phase-0-as-found-2026-11-25)) |
| **0.5 A package's document about the project's statements** | `EventJudgement` (6.5) and `Expectation` (8.1) are documents that point at statements by citing them (so that Pangloss notices when a cited statement changes). They ship in packages, which do not know a project's statement classes, so the class takes the statement class as a parameter that the project fills in: `class StatementJudgement(EventJudgement[Statement])`. Pangloss has such parameters on wrappers (`Negative[T]`, `Identification[T]`); whether a top-level document can take one, and still be migrated and saved, has not been checked (phase 12's first question for its 12.2). If it cannot: the package ships a base class without the citing field, the project declares the field with its own class (`statements: list[Cites[Statement]]`), and `initialise()` checks that it did | A written finding in 6.5's and 8.1's briefs | `Explore`, then main | **Done** 2026-11-25 ([as found](#phase-0-as-found-2026-11-25)) |
| **0.6 (removed)** | Was "how a field reached through wrappers is found from its class". Not a question: the code already reaches the entities behind wrappers (search's `through`: `held_field_names` and `wrappers_of` in `pangloss_models.search`; derived's rules match through them), and the field definitions know which field narrows which (`FieldSubclassing`). 2.5 and 6.1 reuse that | — | — | Removed 2026-11-24 |
| **0.7 What stored nodes hold today** | On a scratch database (never `:7687`, `:7688`): the shapes of `/tmp/plan-review/t.py` written and read back, to say whether stored `context_labels` hold the node itself and its siblings as the trial on plain objects does (it depends on whether assigning the lists copies them). The finding goes into 1.3's brief (what the migration replaces) and 1.4's (what the readers showed until now) | A written finding | Main | **Done** 2026-11-25 ([as found](#phase-0-as-found-2026-11-25)) |

### Phase 0 as found (2026-11-25)

**0.2, what `stop` does.** `FastRPMeta(stop=True)` makes a space an `end`: a chain from the factoid stops there with
no join, and that is all. The statement inside is still a stop of its own, with joins to its people. So "Ada did not
meet Ben" joins Ada and Ben to the denied meeting, two joins from each other, with exactly the vectors of a pair
that did meet (cosine 1.0 on the test's graph); the one thing the space changes is that neither is joined, through
the statement, to the factoid, its source or the other statements of it. Kept as
`test_the_people_of_a_statement_inside_a_stop_are_still_two_joins_from_each_other`
(`packages/pangloss-fastrp/tests/test_fastrp_rules.py`), a test of what the code does, beside
`test_a_stop_ends_the_chain_with_no_join`, which already had the join. For 5.3: `stop` today is "apart from its
source", not "does not count"; whether it should end the statement's own joins is that step's question.

**0.4, what a derived rule can read** (`Explore`, read from the code, nothing run). **A rule cannot read another
rule's derived edges; it can read another rule's derived documents.**

- A rule's `.when()` takes only `Model.Where` patterns (`declare.py`, `as_constraint` refuses the rest); a derived
  class's `Where` is a `DerivedWhere` (`views.py`), not one, so it is refused with a `TypeError` (no test of that).
  The compiled query walks field edges between model labels only (`compile.py`), never `PGDerived` nodes or shortcut
  edges. On purpose: [derived.md](derived.md) ("no recursion"; a derived class in a rule's body needs strata).
- A chain through **derived documents** is built: a rule's pattern names a class another rule's template writes;
  the rules are ordered (`check.py`, `rule_graph`, `build_order`), loops refused (`refuse_cycles`), the worker
  follows the order, and a worker's write leaves work for the readers. Tested pure
  (`test_a_chain_is_allowed_and_built_in_order`, `test_a_rule_of_edges_that_reads_derived_documents_comes_after_their_rule`)
  and live (`test_a_rule_reads_what_another_derived_and_its_documents_rest_on_those`).
- **For 8.3**: a notable absence from an expectation and its denial needs no change to derived if the rule of
  expectation derives a *document* (an "expected at" statement in a derived factoid) and the second rule reads that
  class beside the denial. Reading facts directly would need: `DerivedWhere` taken by `when()`; a `PGDerived` node
  compiled; evidence for it (a fact has no head: the heads of its justifications); edge rules in the rule graph; and
  a fact's write leaving work for its readers. Not proposed.
- Also read: a rule's query reads only `meta.semantic_spaces` of what it matches (`compile.py`: blocked spaces, and
  `spaces` returned for each node that is not an entity), never the nodes' `context_labels`; `store.py` joins them
  with the wrappers on the rule's own paths into the justification's `context_labels` (derived's own, a list of
  names). `rule_hash` covers the class, fields, template, nodes, edges, values, constraints, patterns, and
  `blocked`, `transparent`, `exclusive`: nothing of a space's own fields (4.1 adds them). A wrapper's `DerivedMeta`
  is one of `block`, `transparent` (taken out of the context) or `qualify` (the default for a space); a rule's
  `block=` and `allow=` override it, and for a document rule `qualify` is `block` unless allowed.

**0.5, a package's document about the project's statements** (`Explore`; one trial run with no database, the SDK's
storage and `initialise(bind_database=False)`). **A top-level document cannot take a type parameter today**, so
6.5 and 8.1 take the fallback.

- `class EventJudgement[T](Document)` with `statement: Cites[T]` fails at `initialise()`: field definitions are made
  for every registered class, the unfilled generic base among them, and `cited_types` (`citations.py`) refuses the
  type variable ("only a document can be cited"). It is not refused by name, only not handled: the generic paths of
  `initialise_field_definitions.py` cover reified relations, semantic spaces and conjunctions. `abstract=True` on
  the base changes nothing.
- Were that mended there is more: `EventJudgement[Statement]` is a class of its own, not abstract (`abstract` is not
  inherited), and would be given routes; and `generic_get_subclasses` (`utils.py`) does not look below a filled-in
  generic, so `StatementJudgement` would be missing wherever a class is expanded to its subclasses (relation
  targets, `Cites[EventJudgement]`, the export's `concrete`). The labels, the snapshot, the export and the stubs
  would be right as they are. Pydantic itself does fill `Cites[T]` in on the subclass.
- **The shape to build** (tried: it initialises, and `Create` has the fields of both):

  ```python
  # the package
  class EventJudgement(Document):
      _meta = Document.Meta(abstract=True)
      verdict: ...
  # the project
  class StatementJudgement(EventJudgement):
      statement: Cites[Statement]
      other: Cites[Statement]
  ```

  No type parameter at all (a generic base leaves the stray class). `EventJudgement` is then a label of every
  judgement, which the route's query wants. The package checks at `initialise()` that each class below its base
  that is not abstract has the citing fields, by a hook of the registry as `pangloss-library` does
  (`_registered_once(ModelRegistry.after_finalise, ...)` reading the field definitions' cited types), raising a
  `PanglossModelError` with a `fix=`. The same for `Expectation` (8.1). As `ZoteroBacked` and
  `DateCharacterisation` are shipped today.

**0.7, what stored nodes hold today** (written and read back on a scratch Memgraph, `:7695`, through the models;
`/tmp/space-07/test_stored_shapes.py`). Stored `context_labels` are as the trial on plain objects had them: the
dictionaries of the labels are shared (`assign` copies the list, not its entries), so a node's stored label holds
whatever was added after the node was given it.

| Written | Stored |
|---|---|
| `Order(thing=Ordered[P], witnesses=[W])` | P: spaces `[Ordered]`, `Ordered: [P]`. **W: spaces `[Ordered]`, `Ordered: [W]`** (the fault, with one single relation and a list) |
| `Not[P]` | P: `Not: [P]` (itself) |
| `Not[Service(parts=[P])]` | Service: `Not: [Service]`; P: `Not: [Service, P]` |
| The same, `Service` with `use_in_semantic_space_label=False` | Service: `Not`; P: `Not: [P]`, the same as `Not[P]` |
| `Not[Causes(cause=A, result=B)]` | A: `Not: [A, B]`; B: `Not: [A, B]`; the `Causes` itself: `Not: [A, B]` (what it holds) |
| `Cond(cause=If[A], consequence=Committed[B])` | A: `[If]`; **B: spaces `[If, Committed]`** (the fault as first found) |
| A bare `Causes(cause=A, result=B)` | **A: nothing; B: `#rootcontext: [A, B]`** |
| Any space | No spaces, no labels |

- A node is in its own label whenever a label was there before it (always inside a space); in a root context only
  from the second document on, since the first is given an empty list before the root label is made. So "the item
  itself" is sometimes there and sometimes not, which is why the interface takes it out by its id.
- **For 1.3**: every stored `context_labels` is replaced, not mended; `semantic_spaces` changes only for the two
  faulty shapes (a node after a single relation that holds a space), and for spaces nested in spaces, which get
  the spaces above them for the first time. The heads to mark as written are those where some node's
  `semantic_spaces` changes.
- **For 1.4**: what readers showed until now, per the table: a nested item's own page had bands for its siblings
  under single relations as if they held it (the cause of a `Causes` result, and also the *result* in the cause's
  bands when inside a space), and a faulty node an extra space's band.

## Phase 1: the fault in recording spaces

Rewritten 2026-11-25 ([the review](#the-review-of-2026-11-25-and-what-it-changed), R1 and R4): the fault is mended
by replacing what is recorded, not by a narrower rule for the lists.

**What is proposed for `context.py`** (the user asked for improvements; D13, D14 and D17 decided):

- **One value, the path**: `meta.path`, the nodes a node is nested in, from the head down to what holds it, each
  `{kind, type, id, field}`: `kind` is `document`, `space`, `reified`, `conjunction` or `embedded`; `field` is the
  relation of that node through which the next is held (so a view can say "the result of this `Causes`"). Every node
  on the way is in it, whatever its `use_in_semantic_space_label`; a space is in it with its id, and has a path of
  its own (today a space is given nothing). An entity's path is empty, as its lists are today.
- **Worked out with nothing shared**: a child's path is its parent's path and the parent. No list is passed down and
  added to, nothing is copied, the order of a class's fields no longer matters, and a node is never in its own
  context. The fault cannot be written.
- **`meta.semantic_spaces` stays**, as the types of the path's spaces in order: it is what Cypher filters by
  (`$spaces`, derived's blocked spaces), and is made from the path by one function.
- **`use_in_semantic_space_label` becomes a matter of display**: the interface leaves a class out of a trail by the
  export; storage no longer does.
- **`#rootcontext` and the nesting of `contents` go.**
- **A document in the context of what follows it** (0.1: the result of a `Causes` has its cause in its context) is
  today an effect of the sharing, by the order of the fields. The path does not have it. **Decide** (D13): dropped;
  or declared (`Conjunction.Meta` naming the field whose contents are the context of the others) and worked out by
  the view from the document it already has, not stored. Proposed: declared, when a page first needs it.
- **Decided** (D14, the user, 2026-11-25): `meta.context_labels` is removed where nothing requires it, and every
  reader moved to the path. How the interface shows the path is D17, below (decided the same day), so 1.2 moves the interface too and 1.3's
  migration removes the old value.
  (Derived's `context_labels` on a fact and a justification is another thing, a list of names, and stays.)

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **1.1 The path** | `propagate_context` rewritten as above, for an instance about to be written (`_InstanceContext`) and for stored nodes (the migrations' `StoredContext`), still one algorithm; `write_plan.py` writes `meta.path`; the reads give it (`read_query.py`, `list_query.py`, `read_incoming.py`, search's results); Neo4j keeps it as JSON, as it keeps `context_labels` (`properties.py`) | Pure, in `pangloss-models`: the shapes of the trial (two single slots each in a space; a single relation holding a space and then a list; a bare result after a cause in `Negative`; an order's space nested inside a cause; `Not[p]` against `Not[Service(parts=[p])]`, with the flag on and off; a space's own path); `semantic_spaces` equal to the path's spaces. Conformance: written and read back, on create and on update, on both backends | Main ★ | **Done** 2026-11-25 ([as built](#11-as-built-2026-11-25)) |
| **1.2 The readers moved** | By D14: the interface's `api/context.ts` (`wrappingSpaces`, `contextPath`, `contextTrail` from the path: the item itself no longer has to be taken out), `Item.tsx`, `List.tsx`, `ItemContents.tsx`; the library's `identity.ts` and `clusters.py`; derived's `DerivedSection.tsx`; history's view; `pangloss-vectors`' `views.py`; label templates' skip list; `interface-core`'s types and the export | Each package's own tests; Vitest; the e2e files that show bands and trails, and `test_dev_mode.py` | `builder`, one brief for the Python readers and one for the interface; the second reading with the `solidjs-v2-reviewer` skill | **Done** 2026-11-25 ([as built](#12-as-built-2026-11-25)) |
| **1.3 Stored data, by a migration** | A migration of the package that owns the stored structure (where each backend's `0001_initial` is; named in the brief) gives every nested node its path and its `semantic_spaces` anew (`recompute_contexts`, moved to the path), removes `context_labels` by D14, and marks each head whose `semantic_spaces` changed as written (`pending.mark_written`), so derived, the vectors and criteria find its facts again. It reports, by class, the heads the fault had wrong, and the stored spaces of more than one item (for 2.3). `pangloss contexts check` stays, read only: the heads whose stored values differ from a recomputation. Measured once at size on a scratch database (642,000 nodes) before the brief names the batch | Live, both backends: a document written in the old shape (by hand, in the test); the migration mends it; `check` is clean; nothing else changes (edges, versions); a derived fact from the mended node is plain after the worker's turn; a server with the migration pending does not start | Main (the measurement), then `builder` ★ | **Not built** (D18, 2026-11-25): there is no stored data to mend. What 1.2 left for old data was removed instead ([as built](#13-as-built-2026-11-25)) |
| **1.4 Docs** | [semantic-spaces.md](semantic-spaces.md) rewritten for the path (what is recorded, and the rule); `models.md`, `migrations.md`, `guide/cli.md`, `status.md`; the item of `TODO.md` ticked; the skill where it speaks of the lists | The skill's check | `builder`, read by main | **Done** 2026-11-25: [semantic-spaces.md](semantic-spaces.md) rewritten with a worked example; every page that described the lists as current corrected (the reading of 1.2 had found far more than this row names); derived's own lists and dated records left; a dated line on the design pages |

### 1.1 as built (2026-11-25)

- **The algorithm** is `pangloss_models/context.py`: `propagate_context(head, view)` gives every node a list of
  its own, its parent's path and the parent; `spaces_of(path)` makes `semantic_spaces`. A view says `kind_of`,
  `type_of`, `id_of`, `children` (each with its field) and `assign`; whether a relation is single or a list is no
  longer asked. The two views are `_InstanceContext` (`model_bases/instance_context.py`) and the migrations'
  `StoredContext`.
- **A sixth kind, `entity`**: the head of what an entity holds (a reified relation on an entity's own field has
  the path `[{kind: "entity", ...}]`). An entity met inside a document starts an empty path, as before.
- **Embedded objects are followed** (they were not): an embedded object has a path, and is on the path of what it
  holds.
- **On an instance the field is `context_path`**, not `path` (a project's class may have a field `path`); it is a
  reserved name, as `context_labels` is. In `meta`, stored and read, it is `path`.
- **`context_labels` is still written in this step, made from the path** (`labels_of`): what a node is nested in,
  in the old shape, so the readers work until 1.2 moves them and 1.3 takes the value away. So already from 1.1 a
  node is not in its own label, a sibling is not shown as holding it (the cause of a `Causes` result is gone from
  its bands, by D13), and the two faulty shapes are right for what is written from now on.
- **A space in a space is in the outer one** (`Doubt[Negative[S]]`: the `Negative` node has
  `semantic_spaces == ["Doubt"]`); a space had nothing before. Search's `$spaces` and derived's blocked spaces read
  the statements, not the spaces, and their tests pass unchanged.
- **Neo4j**: `meta.path#json` (JSON text) and, flat beside it for a migration's rename, `meta.path_types`. A read
  query gives the path through `Dialect.meta_entry(node, "path")`, new, which names the entry so that it is read
  back as the list on either backend.
- **Migrations**: every operation that puts a node on a path, takes one off, or changes a name that is in paths now
  ends with `recompute_contexts` for the heads it touched: wrapping and unwrapping (a reified relation, a space),
  `change_wrapper`, `literals_to_embedded` (and so `add_embedded`), a renamed relation (the field is in the path of
  what it holds), a renamed class (found by `meta_mentions`, which now looks in the path: a renamed **head** class
  is in the path of everything nested in its documents, so all of those documents are worked out again; to be
  measured at size with 1.3). `StoredContext` reads a node's kind from its labels and takes an edge of no field of
  the snapshot as a field of its own name, so it does not depend on the snapshot being of before or after the
  change. `INSERTED_NODE_META` in both dialects gives a new node who and when only; its place comes from the
  recomputation.
- **Tests**: pure, `packages/pangloss-models/tests/test_context_path.py` (the algorithm on plain objects; the
  shapes of the trial on the models' instances). Conformance, `test_stored_path.py` (create, update, read back,
  listed and read alone), and a check after **every** conformance test that looks underneath
  (`conftest.paths_are_true`, `helpers.assert_paths_true`): whatever the test left, written by the models or by a
  migration, each nested node's path is its parent's path and its parent, by the edges alone. A test that writes by
  hand is marked `stored_by_hand` (1.3's will be).
- **Not in this step**: data stored before it has no `path` until 1.3's migration (a read gives `[]`); the
  interface and the packages still read `context_labels` (1.2).

**The interface's four uses of `contextLabels` today** (read 2026-11-25), for D17:

| Where | What it shows | From the path |
|---|---|---|
| A row of a list (`List.tsx`, `wrappingSpaces`) | The names of the spaces an item is in | `semanticSpaces` alone would do |
| An item's console (`Item.tsx`, `wrappingSpaces`) | The same, as its chips | The same |
| A nested document's own page (`Item.tsx`, `contextPath`, `ContextFrames`) | Bands round the whole item: each space, and each document it is nested in, linked | The path's spaces and documents, in order; what was a sibling shown as if it held the item is gone (and with it the cause of a `Causes` result, until D13's declaration is built) |
| A chip of a nested item (`ItemContents.tsx`, `contextTrail`, `SpaceBands`) | Bands round the chip | The same |

**Decided** (D17, the user, 2026-11-25): a reified relation, a conjunction or an embedded object on the path is
**passed over** in a trail, for now; the **field is said** ("the result of…"); a class with
`use_in_semantic_space_label=False` is **left out of a trail** by the export (the user is not sure what the option
was first meant for); and how a band shows what kind of space it is (each space has its own colour today; perhaps a
small icon) is **a later decision**, taken with 7.3. So the interface's part of 1.2 no longer waits.

### 1.2 as built (2026-11-25)

- **`context_labels` is gone from what is written and read**, not only from the readers (main's change, D14): the
  generated models and their metas have no such field, `ContextLabel` and `labels_of` are removed (`PathEntry` is
  exported from `pangloss_models` in its place), `write_plan.py` and the reads no longer give it, Neo4j no longer
  encodes it, and `recompute_contexts` takes the old value away from the nodes it rewrites. Left until 1.3's
  migration has run: the `context_labels` clauses of `meta_mentions` in both migration dialects and the `None`
  entries of Neo4j's `flat_meta`.
- **The name stays reserved and tolerated**: `context_labels` is still a reserved field name and still among the
  keys a payload may send back (`SERVER_KEYS`), because versions `pangloss-history` stored before the path hold it at
  every depth. History leaves it and `context_path` out of a version's view and diff, and takes the old key out of a
  draft made from an old version (`draft.without_retired`), so an old version restores.
- **The Python readers** were fewer than the plan's row said: `pangloss-vectors`' reference views (now the path,
  through `Dialect.meta_entry`) and history. The library's `clusters.py` and `identity.ts` read `semantic_spaces`
  already; derived's `DerivedSection.tsx` reads derived's own list, which stays.
- **The interface** (`api/context.ts`, each function pure and tested): `wrappingSpaces(meta)` is the meta's
  `semanticSpaces` (a list row, the console); `contextPath(path, definitions)` is the path after its head, the
  spaces and the documents only, a document of a class with `useInSemanticSpaceLabel` off left out, an unknown class
  kept; `contextTrail` its names (a chip's bands). `ContextFrames` chooses a band or a frame by the entry's `kind`.
  **The field is said** (D17): a document's frame names its field that holds what follows, between its head and
  what is inside, as a field is named on a page; beside "Contained in" the head's field is named the same way
  (`data-context-field`). Not said for a space, and not on a chip (main's call: no room).
- **What changed on screen**: the head is not in a chip's trail nor a frame of the nested page (it is the
  "Contained in" chip); a wrapper on the way is passed over, and the field said is then the document's own.
- **Tests**: every assertion on the old lists moved to exact path entries; new conformance tests that nothing
  written now has `context_labels` and that a recomputation takes an old one away; guards that `PathEntry` and the
  label templates' skip lists agree between Python and TypeScript; e2e for the field said on a nested page
  (`test_keys_and_nesting.py`, `test_fields_and_wrappers.py`, `test_dev_mode.py`).
- **Open, for 1.3**: data stored before 1.1 has no path, so until the migration its nested pages and chips show no
  bands (lists and the console still show its spaces); history will show `semantic_spaces` of nested nodes as changed
  between a version from before 1.1 and one after; `useInSemanticSpaceLabel` is still among the options whose change
  makes a migration (`migrations/diff.py`), though it is no longer data; search's results give no path (they are
  heads, whose path is empty); no test of the vectors' views looks at the path.
- **For 1.4**: many more pages speak of the lists than its row names (the reading listed 24 under
  `implementation_docs/`, among them `history.md`, `generated-models.md`, `neo4j-implementation.md`, `memgraph.md`,
  `interface-to-document.md`, `label-templates.md`, `sdk.md`; some are derived's own lists and stay).
  `guide/migrations/03-changes.md` and the root `README.md` were corrected here.

### 1.3 as built (2026-11-25)

Not a migration. The user decided (D18) that no stored data is carried over: the demo is reset, and rewritten when
the plan is done. So there is no migration of the path, no `pangloss contexts check`, no measuring at size, and the
report for 2.3 (stored spaces of more than one item) is not needed. Instead, what 1.2 had kept for data stored
before the path was taken out: the `context_labels` clauses of `meta_mentions` in both migration dialects, the
`None` entries of Neo4j's `flat_meta`, the filter in `recompute_contexts`, the reserved name and the tolerated key
(`RESERVED_FIELD_NAMES`, `SERVER_KEYS`), and history's handling of an old version's key (`RETIRED`). The open
points 1.2 listed for old data (no bands until a migration; history showing nested `semantic_spaces` as changed) go
with it. A database made before step 1.1 has to be made again.

Still open from 1.2: `useInSemanticSpaceLabel` among the options whose change makes a migration
(`migrations/diff.py`); no test of the vectors' views looks at the path; a renamed head class recomputes every
document of that class (not measured).

## Phase 2: the four fields in the core

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **2.1 The fields and `Modal`** | On `SemanticSpaceMeta` (`model_bases/semantic_space.py`): `veridical: Literal[1, 0, -1] \| None = None` (`None`: what `logical` implies, `-1` for `"not"`, else `0`; R6), `fit: Literal["describes", "prescribes"] = "describes"`, `logical: Literal["not"] \| Modal \| None = None`, `unary: bool \| None = None` (`None`: what `logical` implies, else `False`), inherited by the meta kit's default rule. `Modal(force, flavour, of_not=False)`, frozen: `force` `"necessity"` or `"possibility"`, `flavour` a non-empty word; exported from `pangloss_models` (`imports.md`). If D5 says so, a fifth field: the class's default degree for its contents (in the five steps of an `Expectation`), the strength of an order above a request. **Decide** (D2): `logical` as force and flavour | Pure: defaults; a family class sets values once, a subclass changes one and inherits the rest; `Modal`'s validation | Main | **Done** 2026-11-25 ([as built](#21-as-built-2026-11-25)) |
| **2.2 The checks at `initialise()`** | `initialise_models/check_semantic_spaces.py`, called where `check_label_templates` is (`model_registry.py`). Refused by the class's name, each a `PanglossModelError` with `fix=` (so the language server offers it): `"not"` with a `veridical` set to other than `-1`; a possibility with `veridical` other than `0`; `-1` on a modal that is not a necessity `of_not`; `1` on a necessity `of_not`; `unary=False` on `"not"` or a modal `of_not`. A warning for two flavours that differ only in case | Pure: every refusal by its message and its `fix` | `builder` from main's brief | **Done** 2026-11-25 ([as built](#22-as-built-2026-11-25)) |
| **2.3 `unary` enforced** | A unary space's `contents` gets a length of at most one in its field definition (`initialise_field_definitions.py`), so `Create` and `Update` refuse a second item with a message that says why, and the interface's handling of a length (no "Add" past the last) follows. Measured: every space of the demo holds one item | Pure: two refused, one taken, the message; the export says the length | `builder` | **Done** 2026-11-25 ([as built](#23-as-built-2026-11-25)) |
| **2.4 Exported, not migrated** | `export.py` gives a space's `veridical`, `fit`, `logical` (`{"not": true}` or `{"force", "flavour", "ofNot"}`) and `unary`; `interface-core/src/types/models.ts` has them; `make-stubs` knows `Modal`. The migrations' snapshot (`migrations/diff.py`, its list of keys) is left as it is: the fields are not data | Pure: the export; `packages/pangloss-interface/tests/test_models_match_typescript.py`; a change of `veridical` makes no migration | `builder` | **Done** 2026-11-25 ([as built](#24-as-built-2026-11-25)) |
| **2.5 `Holder()` and `Addressee()`** | Field markers (`markers.py`, `FieldMarker`) on a relation of a statement class: who holds the attitude or gives the order, and to whom; at most one of each on a class, on a relation to agents, found through a reified relation (a proxy) by the code search already uses to reach what is behind a wrapper (`pangloss_models.search`). Exported (on a relation a marker is kept on the field's definition today, not exported). **Needed by fulfilment (6.2)**; **decide** (D3) | Pure: the checks; the marked fields of a class read through wrappers; the export | `builder` | **Done** 2026-11-25, as one marker `Attribution(by=, to=)` on the field that holds the space ([as built](#25-as-built-2026-11-25)) |
| **2.6 Docs and the skill** | [semantic-spaces.md](semantic-spaces.md) (the fields, ✅), [models.md](models.md), `imports.md`, the guide's statements page (`guide/tutorial/04-statements.md`), `status.md`; the skill's `references/modelling.md` (a new `Meta` option is one a newcomer needs to be told), and `check_skill.py` | The skill's check | `builder`, read by main | **Done** 2026-11-25 ([as built](#26-as-built-2026-11-25)) |

### 2.1 as built (2026-11-25)

- The four fields as the row says, and by D5 a fifth, **`degree`**: `"impossible"`, `"unlikely"`, `"possible"`,
  `"likely"`, `"expected"` or `None` (the type `DegreeStep`, the tuple `DEGREE_STEPS`, in
  `model_bases/semantic_space.py`; main's name for it).
- **What is set and what follows are apart**: `veridical` and `unary` stay `None` where the class does not say, and
  two properties of the meta give what holds: `veridicality` (`-1` for a `"not"`, else `0`) and `is_unary` (true for
  a `"not"` and for a modal `of_not`). Readers use the properties. They give what is set even where it contradicts
  `logical`: refusing that is 2.2's.
- **`Modal`** is a frozen pydantic dataclass, so `Modal("necessity", "command")` is written by position, is checked,
  compares by value and can be a key. A flavour is one word with no space in it; flavours that differ in case are
  different (2.2 warns).
- Tests: `packages/pangloss-models/tests/test_semantic_space_fields.py`. The snapshot of the generated models gained
  the five fields in each space's meta, nothing else.

### 2.2 as built (2026-11-25)

- `initialise_models/check_semantic_spaces.py`, called after `check_label_templates`. It reads what is set
  (`veridical`, `unary`: `None` where the class says nothing), and refuses the five contradictions of the row, each
  a `PanglossModelError` that begins with the class's name.
- **A sixth refusal, not in the row**: `degree` on a space whose contents are asserted or denied (its `veridicality`
  is not `0`), as 2.1's field says and as 2.7 will refuse the marker.
- A possibility with `veridical=-1` gets the possibility's message, not the third check's.
- **A class is refused only for what it says itself.** A fault a class inherits whole (each value the fault is
  between equal to its nearest checked parent's) is reported of the parent alone; a subclass that sets one value
  against an inherited one is refused by its own name. A parametrisation (`Not[Person]`) is not checked: its generic
  class is.
- **The fixes** are new code, since every fix before these edited an annotation: three keys in `diagnostics.FIXES`
  (`space_veridical`, `space_unary`, `space_degree`) over one helper that edits a keyword of the class's own
  `_meta = ...Meta(...)`. A fix never changes `logical`: it leaves the other value out where the class would then
  inherit `None` or the right value ("Leave out"), else changes it in place ("Change to") or, where the value is
  inherited, writes it in ("Add"). A class with no `_meta` of its own gets no fix. The diagnostic is at `_meta`.
- **The warning** (`PanglossModelWarning`, at the `_meta` of the first class by name) names each flavour and the
  classes that set it; a subclass that inherits a flavour is not listed. It has no fix: which spelling is meant
  cannot be told.
- Tests: `tests/test_check_semantic_spaces.py` (49: each refusal by message and by the edit applied to source, each
  allowed case with warnings as errors, inheritance, the warning), two in `pangloss-cli`'s `test_check_command.py`
  (the diagnostic's place and its fix; the warning). Pure runs only: models 1584, cli 259, lsp 85.
- The docstring of `PanglossModelWarning` says the new kind of warning since 2.6. Not done: a `Meta(` whose bracket is on a later line than the name gets no fix where the fix would add the first
  argument or remove the only one (untested).

### 2.3 as built (2026-11-25)

- `limit_unary_contents` (now `limit_contents`, below; `initialise_field_definitions.py`, last before `check_declared_class`): a space class whose
  `is_unary` holds (set or inherited) gets `MaxLen(1)` among the validators of its `contents`, the slot a project's
  own `Annotated[..., MaxLen(n)]` uses. So every generated model has the length, a parametrisation and a concrete
  subclass included, and the export says `{"name": "MaxLen", "max_length": 1}` as for an annotated list.
- **The message**: pydantic's `max_length` takes no message of its own, so the written models (`Create`, `Update`,
  `CreateDB`, `UpdateDB`) also have a `before` validator of `contents` (`common.one_item_only`, `check_one_item`),
  which refuses first, with pydantic's error type `too_long`: "Not holds one item only (it is unary: of two items
  under a 'not', neither is denied by itself)" for a `"not"` or a modal `of_not`, "X holds one item only (it is
  declared unary=True)" where only `unary=True` says so. The class named is the declared one.
- A project's `MaxLen` of one or less is kept; a larger one becomes one. A `MinLen` of two or more on a unary space
  is refused at `initialise()` (a `PanglossModelError` at `contents`, no fix), where the field definitions are made,
  not in `check_semantic_spaces.py`.
- **The least is one, for every space** (the user, 2026-11-25, after this step: a space of nothing makes no sense;
  as first built an empty list was taken, since no `contents` had a least). The function is now `limit_contents`:
  `MinLen(1)` on every space's `contents` unless the class's own `MinLen` is one or more, exported as such; the
  written models' validator (`check_contents_length`) refuses none first, with "X holds nothing: a semantic space
  has at least one item" (`too_short`). The read models have it too: a stored empty space would not be read (D18).
  In the form (read, not run): a space is only ever made with its first item; its last item can still be removed,
  and Save then says "At least 1 needed" in the space. The whole suite and e2e were run for this.
- **No count of stored spaces** (the review's note on 2.3): by D18 there is no migration. The read models have the
  length too, as with any annotated `MaxLen`: a stored unary space of two items would not be read.
- **The interface was not changed and not run**: by reading, `RelationEditor`'s `canAdd` (`ModelFields.tsx`) and
  the client's check (`schema/validation.ts`) take the length from the exported validators, and a space's
  `contents` goes through them. No browser test until a model of the e2e project is unary (9.1 or 2.6).
- Tests: `tests/test_space_contents_length.py` (18, once `tests/test_unary_spaces.py`). Pure runs only: models 1598, cli 259, lsp 85, interface 198, api 202,
  sdk 144, cypher 60.
- Not done: a `contents` that is not a relation is passed over (none can be declared today, as far as was looked);
  where the language server puts the `MinLen` refusal on a class that inherits `contents` is untested.

### 2.4 as built (2026-11-25)

- **The export** (`export.export_space`, `export_logical`): on a semantic space only, `veridical` and `unary` **as
  they hold** (`veridicality`, `is_unary`: never null, so the interface need not know what `logical` implies), `fit`,
  `logical` (null, `{"not": true}` or `{"force", "flavour", "ofNot"}`) and, with D5, `degree` (a step or null). A
  parametrisation and a subclass give their class's values.
- **TypeScript** (`types/models.ts`): optional keys of `ModelDefinition`, which is one type for every kind, with the
  types `Veridical`, `SpaceFit`, `DegreeStep`, `SpaceLogical` (`SpaceNot | SpaceModal`). `SpaceModal` and not
  `Modal`: the primitives have a dialog of that name. Types only; no code of the interface reads them yet, and the
  diff had no second reading for that reason. The guard (`test_models_match_typescript.py`) holds the keys, the
  literal types and each exported space's values to them.
- **Not data, but not as the row said**: `migrations/diff.py` is as it was, yet the snapshot is made from the export
  and so had the keys, which changed its hash. `migrations/snapshot.py` leaves them out in `data_view` (`SPACE_KEYS`),
  from a model of kind `SemanticSpace` only, not at every depth as `NOT_DATA_KEYS` are: a `TypedDict` may have a
  field `degree`. A change of any of the five makes no operation and the same hash (`test_migration_diff.py`, 8
  cases).
- **Stubs**: nothing to change. A project's stub keeps its imports and the `_meta = ...` line, and they are checked
  against `pangloss_models` itself; `tests/typestubs/test_space_meta_stubs.py` proves it with `ty`.
- Tests: `tests/test_space_export.py`, and those above.
- Open: `ty` does not refuse `logical="nope"` or `unary="yes"` on `SemanticSpace.Meta` (the runtime does). A
  `TypedDict` field named as one of `NOT_DATA_KEYS` (`default`, `required`, `description`...) is left out of the
  migrations' view, and was before this step: not looked into further.

### 2.5 as built (2026-11-25)

Not as the row says: by the user's change to D3, one marker on the field that holds the space.

- **`Attribution(by=..., to=...)`** (`markers.py`, exported from `pangloss_models`; frozen, keyword-only):
  `thing_ordered: Annotated[Ordered[Statement], Attribution(by="ordered_by", to="ordered_to")]`. `by` is the field
  that says whose attitude or act the space is, `to` the field that says whom it is addressed to; either may be left
  out, not both. Readers in `pangloss_models.markers`: `attribution_of(definition)`, `attributions(model)` (inherited
  fields included).
- **The checks** (`initialise_models/check_attributions.py`, after `check_semantic_spaces`; each at the field, a
  misspelt name underlined with a did-you-mean fix): one marker on a field; a name given; the marked field a relation
  with a semantic space among its top-level options (a space only inside a reified relation does not count); each
  named field another field of the class, a relation that reaches an entity, directly or behind wrappers as search
  reaches them (`search.leaf_classes`); a field that reaches entities and documents is taken, one that reaches only
  documents refused. `by` and `to` may be one field; several fields may each have a marker. A subclass in which a
  named field no longer reaches an entity is refused by its own name. No notion of an agent: any entity.
- The marker was already kept on a relation's definition in every shape (single, list, union, optional). An embedded
  field's definition drops it, so the checks read the annotation and refuse it there.
- **Exported** as the field's `attribution`: `{"by": {name, key} | null, "to": ...}`, absent without one, and not
  among the field's `markers` (which relations do export, against what the row and the old docstring said).
  `types/models.ts`: `attribution?: FieldAttribution` on `RelationField`. Types only; no second reading.
- **Not data**: `migrations/snapshot.py` leaves `attribution` out of a field's entry (`FIELD_KEYS`); a change makes
  no operation and the same hash.
- Tests: `tests/test_attribution.py` (17), `tests/typestubs/test_attribution_stubs.py`, one each in the migration
  diff's, the guard's and `pangloss-cli`'s check command's. Pure runs only.
- Open: a named field that is a type variable of a generic class is refused (untested). Nothing reads the marker yet:
  6.2 does.

### 2.6 as built (2026-11-25)

- **[semantic-spaces.md](semantic-spaces.md)** has the section "What a space says of its contents": the five options
  and what holds when one is left out, a worked example (`Negative`, `Hypothetical`, `Ordered`, and `Forbidden` below
  it), the refusals as a table with their messages, how many items a space holds (never empty; a unary one exactly
  one; several in another read each by itself, never together), `Attribution`, the export, that none of it is data,
  and what is not built yet.
- A short account with a link in `models.md`; a line or a row each in `generated-models.md`, `migrations.md`,
  `language-server.md` (the three fixes), `modelling-dx.md`, `interface.md` (the export's keys: the page that lists
  them, not the two the row names); `status.md` has phase 2 as 🚧 until 2.7. `imports.md` already had `Modal` and
  `Attribution`.
- Dated lines on the design pages where they differ from what was built (`semantic-space-fields.md`,
  `semantic-spaces-formalisation.md`, `semantic-spaces-summary.md`).
- **The guide** (`guide/tutorial/04-statements.md`): its `Negative` has `logical="not"`, with a short passage on a
  space never being empty, what the "not" buys, and one modal as an aside.
- **The skill**: `references/modelling.md` (the options, the properties to read, the refusals, the reading of
  several items, `Attribution`). `SKILL.md` and `check_skill.py` unchanged: no numbered fact became untrue.
- Every example of the main page and the guide was run through `initialise()` from the Markdown, and each message
  quoted was copied from a run. What the fixes do is described from the code, not from applying one.
- Noticed, not fixed: `imports.md` leaves `Computed` and `KeepOnMerge` out of its table of the root's names.

### 2.7 as built (2026-11-25)

Step 2.7 has no row in the table: it is the bullet "2.7 (new)" under "Other changes to steps". **Done** 2026-11-25.

- **`Degree()`** (`markers.py`; exported from `pangloss_models` with `DegreeStep` and `DEGREE_STEPS`) on a literal
  field of a space class that the project declares: `how_likely: Annotated[DegreeStep | None, Degree()] = None`. The
  field is stored and versioned as any field of the space.
- **In the path** (main): `PathEntry` has an optional `degree`, in a space's entry only and only where one was
  entered. `ContextView.degree_of`; the models read the marked field of the instance about to be written. **The
  class's default (`Meta(degree=...)`) is not written into the path**: a reader takes it where the entry has none
  (3.1). An update that changes or clears the degree changes the entries, as any write does.
- **A migration that works the paths out again keeps it**, from the paths stored before
  (`recompute_contexts`): a migration's state does not say which field is marked, markers not being data. For the
  same reason putting the marker on a field that has values, or taking it off, makes no migration and leaves the
  stored paths as they were until each document is written again (D18: nothing is carried over).
- **The checks** (`initialise_models/check_degree_fields.py`, after `check_attributions`; no fixes): on a class
  that is not a space; more than one on a class, inherited fields counted; a type that is not `DegreeStep` or
  `DegreeStep | None`; on a space whose contents are asserted or denied. A fault the parent has too is the parent's;
  a subclass that makes one is refused by its own name, at the field if it declares it, else at its `_meta`.
- **Exported** as any literal field's marker (`markers: [{"name": "Degree"}]`); `api/types.ts`: `PathEntry` has
  `degree?: DegreeStep`. Types only; no second reading.
- **Not built: the form beside the space's head.** By reading, the form draws the field as a named row below the
  space's contents (`ModelFields.tsx`), and the item page shows no field of a space but its contents
  (`ItemContents.tsx`). **Decided by the user (2026-11-25): with 7.3**, where the head of a space is drawn anew.
- Tests: `tests/test_degree_marker.py` (25) and additions to the path's, the migration diff's, history's and the
  guard's; conformance on both backends: four in `test_stored_path.py` (written, read back, a space in a space, an
  update that changes and one that clears, a search by `semantic_spaces`) and one in `test_migrations_context.py`
  (a recompute keeps it). The whole suite: Memgraph 2176, without a database 4676, `pangloss-neo4j` 176, Neo4j
  conformance 2070, e2e 359, all passed.
- Docs with the step: `semantic-spaces.md` (the entry's shape, a subsection for `Degree()`), `models.md`,
  `imports.md`, `status.md` (phase 2 ✅), the skill's `modelling.md` and `architecture.md`.
- To know: `typing` keeps one `Literal` for one set of values, so a class that writes the five steps in another
  order can change the order in which `DegreeStep` is exported elsewhere in the process; the type check takes any
  order.

## Phase 3: the walk

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **3.1 `pangloss_models.spaces`** | `signature(path) -> Signature` (rewritten 2026-11-25, R1 and R2): from a node's stored path (1.1), which says which of its nodes are spaces and which are statements between them; each run of spaces next to each other normalised ([the table](semantic-space-fields.md#logical): within one flavour; `of_not`; a double "not"); then [the walk](semantic-space-fields.md#veridical): `veridical`; for an uncommitted path its lean (for, against, neither) and the default degree of the class of its innermost space. **No statement's own degree**: a caller that has one (phase 8's hook) weighs with it; the walk reads no database; the `fit` of the innermost space that prescribes; the id of the statement holding it; the force and flavour of the innermost modal. Reads the classes' meta from the registry; no database | Pure: every row of the walk's table and of the normalising table; the two limits (two flavours never rewritten into each other; a statement between two spaces stops it); `Not[ChurchService(parts=[p])]`, which the flat list gets wrong. The cases are data (`space_cases.json`, beside the models' `label_cases.json`), which the TypeScript port (7.3) passes too | Main | **Done** 2026-11-25, [as built](#31-as-built-2026-11-25) |
| **3.2 Read from what is stored** | Where a package's query reads only `semantic_spaces`, it reads the path (`meta.path`) too: derived's `compile.py` (4.1), the library's clusters (4.3), the time part's rows (5.2) | Pure: the signature of a node read back (1.1's conformance write) | Main | **Done** 2026-11-25, [as built](#32-as-built-2026-11-25) |
| **3.3 Docs** | [semantic-spaces.md](semantic-spaces.md): `signature`, what it gives, with three examples | — | Main | **Done** 2026-11-25, [as built](#33-as-built-2026-11-25) |

**Worked out when read, never stored**: a change of a space's fields changes nothing stored and needs no migration.
What waits on that is search's `$asserted` (4.5).

### 3.1 as built (2026-11-25)

`packages/pangloss-models/src/pangloss_models/spaces.py`, exported as `pangloss_models.spaces`.

- **`signature(path, spaces=None) -> Signature`**: `veridical`, `lean` (`"for"`, `"against"`, `"neither"`, or `None`
  where the path commits), `degree`, `fit`, `prescribed_by`, `force`, `flavour`. `normalise(path, spaces)` gives the
  steps it walks. `spaces` is what each space class says, **in the export's shape** (`export_space`, and `abstract`),
  so that the walk needs nothing of the registry and the TypeScript port (7.3) has the same input;
  `registered_spaces()` makes it from the models, and is what `signature` calls where none is given (a caller with
  many nodes makes it once).
- **Normalising** is one pass with a "not" held in hand: a "not" toggles it; a modality met while it is held is put
  down as its dual, the "not" still held; a modality `of_not` toggles it after itself; anything else (a space that is
  no operator, a statement, the end) puts the "not" down first. So `Not[Forbidden[p]]` is `Permitted[p]`.
- **Settled by main, where the design page was silent**:
  - *Whether a dual commits.* The page says `Not[Might[p]]` is `-1` "where the project's `Must` commits". A dual is
    of no class, so: a possibility never; a necessity where the project has declared one of that flavour and every
    one it has declared commits (`veridical=1`, or `-1` on one `of_not`), abstract classes not counted. Two
    necessities of one flavour that disagree: not committed.
  - *The degree is that of the innermost space that leaves its contents neither* (its entry's, else its class's
    default), since a "not" inside an order can have none; an outer space's is never taken in its place
    (`Believed(possible)[Reported[p]]` has none); a dual has the degree of the space as written; none where the
    path commits or leans neither way. The plan's "its innermost space" is read so.
  - *A denial that is no "not"* (`veridical=-1`, no `logical`) turns the sign and is rewritten with nothing: two of
    them leave the node neither.
  - *Any node that is not a space is a statement* for both limits (a reified relation, a conjunction, an embedded
    object as a document).
  - *`fit`, `prescribed_by`, `force` and `flavour` are given whatever the sign*: of the innermost space that
    prescribes anywhere on the path, and of the innermost modality of the normalised path. `prescribed_by` is the
    nearest node outside that space that is not a space.
  - *A space class the models do not have* raises `UnknownSpaceError` (no fallback).
- **The cases** are written by hand in `tests/test_spaces_walk.py` (54, each with what the walk must give) and kept
  as `tests/space_cases.json` (`PANGLOSS_WRITE_SPACE_CASES=1` writes it), which a test runs again from the file
  alone, as the port will. One expectation of mine was wrong and the walk right (`Not[Might[Permitted[p]]]` is a
  necessity, "must be forbidden").
- Not done: no second reading (the row has no ★).

### 3.2 as built (2026-11-25)

- **The walk takes what is stored as it is**: `n.meta.path` of a row, or `meta.path` of a view. Conformance, on both
  backends, `test_stored_signature.py` (4): the signature of each of twelve nodes from the path a query reads and
  from a view; of a nested document read alone and listed; after an update that clears an entered degree (the
  class's default then).
- **The three queries are not changed here** (derived's `compile.py`, the clusters' `clusters.py`, the time part's
  rows): each still returns `semantic_spaces` only. Main's call: a path returned with nothing reading it could not
  be tested, and each is one more column in the step that makes its package follow the walk (4.1 (a), 4.3, 5.2),
  where its test is. Those rows say `context_labels`: read `meta.path`.

### 3.3 as built (2026-11-25)

[semantic-spaces.md](semantic-spaces.md#the-walk-what-a-path-says-of-a-node-): the section "The walk", with the
table of what a `Signature` has, the two steps, three examples and what follows from the options; `models.md`,
`imports.md`, `status.md` (and its stale "the degree's live tests have not been run" taken out), a dated line on
[the design page](semantic-space-fields.md#veridical), the skill's `modelling.md` and `architecture.md`.

## Phase 4: the packages that read spaces

Each step is one package, backend-neutral, with its own tests on both backends, and **each changes behaviour, so
each is decided by the user before it is built** (D4). A project that sets no field sees no change.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **4.1 Derived** | As [Derived edges through spaces](semantic-space-fields.md#derived-edges-through-spaces) says. (a) The rule's query reads the matched nodes' `context_labels` beside `semantic_spaces` (`compile.py`), and each justification gets its status from the walk over the node's path and the wrappers on the rule's own paths: asserted, denied, uncommitted leaning for or against, prescribed, or saying nothing. (b) The derivation follows the status (asserted: through; uncommitted or prescribed: qualified; denied, or leaning neither way: blocked) unless a wrapper's own `DerivedMeta` says otherwise. (c) The status kept on each justification and summed up on the fact (asserted, contested, **likely** (prescribed contents whose degree is above a setting: a fact from a royal order counts as a weighted fact, not only as a virtual edge), reported, prescribed, denied only), `plain` kept; in the views, the API's filters, `why`, `export`, `graph` and derived's RDF. (d) A rule option to take only justifications of a status, for virtual edge classes. (e) The degree (and, for a denial, the liveness) as a `PerJustification()` value (8.4) | Pure: the status of the walk's cases. Live, both backends: a rule over a purchase in a `1`, a `0` and a `-1` space; `Not[Not[...]]` plain and `Not[Known[...]]` nothing; a contested fact; `DerivedMeta` winning. On the demo's data (read, not applied): of its 34 `GaveTo` edges, the 3 from ordered gifts prescribed, the 1 from a forbidden gift blocked, the other 30 as they are | Main (a, b), `builder` (c to e) ★ | **Done** 2026-11-25 but for "likely" and (e), which are phase 8's: [a, b](#41-a-and-b-as-built-2026-11-25), [c, d](#41-c-and-d-as-built-and-the-second-reading-2026-11-25) |
| **4.2 Criteria's `$derived`** | Its filter of facts by their justifications' context labels follows 4.1's status: a description that asks for what is plain gets what is asserted; one may ask for a status | Live, both backends: a description over a contested fact and over a prescribed one | `builder` | **Waits** for criteria's step 13: [why](#42-not-built-2026-11-26) |
| **4.3 Identity claims** | A `SameEntity` whose path is `1` joins as if it were in no space; one whose path is `-1` is a claim that the two are different, given apart in the cluster ("said to be different"), not joining. `clusters.py` reads `context_labels` too; `identity.ts` shows it | Live, both backends: each case; a claim in a `0` space as today | `builder` | **Done** 2026-11-26, [as built](#43-as-built-2026-11-26) |
| **4.4 The RDF export** | What is inside a space whose path is `1` has its direct triples (today nothing inside any space does); `0` and `-1` as today. `convert.py` walks the tree itself, so it asks the walk of each node's path as it goes | The RDF package's tests: a `Known[...]` statement asserted; a `Not[...]` one not | `builder` | **Done** 2026-11-26, [as built](#44-as-built-2026-11-26) |
| **4.5 Search's `$asserted`** (outline) | A condition on a document's pattern: needs the value on the node (stored at write, and so a migration whenever a space's fields change) or a filter after the query (slow on large results). Not built until a page needs it | — | — | Later |

### 4.1 (a) and (b) as built (2026-11-25)

On the branch `spaces-4-readers`, made from `spaces-foundation` (not yet in `dev`). Main's part.

- **`pangloss_derived/status.py`** (new). A justification has **parts**: the node of each pattern, by its stored
  path; and each relation to an entity that passes through a space (`buyer: Person | Not[Person]`), by the path of
  the node it starts at, that node, and the spaces on the way (which then stands for that node: its path has the
  node's in it). `status_of` gives a part's status from the walk's `Signature`; `together` puts them together.
  Seven statuses: `asserted`, `reported`, `prescribed`, `denied`, `reported_not`, `prescribed_not`, `nothing`.
- **The derivation follows the status** (`store.Found.add`): a rule takes `asserted`, `reported` and `prescribed`
  (`status.DERIVES`, `CheckedRule.statuses`); the other four give no justification. So a forbidden gift (prescribed,
  leaning against) leaves the positive class, as a denial does. The status is kept in the justification's stored
  `context` (JSON, `"status"`); a property of its own and the fact's sum are (c).
- **A fact that is asserted is plain whatever spaces say so**: of an asserted justification, `context_labels` leaves
  out the spaces the walk read (`Known[p]`, `Not[Not[p]]`), and keeps what qualifies whatever the walk says (a
  wrapper that is no space, as the library's `WeightedAlternative`; a forced space). `qualified_only` is as it was.
- **A wrapper's own `DerivedMeta` wins** (`check.wrapper_settings`, which now gives three sets): `block` as before
  (the query); a space that is `transparent` is left out of the path; a space whose `DerivedMeta` says `qualify`, or
  that the rule allows (`allow=[...]`), is **forced**: read as a plain space that neither asserts nor denies, as
  every space was before the walk. A reified relation or a conjunction stays in the path as a statement, whatever
  its derivation (`Not[Causes(cause=A, ...)]` says nothing of A).
- **A rule that derives a document** blocks, as before, a plain space it does not allow; a space that says something
  of its contents is left to the walk, and the rule takes a justification that is not asserted only where every
  space it passed through (but those that assert) is one it allows.
- **The query** (`compile.py`) returns two more columns: `walks`, the id and stored path of each node of the rule
  that is not an entity, and `ways`, the type and id of each wrapper of each relation. (This is 3.2's column for
  derived.)
- **The rule's hash** has what the walk reads of every space class and the rule's statuses, so a change of a space's
  `Meta` makes the rule's facts due again. Every rule's hash changes once with this step.
- **Settled by main**: the seven statuses and `together` (several parts not asserted: all leaning for, reported, or
  prescribed if one is; otherwise nothing, so two parts each denied say nothing); leaning against is blocked as a
  denial is; the degree is not read (a relation's spaces have none in the query; "likely" is phase 8's).
- **A project that sets no option sees no change** but the new hash: a plain space gives `reported`, qualified as
  before. Checked by derived's whole suite, unchanged but for five hand-made rows given the two columns.
- Tests: pure `tests/test_derived_status.py` (27); live on both backends `tests/live/test_derived_status_live.py`
  (5: asserted through `Known`, `Not[Not]` and a known service; reported and ordered; denied, reported not,
  forbidden, not known and a part of no service deriving nothing; a space on the relation; `DerivedMeta` winning).
  Green: derived 273 pure and 158 live on Memgraph; criteria, library and RDF on Memgraph; derived, criteria and RDF
  live on Neo4j (418).

### 4.1 (c) and (d) as built, and the second reading (2026-11-25)

`builder` from main's brief; then a second reading (★) of the whole step, whose findings main mended. "Likely" and
(e) are not built: phase 8.

- **(d) `.when(..., status=[...])`** on a rule of edges and of documents: the statuses it takes (left out:
  asserted, reported, prescribed). Refused at `initialise()`: a name that is no status (with the nearest), an empty
  list, a bare string. For virtual edge classes: `DidNotBuyFrom` with `status=["denied"]`. `DerivesEdge`
  declarations have no such option, as they have no `block` or `allow`.
- **(c) Kept and summed**: `status` is a property of each justification (and still in its `context`); a fact has
  `statuses` (the distinct ones, in the order of `STATUSES`) and `status`, one of `status.SUMMED`: `asserted`,
  `contested` (one asserts and one speaks against: denied, reported not, forbidden), `reported`, `prescribed`,
  `denied` (every one speaks against), `nothing`. `status.summed` in Python and the same in `SUMMARY_QUERY`, compared
  by a live test. `plain`, `qualified_only` and `context_labels` are as they were.
- **(c) The readers**: the fact's and the justification's views; `Where(status=...)` and the API's `?status=`
  (the summed names; anything else a 422); `why`'s route (there is no `why` command); the graph (JSON, a CSV
  column before `weight`, GraphML `e_status`) and the export, which sum over the justifications the reader sees, as
  their `plain` does; RDF `pgo:derivedStatus` on a fact that is not plain or not asserted (direct triples as
  before: plain facts only); the interface's Derived section, a mark for what is not simply asserted, and one on
  each justification under "Why" (Vitest only: the e2e project has no space with options).
- **Mended by main before the second reading**: a rule of documents that names its statuses takes them through
  any space it does not block (it required the space to be allowed, and an allowed space is read as plain, so
  `status=["denied"]` took nothing). `allow=[Not]` with `status=["denied"]` on a rule of edges takes nothing from a
  `Not`: said in `derived.md`, not refused.
- **Found by the second reading in (a) and (b), and mended** (`status.parts_of`):
  1. A pattern nested in another (`Order.Where(content=Gift.Where(...))`) was no part: a gift in a `Not` gave a
     plain fact, and one in a plain space lost its label, so a project with no options did see a change. Every node
     of the rule that is not an entity is now a part, by its own path.
  2. The spaces of a relation that starts at an entity were not read. Such a relation is its wrappers alone.
  3. A wrapper that is no space was dropped from a relation's way, so two "not"s either side of one cancelled. It
     is kept as a statement, as in a stored path.
  4. `Not[Purchase(buyer=Known[x])]` gave nothing. A relation whose wrappers, read alone, assert is no part: the
     statement's own path decides.
- **Found and left, to know**:
  - a database derived at 5c989a10 is not mended by `derive rebuild` (its justifications have the status in their
    context already, so they are not written again): derive it afresh (D18; only test databases were);
  - where two rows of a query are one justification, the first decides its context, and now its status too (as
    before this step);
  - a fact's stored `status`, and so `?status=`, counts justifications a reader may not see, as `plain` does;
  - a stored path that names a space class no longer among the models raises in the worker (`UnknownSpaceError`).
- Tests: pure 303 in derived; live `test_derived_status_live.py` (7, with the nested pattern and the relation from
  an entity) and `test_derived_status_readers_live.py` (4). The whole of `./run_tests.sh`: without a database 4788,
  `pangloss-neo4j` 176, Memgraph 2188 (and one criteria test of concurrent writers that failed under load and
  passed alone), e2e 359; after the last mends, derived, criteria and RDF again on Memgraph (558 pure, 424 live) and
  on Neo4j (424), and the derived module's Vitest and typecheck.

### 4.2 not built (2026-11-26)

There is nothing to change yet. A stored description refuses `$derived` (`pangloss_criteria.pattern`,
`REFUSED["$derived"]`): reading derived facts from criteria is step 13 of
[matches-criteria.md](matches-criteria.md), which is not built. When it is, it reads a fact's `status` (4.1 (c):
`Where(status=...)`, the summed names) from the start, and this row is its test: a description over a contested fact
and over a prescribed one. Nothing of this plan waits for it.

### The walk mended: a space says something of its `contents` only (2026-11-26)

Found by the second reading of 4.3 and 4.4, in the walk itself (3.1), and mended by main with them.

- A space was read as a space whatever field of it the path went through. So what a space holds in a field of its
  own (who reported it, when: `Reported(reported_at=d, contents=[p])`) was read as uncommitted or denied with its
  contents, and in the RDF export an embedded object of a space lost its direct triples and its CRM type.
- `pangloss_models.spaces.holds_as_space(entry)`: an entry is a space holding its contents where its kind is a space
  and its field is `contents` (`CONTENTS`). Otherwise the space is a statement like any other node: it asserts what
  it holds there, it ends a run of spaces (a "not" outside it does not pass), and as a statement it is the holder of
  a prescribing space further in (`prescribed_by`).
- Three cases more in `tests/space_cases.json` (57), "what a space holds in a field of its own"; the test's shorthand
  takes `Type.field`. The interface's port of the walk (7.x) has to pass them.
- Stored paths do not change: the entry's `field` was there since 1.1. Derived's relation parts build their ways
  with `field="contents"`, which is right for a wrapper on a relation.

### 4.3 as built (2026-11-26)

`builder` from main's brief; a second reading (with the `solidjs-v2-reviewer` skill for the interface's part), whose
findings main mended.

- **`pangloss_library/clusters.py`**: the claims' query returns each claim's stored path beside its spaces (3.2's
  column for the library), and the walk says what the path says of the claim (`registered_spaces()` once for a
  reader). `1`: it joins, as a claim in no space does (`Known[SameEntity]`, `Not[Not[SameEntity]]`). `-1`: a claim
  that the two are **different**; it joins nothing, and between two members of the cluster it is given apart, in
  `Cluster.said_different` (`saidDifferent` in the API). `0`: as before, `in_spaces`. A project that sets no option
  sees no change: a plain space is `0`.
- **The interface** (`identity.ts`, `IdentityCluster.tsx`, `ui.jsonc`): a row "said to be different" in the cluster,
  each claim a `ReferenceChip` of its document, as the claims in spaces are.
- **Mended by main after the second reading**: a claim stored with spaces and no space in its path (a database
  written before 1.1) would have been read as asserted and joined what the source did not. It raises, saying that
  the database has to be made again (D18: no old shape is tolerated, and none is read wrongly).
- **Found and left, to know**:
  - a path that names a space class no longer among the models raises `UnknownSpaceError`, which fails the cluster's
    page and a search with `$same_as` over that entity (as the derived worker does, 4.1);
  - the interface's own reading of a document being edited (`identity.ts`: `claimsHeld`, `claimDirect`, `grouped`,
    `contested`, `byContext`) still treats any claim in a space as not joining: it has no walk until the port of
    7.3, and is mended there;
  - no browser test of the "said to be different" row: the e2e project has no space with options (Vitest only);
  - `stored_path` (a list, or JSON text on Neo4j) is written twice, here and in derived's `status.py`.
- Tests: the conformance suite's `test_identity_clusters.py` on both backends (21: a claim in `Known`, in
  `Not[Not]`, in `Not`, in a plain space); the library module's Vitest and typecheck.

### 4.4 as built (2026-11-26)

`builder` from main's brief; the same second reading; main's mends.

- **`pangloss_rdf/context.py`**: a `Context` has the node's `path` (as the converter has walked it, in the shape of
  a stored path) and `known`, what each space class says (made once a conversion). `asserted` is the walk's: in no
  space, or `signature(path).veridical == 1`. A context made by hand with spaces and no path is not asserted.
- **`convert.py`**: `_held` makes the context of what a node holds in a field, for a relation and now for an
  embedded object too (which had the holder's context). So what is inside `Known[...]` or `Not[Not[...]]` has its
  direct triples; what is inside a `0` or a `-1` space has none, as before.
- **Mended by main after the second reading**: what a space holds in a field of its own is not inside it (the
  walk's mend, above; in `_held` the space's IRI is not among its `spaces`).
- **Found and left, to know**:
  - a property of an outside vocabulary on a relation that goes through an asserting space to an entity is not
    emitted (the relation's own triple is the space's): said in `rdf.md`;
  - `registered_spaces()` runs once for each item of a dump, not once for the dump: not measured;
  - no test of an embedded object on a space itself (the walk's cases cover the path).
- Tests: `tests/test_rdf_converters.py` (pure, 132 in the package) and `tests/live/test_rdf_walk_live.py` (new, 6)
  on both backends (47 live each).

## Phase 5: the vector parts

Changes to parts that are built, under the similarity plan's discipline: each part keeps passing its suite
(`pangloss_testing.parts.PartSuite`), takes the fields into its signature (so a rebuild is due once), and is measured
on the planted world before a default is chosen.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **5.1 The planted world with spaces** | `planted.world(..., compared=True)` with `similar_models.declare(compared=True)`, made once for this phase and phase 6: phase 12's cases (a once-per class; a general and a specific class; other reports that disagree; `Negative` reports; `Hypothetical`; the series kept) and these: reports in `Reported` and `Believed` leaning each way; "cannot have been" (`Not[Might[...]]`); orders carried out on time and late, not carried out, orders not to kept and broken; permissions used; two normative orders; absences that were expected (members of a group missing from its events) and absences that were not; a source contradicting itself in one factoid; an order and what came of it in one passage; one event entered twice in a factoid. The truth (`world.verdicts`) has the relation of each pair, and the liveness of each negative | Pure: the same seed, the same world; each kind of pair present in a share near the one asked; the truth holds for a handful read by hand | Main | **Done** 2026-11-26, [as built](#51-as-built-2026-11-26) |
| **5.2 The time part** | A date counts for nothing when its statement's path is `-1`, and a date of prescribed contents counts at their degree (the date of what a king ordered helps date the act); **decide** (D4) whether an uncommitted date with no degree counts, which changes every project with statements in spaces (and answers the open item of the similarity plan's step 9.3). `counts_for` (`pangloss_dates_vectors/part.py`) reads `context_labels` | Pure (`counts_for`); the part's suite (`dated=True`); a statement in `Not` has no time vector | `builder` | **Done** 2026-11-26, the denial only ([as built](#52-as-built-2026-11-26)) |
| **5.3 The graph part's `stop` and weights** | From 0.2: if a negated statement is still joined to its people, what `stop` should do (end the statement's own joins too, or an option of its own); whether a space with no `FastRPMeta` takes a weight from the walk: the degree (asserted 1, a royal order's contents likely, a stranger's hardly at all, denied: what `stop` decides). Measured on 5.1's world, against the same world without spaces: who comes out alike | Pure (the maps, the joins); the part's suite; the measurement written into the step | Main measures, `builder` builds | **Measured** 2026-11-26 ([the figures](#53-measured-2026-11-26-waiting-for-the-user)); the user to decide |
| **5.4 The actual network** | A second graph part in which a node joins at its degree (the walk in the graph's reader): asserted in full, a prescription's contents at their degree, a denied or a vacuous one not at all, beside the structural one (virtual relations weighed: 5.3, 8.4); profiles `who_met` and `who_belonged`. Measured: a second rebuild's and refresh's cost on both backends; how the nearest neighbours differ on 5.1's world | The part's suite for the second part; the measurement | Main measures, `builder` builds | **Done** 2026-11-27, `who_met` alone ([measured](#54-measured-2026-11-26-waiting-for-the-user), [as built](#54-as-built-2026-11-27)) |
| **5.5 Reconciliation's network** | `RECONCILE_PROFILE` stays a profile of the structural network (for "who is this?", co-mention in a denial is good evidence of the same world); said in `reconcile.md` and checked at `initialise()` if the actual part is installed (a warning when the profile weighs only it). A claim that two are different (4.3) as a reason against a candidate: later | Pure: the warning | `builder` | **Done** 2026-11-27 ([as built](#55-as-built-2026-11-27)) |

### 5.1 as built (2026-11-26)

`pangloss_testing.planted.world(compared=True)` on `pangloss_testing.similar_models.declare(compared=True)`; the
module docstrings of the two have the whole of it. Tests: `packages/pangloss-testing/tests/test_planted_compared.py`
(13, no database).

- **The models** (`compared=True`, which is dated too): `Birth` (once for each person), `Making` and
  `MakingOfPicture` (`picture_made` narrows `made`; entities `Thing`, `Picture`), `Attendance` (a person at a group's
  assembly), `Order` (`thing_ordered: Ordered | Permitted`, with `Forbidden` below `Ordered`;
  `Attribution(by="ordered_by", to="ordered_to")`), `Rule` (a group's statute: `ruled: Obliged`, flavour `"statute"`,
  attributed to the group), the spaces `Hypothetical` (a possibility, with a `Degree()` field `how_likely`), `Must`
  (an epistemic necessity that commits), `Reported` (degree `"likely"`) and `Believed` (`"possible"`), and
  `Factoid.statements` taking them, with `Negative[Hypothetical[...]]`, `Reported[Negative[...]]` and
  `Believed[Negative[...]]`.
- **The world**: the dated world unchanged, and after it, for each family, each case of `planted.COMPARED` with the
  chance the table gives (28 cases of pairs, and two of absences for each group's assembly). At 300 people: 250
  factoids more (944 to 1,194), 348 statements, 123 pairs; at 32,000 people: 29,429 factoids more, 41,296 statements,
  14,945 pairs, 6,205 statements said not to be so.
- **The truth**: `world.told` (each added statement by its label, which no other statement has: its factoid, case,
  event, spaces, and the order that prescribes it), `world.verdicts` (each pair: one of the fifteen
  `planted.RELATIONS`, the fields disagreed on or the targets missed, `same_factoid`, `same_source`),
  `world.liveness` (each statement in a `Negative`: 1 or 0, and its grounds), `world.relation(a, b)` (a pair the
  truth does not have is of two events) and `world.statement(label)`.
- **Read by hand, and by the walk**: seven pairs and three absences were read from their payloads; and a test gives
  every added statement the path it would be stored with, asks `spaces.signature`, and holds each pair's two
  signatures against its relation by [the table](semantic-space-fields.md#contents-find-spaces-decide). It passed as
  first written, "it cannot have been" (`Negative[Hypothetical[p]]`) a contradiction included. Every record of the
  world is also made a `Create` of the declared models.

**Where it differs from the row, and main's calls** (the user may overrule each):

- **`Negative` of `similar_models` is a "not" with or without `compared`** (it had no options, so its contents
  counted as neither asserted nor denied: a trap for 5.2 to 5.4). It is therefore unary; every test that declares
  these models was run again (the result is in "Where the work stands").
- **A source**: `Source`, and `Factoid.source` on the added factoids (the earlier ones have none), since "the same
  source" is a feature of the verdict (6.2). Two factoids of a pair are of one source one time in five.
- **A statement is known by its label** (`... [c17]`): a nested statement has no id before it is written, and after
  a write the label finds it.
- **`Hypothetical` is compared** ("might have" beside an assertion is support), where phase 12 left it out.
- **`Must` is declared and nothing is planted in it**: it is there so that this project's "cannot have been" is a
  denial.
- **Not planted** (rows of the relation table that 6.2 tests by cases written by hand): "done, but not carried out",
  a conflict within one flavour and authority, "reportedly carried out", a pair one of which leans neither way.
  Liveness is 1 or 0 only, with nothing between (a relative of a member): phase 8 may want it.
- **A date disagreed on**: of a birth, 400 to 2,000 days apart (one event all the same, being once for a person); of
  a gathering 2 to 20 days apart, both said to the day; the second gathering of the same people ("two") is 300 to 900
  days later. So a verdict cannot be right every time, as meant.
- **What is added is not in `world.events`** (the time part's truth, as it was).
- **`notes/similarity-evaluation/planted.py` does not write this world yet**: it gains `compared` with the first
  measurement that needs it at size (5.3).

### 5.2 as built (2026-11-26)

By D4, the denial only: a date counts for nothing, neither for what holds it nor for its head, when the walk says the
statement it is a date of is denied; a date in what is neither asserted nor denied counts in full, whatever its lean
or degree. **The degree of what is prescribed is not weighed**: that waits for the third part, with phase 8.
[dates-vectors.md](dates-vectors.md#whose-vector-a-date-is) has the rule.

- **Whose path is walked** (the brief was wrong here, and the `builder` found it): not the date's own path whole,
  which has the statement after the "not", so that the walk reads the date as neither. The statement a date is of is
  the last entry of the date's path that is not a wrapper, and the walk is over the entries before it. So
  `Negative[Activity(when=d)]` counts for nothing; `Negative[Service(parts=[p(when=d)])]` counts;
  `Negative[Hypothetical[p(when=d)]]` counts for nothing where the project's epistemic necessity commits; a date a
  space holds in a field of its own counts for nothing where the space itself is denied.
- **A date held by a wrapper follows the wrapper's statement** (main's call, after the `builder` had it count): the
  date of a role (`InRole.during`) in a gathering that is denied counts for nothing, as the gathering's own date.
- **Read with the date**: the rows return the date's `meta.path` (`Dialect.meta_property`, JSON text on Neo4j); an
  overlay takes it from the plan's `meta`. `registered_spaces()` is made once for a rebuild, a refresh, an overlay. A
  path that names a space the models do not have raises `UnknownSpaceError`.
- **The part's signature** takes in what the walk reads of each space class (`veridical`, `logical`, `abstract`), only
  where the models have a space: a project with none keeps the signature it had (no rebuild due); one with spaces has
  a rebuild due once, and again when a space's `veridical` or `logical` changes, or a space class comes or goes.
- **The demo**: its `Negative` has no `logical="not"`, so nothing of the demo is denied until 9.1 gives its spaces
  their fields.
- **Left**: `stored_path` (a path as a list, from a list or JSON text) is now written three times (derived's
  `status.py`, the library's `clusters.py`, here): one helper in `pangloss_models` would do.
- Tests: `tests/test_time_part.py` (the shapes above by name, the signature), `tests/live/test_time_part_live.py`
  (the part's suite, whose slow way now leaves denied dates out by the holder's path, read apart from the part's; a
  dated statement in a `Negative` after a rebuild, after an update that moves it there, in an overlay; one in
  `Reported`, in `Hypothetical`, and "it cannot have been").

### 5.3 measured (2026-11-26): waiting for the user

**Answered 2026-11-26: two networks, as recommended below.** Nothing of it is built yet (5.4).

`notes/similarity-evaluation/spaces_graph.py` (what it printed: `spaces_graph.txt`): no database; the planted world
for comparison (about 1,450 people, 5,800 factoids, 690 pairs; three seeds) made a graph in memory, the maps those
of the declared models, the vectors a whole rebuild by the pure maths (128 dimensions, steps `[0, 1, 1]`). Five ways
of joining a statement that is in a space:

| Way | What it does |
|---|---|
| through | Every space a plain wrapper: what is denied, ordered or reported joins as what is asserted (today, for a space with no `FastRPMeta`) |
| stop-not | `FastRPMeta(stop=True)` on `Negative`, as it is today: the chain from the factoid ends at the space, the statement inside keeps its joins (0.2) |
| cut-not | A denied statement (the walk: `-1`) joins nothing: left out of the graph |
| by-walk | As cut-not, and a statement neither asserted nor denied joins at a weight: its degree where it leans for (expected 0.8, likely 0.6, possible 0.4, none 0.5), 0 where it leans against or neither way |
| asserted | Only what is asserted: the network of what the sources say happened |

**How alike two entities come out** (mean cosine) that a planted case ties:

| The two | n | through | stop-not | cut-not | by-walk | asserted |
|---|---|---|---|---|---|---|
| Someone with no tie to a group, and the group whose assembly they are said not to have been at | 76 | 0.146 | 0.147 | 0.003 | 0.001 | 0.000 |
| A member said not to have been at the assembly, and the group | 256 | 0.275 | 0.279 | 0.189 | 0.188 | 0.189 |
| Who was ordered to give and who was to receive, the order not carried out | 96 | 0.412 | 0.425 | 0.317 | 0.294 | 0.161 |
| The same, forbidden and not done | 68 | 0.402 | 0.416 | 0.303 | 0.137 | 0.136 |
| The same, ordered and done on the day | 98 | 0.389 | 0.388 | 0.394 | 0.374 | 0.262 |
| The same, forbidden and done | 69 | 0.424 | 0.424 | 0.429 | 0.295 | 0.300 |
| Two people at random | 6,000 | 0.008 | 0.008 | 0.008 | 0.007 | 0.007 |

**Whether the other statement of a planted pair is among a statement's ten nearest statements** (what comparison's
pairs by vectors need, 6.4): with through and stop-not, 0.96 to 1.00 of every relation but "disagree" (0.89, the
same in every way). With cut-not **no pair that has a denial is found** (contradiction, not carried out, complied
with: the denied statement has no vector); with by-walk none that has a statement leaning against either (breach,
tension, two orders at odds); with asserted only the pairs of two assertions.

**The ten nearest people of a person that are also those of "asserted"**: through 0.807, stop-not 0.809, cut-not
0.833, by-walk 0.883.

**What it says.**

1. **`stop` as it is does nothing for who is alike** (0.146 against 0.147): someone said *not* to have been somewhere
   is tied to it a hundred times more than a stranger, and half as much as a member. It only keeps the denied
   statement from being near its factoid.
2. **Cutting the denied statement mends that, and loses the denial for comparison**: the pair most worth finding (a
   denial and what it denies) is found by vectors only while the denied statement keeps its joins.
3. **So one network cannot do both.** The structural network (finding statements, reconciling: who is this?) wants
   every statement joined, denied or not; the question "who met whom" wants what the walk says. This is the case for
   5.4's second graph part, and against changing the first.

**Main's recommendation, for the user to decide** (nothing is built):

- **The graph part as it is stays the structural network, unchanged**: no weight from the walk, and `stop` left
  meaning what it means. Its page says plainly what the figures show: `stop` does not keep a denied meeting from
  joining its people.
- **What the walk says goes into 5.4's actual network**, by the rule "by-walk" above (the weights a first guess, to
  be measured there): a denied statement joins nothing, a prescription's contents join at their degree, what leans
  against joins nothing.
- If the user would have one network only: cut-not for it, and comparison's pairs by vectors (6.4) are then by rule
  alone wherever a denial is one of the two.

### 5.4 measured (2026-11-26): waiting for the user

Nothing is built. `notes/similarity-evaluation/actual_network.py` holds a trial second part, `actual`, made of the
graph part's own pieces: its reader with each node's stored path read beside it, and a nested document whose path has
a space walked by the rule "by-walk" of 5.3 (asserted: joins as it does; denied, or leaning against or neither way:
out of the graph; leaning for: at the weight of its degree, 0.8, 0.6, 0.4, none 0.5). It was registered only in the
script's own processes, with a second profile `who_met` (actual 1, class 0.1) beside `default` (graph 1, class 0.1).
The world: `planted.world(compared=True)` at 32,000 people asked for (`planted.py --compared`): 126,122 factoids,
1,119,967 nodes, 2,495,018 edges, on a scratch Memgraph (`:7716`) and a scratch Neo4j (`:7717`), one run each, the
other database stopped. What it printed: `actual_network_memgraph.txt`, `actual_network_neo4j.txt`.

**A second rebuild** (seconds):

| | Memgraph | Neo4j |
|---|---|---|
| Today: the class part, the graph part, the profile `default` (326,877 vectors each) | 310 (16, 89, 205) | 161 (14, 56, 91) |
| The second part alone (319,315 vectors) | 105 | 58 |
| Of which: reading the graph with the paths; the walk; the maths; writing the vectors | 16; 0.5; 5; 80 | 11; 0.5; 4; 38 |
| Its profile `who_met` combined (326,972 vectors) | 206 | 90 |
| **Added in all** | **311** | **149** |

The graph part's own read is 12 s and 13 s, its maths 5 s: on both backends the time of a rebuild is the writing.
The walk is asked once for each shape of path (a path without its ids): 157,381 nested documents' paths read,
13,137 with a space in them, 13 shapes.

**A refresh**: one factoid of the world written again, then one turn of the vectors' worker; 20 plain factoids and
20 with a statement in a space, the same in both phases; the median, and in brackets the 90% figure, in seconds.

| | Memgraph | Neo4j |
|---|---|---|
| A turn today, plain | 6.1 (12.2) | 5.4 (12.6) |
| A turn with the second part, plain | 12.0 (25.0) | 11.0 (25.4) |
| A turn today, in a space | 9.0 (12.9) | 9.0 (12.1) |
| A turn with the second part, in a space | 18.0 (24.3) | 16.9 (24.6) |
| Of a turn with both, plain: the graph part's refresh; the second part's; the class part's; the rest | 5.2; 6.0; 0.14; 0.73 | 5.6; 5.1; 0.02; 0.22 |

A factoid of this world changes 167 vectors of the graph part at the median when plain and 354 when it has a
statement in a space (the second part: 166 and 338), which is why a turn is seconds here and was 1.2 s on the
demo's data (the similarity plan's step 5.3): the ratio carries over, not the seconds. No vector was left stale.
The write itself is the same with and without (15 to 45 ms). The trial runs the two refreshes one after the other,
each with its own reads; whether a built part can share the graph part's reading was not measured.

**How the nearest neighbours differ** (Memgraph's figures; Neo4j's are the same to within 0.005). How alike two
entities come out (mean cosine):

| The two | n | structural | actual |
|---|---|---|---|
| Someone with no tie to a group, and the group whose assembly they are said not to have been at | 666 | 0.145 | 0.001 |
| A member said not to have been at the assembly, and the group | 1,892 | 0.281 | 0.194 |
| Who was to give and who to receive, forbidden and not done | 511 | 0.398 | 0.128 |
| The same, forbidden and done | 538 | 0.399 | 0.269 |
| The same, ordered and not carried out | 642 | 0.395 | 0.268 |
| The same, ordered and done on the day | 675 | 0.399 | 0.385 |
| The same, ordered and done late | 652 | 0.399 | 0.386 |
| The same, a permission used | 566 | 0.397 | 0.344 |
| Two people at random | 2,000 | -0.001 | -0.001 |

In the actual network 36.4% of the attendances, 8.1% of the transfers and 5.8% of the activities have no vector
(7,657 statements out); every person and group has one. Of a person's ten nearest people, 0.811 are the same in both
networks, and the nearest one is the same for 0.892 of people; for the 15,773 people a statement in a space names,
0.760 and 0.838; for the other 16,364, 0.860 and 0.945.

**The weights** (`actual_network.py weights`, no database, 1,500 people, three seeds; `actual_network_weights.txt`):
the first guess, every statement that leans for at 1, the first guess halved, and a steep table (0.9, 0.5, 0.1).
Ordered and not carried out: 0.294, 0.322, 0.230, 0.310 (through 0.412, asserted 0.161). Ordered and done on the
day: 0.374, 0.396, 0.321, 0.387. The ten nearest shared with the structural network: 0.846, 0.857, 0.830, 0.837.
What is denied or forbidden comes out the same under every table: what moves the result is whether a statement
joins, not at what weight.

**What it says.**

1. **The second network doubles a rebuild and doubles a turn of the worker**, on both backends. The part costs what
   the graph part costs; each profile that weighs it costs what `default` costs, and that is the larger share.
2. **The walk costs nothing that shows** (0.5 s of a rebuild), and reading the paths little (4 s on Memgraph).
3. **It does what 5.3 said it would**: a stranger said not to have been somewhere is no longer tied to it, a member
   is tied by their membership alone, a prohibition kept ties no one.
4. **An order not carried out still ties giver and receiver** (0.268 against 0.161 by assertions alone): the
   contents of a prescription join at their degree whatever came of it. That is the rule as decided, and is said in
   the part's page when it is built.
5. **`who_belonged` cannot differ from `who_met` as profiles of one part**: a profile only weighs parts. Open.

**Main's recommendation, for the user to decide**: build 5.4 as measured, the first-guess weights kept; one
profile, `who_met`; `who_belonged` left until what sets it apart is settled; the reading shared with the graph part
in a refresh if that proves simple. 5.5 follows and needs no measurement.

**Answered 2026-11-27: build 5.4 as measured; `who_met` alone.** `who_belonged` is dropped from this step until
there is a case that says what sets it apart (it would be a network of memberships only, a third graph part): no
profile is added to any project, and `who_met` is the example in the guide.

### 5.4 as built (2026-11-27)

By `builder` from main's brief, read by main. In `pangloss-fastrp`, a second part, `"actual"`, registered beside
`"graph"` ([the page](fastrp.md)):

- **The rule is `walk.py`**, with no database in it: for every stop that is a document, nested or a head, the walk
  of its stored path gives a weight (asserted 1; denied, leaning against or neither way 0; leaning for the weight
  of its degree), asked once for each shape of path. Everything else weighs 1.
- **The weight is a field of the node** (`maths.Node.weight`, 1 by default), multiplied in where a stop's class
  weight is taken; a weight of 0 is out of the graph (`GraphMaps.is_in`). Not a class of its own for each weight,
  as the trial had it. The graph part's vectors are what they were (its tests pass unchanged).
- **The path is read in the node's own query**, one column more, only for the second part (`walk=`): the graph part
  reads no path.
- **One part's code for both**: `ActualPart` is `GraphPart` with `walked = True`; rebuild, refresh (with `before`,
  the groups past the cap, the approximate vectors), overlay and unknown are shared. An overlay reads the paths the
  write plan itself carries.
- **The setting `FASTRP_DEGREE_WEIGHTS`**, the first guess as its default, with `"none"` for no degree said; checked
  at `initialise()`.

Where it differs from the plan, and main's calls:

- **Idle unless a profile weighs it** (main's, not in the plan): a registered part is rebuilt and refreshed whether
  weighed or not, and this one doubles both. With no profile weighing `actual` it reads and writes nothing, and
  whether it is weighed is in its signature, so a rebuild is due when a profile first names it. A project that
  installs `pangloss-fastrp` and does not use it still sees a part `actual` with no vectors in the status.
- **No profile is added anywhere**: `who_met` (actual 1, class 0.1) is the guide's example, a name only (the
  network holds every class the graph part holds, not people alone); `who_belonged` is dropped (the user,
  2026-11-27).
- **A head is weighed too**, by the ground of its class (3.5): a class whose ground is 0 joins at its ground's
  degree. Entities are not weighed.
- **Out is a weight of 0, not "deleted"**: the neighbours of a statement an update moves into a "not" are found by
  what the head named before (`Changed.before`), as for a reference dropped.
- **Not built**: the reading shared between the two parts in a refresh; virtual relations weighed (8.4). **Not
  measured**: the built part at size (the figures in the docs are the trial's, which did the same reads).
- Left as found: `stored_path` (a path as a query gives it) is now written in four packages; one helper in
  `pangloss_models` would do (`TODO.md`).

Tests: pure 45 (`test_fastrp_actual.py`: the rule case by case, a refresh against a rebuild on weighted worlds,
the setting, idle, the signature), live 21 on both backends (`test_fastrp_actual_live.py`: the part's suite with a
slow way that walks path by path; a statement in a "not" has a `graph` vector and no `actual` one).

### 5.5 as built (2026-11-27)

By `builder` from main's brief, read by main; in `pangloss-reconcile` only ([the page](reconcile.md)).
`settings.check_network`, called where `RECONCILE_PROFILE` is checked at `initialise()`: a `PanglossModelWarning`,
not a refusal, when the profile candidates are found by (named, or chosen without the setting) weighs the part
`"actual"` above 0 and `"graph"` not. A profile that weighs both is not warned of; nothing when no part `"actual"`
is registered. The package still imports no part: the two names are strings. Pure tests (8 cases, one through a
real `initialise()`); the whole of `pangloss-reconcile` on Memgraph, 545, with no warning from any older test.

Found, and left as it is (main's call, for the user to overrule): **the choice of a profile without
`RECONCILE_PROFILE` counts `actual` as a part that can say what an unknown would be** (`ActualPart` inherits
`unknown`). So a profile of `actual` and `name` beside `default` is chosen by itself, and warned of; and a profile
that weighs `graph` and `actual` counts them as two parts, though they are one network weighed two ways. Not built:
a claim that two are different (4.3) as a reason against a candidate ("later", as the row says).

## Phase 6: `pangloss-compare`

Phase 12 of the similarity build plan, rewritten on the four fields: its user's answers hold, its calls b, c and g are
replaced (below), and its steps are these.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **6.1 The package and `CompareMeta`** | `pangloss-compare`, scaffolded as the testing list's item 10 says; its `tests/live` in `run_tests.sh`. `CompareMeta(identifying=[...], once_per=None \| "field", recurs=False)`, the slot `_compare_meta`, inherited; a class without `identifying` is not compared. On a space only `compared=False` (its statements left out): negation and the rest come from the four fields, so phase 12's `negates` goes. A weight for each space class (strength: an order more than a recommendation), unless D5 puts strength in the core. Checks at `initialise()` as phase 12's 12.2 has them (each field the class's; an identifying field reaches an entity, through wrappers, by the code search already uses (`held_field_names`, `wrappers_of`); `once_per` one of `identifying`; `once_per` and `recurs` not both; a narrowed field counts as the field it narrows, as the field definitions say) | Pure: every refusal by its message; inheritance; a narrowed field; an identifying field behind an `InRole` and behind an identification's alternatives; `compared=False` on a space | `builder` from main's brief, after 0.5 | **Done** ([as built](#61-as-built-2026-11-27)) |
| **6.2 The verdict, pure** | `maths.py`, no database. (a) The contents' verdict as phase 12's 12.3 has it: the nearest common class; field by field (same, different, one silent; dates overlapping, nested or apart beyond both uncertainties, from `Bounds`); one event by once-per, else a hand-set logistic of the date gap, the place, the people in common and different, `recurs`, sources differ, **the same factoid** and **the same source**. (b) The two signatures (3.1), and the relation by [the table](semantic-space-fields.md#how-it-works-with-similarity): agree or disagree, contradiction, support, tension, compatible or at odds, carried out (as prescribed, or otherwise), done but not carried out, not carried out, breach, complied with, permission used, reportedly carried out, conflict, two orders at odds, nothing. (c) Fulfilment's [own matching](semantic-space-fields.md#pairs-within-one-factoid-and-what-carries-out-an-order): the addressee (2.5) doing the prescribed thing after it was prescribed (`orientation`, D5), the prescribed details compared as targets (on time, late, early, elsewhere, in part). (d) A relation within one source says so. (e) The degree weighs the relation: an order with no other evidence still supports a later report that it happened; a failure to carry it out is the more notable, the higher the order's degree; once another statement tells what happened, it decides | Pure: phase 12's cases (a general and a specific class; once per; recurring; negated), each by name; every row of the relation table; Tuesday and Wednesday (carried out, a day late); a source contradicting itself; a seeded floor on 5.1's world (phase 12's trial gave 95 to 98% on "one event"; the floor a little under what is measured) | Main | **Done** ([as built](#62-as-built-2026-11-27)) |
| **6.3 Pairs by rule** | `pairs(statement)`, as phase 12's 12.4 without "in other factoids": the statement's identifying entities, **real entities only** (no stand-in, nothing below an unconfirmed suggestion; a merged entity followed to the one kept); statements of related classes naming one of them in the same identifying field, that the reader may see. Beside them, for a prescription, the statements that may answer it: the addressee's, of the prescribed class or below, after it. The query planned on both backends at size (`:7702`, `:7706`) before the brief names it | Live, both backends: each rule by name (a stand-in never pairs; a suggestion not confirmed never pairs, and does once confirmed); two statements of one factoid pair; an unpublished factoid and a reader not logged in; a merged entity; **nothing written** (nodes, edges, `PGPending` before and after); a cost budget in `test_query_costs.py` | Main, then `builder` ★ | **Done** ([as built](#63-as-built-2026-11-27)) |
| **6.4 Pairs by vectors** | As phase 12's 12.5 without "less those of the same factoid": `nearest(of=statement, types=related classes, k=COMPARE_NEAR_K)` above `COMPARE_NEAR` (measured), less those 6.3 has; never through a stand-in (main first measures on 5.1's world with `stand_in=True` whether stand-ins pull statements together). Through a profile of the **structural** network (D11): a pair by vectors says why ("one event if X and X′ are one person") and links to merging the two | Live: a pair found only by vectors; none by a stand-in; none without `pangloss-vectors`; the reader's visibility as 6.3; nothing written | Main (measure), then `builder` | **Done** ([as built](#64-as-built-2026-11-27); [the first figures](#64-measured-2026-11-27-waiting-for-the-user), [the entities](#64-the-entities-measured-2026-11-27-shown-to-the-user-before-building)) |
| **6.5 `EventJudgement` and the route** | `EventJudgement[T]` in `pangloss-compare`, named by the project with its own root (0.5): two citing fields with roles (R7: `statement: Cites[T]` and `other: Cites[T]`, the prescription first where one is; the names in the brief), not a list of two; `verdict`: agree, disagree, two events, carried out, carried out otherwise, not carried out, breach (**decide**, D7); `fields`: the fields disagreed on or the targets missed; `note`. `GET /api/compare/{type}/{ref}`: the pairs (6.3, 6.4), each with its relation (6.2), how it was found, and whether it is within one source; a person's judgement of a pair overrides (the newest wins, all listed with who and when; one on a statement changed since cited still overrides, with that notice). A judgement is written by the ordinary `POST` of its class, logged in; nothing else is written | Live, both backends: a judgement overrides; the newest wins; changed since cited; nothing written by a lookup, on the error paths too; the reader's visibility; a judgement the reader may not see does not show | `builder` ★ | **Done** ([as built](#65-as-built-2026-11-27)) |
| **6.6 Learning from judgements** | `pangloss compare learn` (`--dry-run`) and an admin job: each judgement is an example of "one event or two" (agree and disagree yes, two no) or of "does this answer that" (carried out, otherwise, not); its features worked out from the statements as they are now (a judgement on a statement changed since cited left out, and counted), among them the same factoid, the same source and the pair of signatures; `compare_calls` against the hand-set logistic; a `PGCompareModel` (one per fit, none deleted, one in use, the features' signature kept), written only past `COMPARE_LEARN_FROM` judgements (100) and when no worse; the route then uses it and says so. And the class defaults of the degree (D5) are learnt from how often prescriptions of each kind, and from each kind of holder, were carried out. Main first: on 5.1's world, how many judgements equal the hand-set rules, and how many cut mistakes by a third | Pure: reproducible; the planted figures as floors. Live: none, too few, a fit, a worse one refused, a model of another signature not used | Main, then `builder` ★ | **Done**, but the degree's class defaults ([as built](#66-as-built-2026-11-28)) |
| **6.7 Liveness in the verdict** | With 8.1 to 8.3: a contradiction between a denial and an assertion weighed by the denial's liveness; "expected, and did not" as a relation of its own (a notable absence) | Pure: the weights; live: a notable absence on the route | `builder` | After 8.3 |

### 6.1 as built (2026-11-27)

On `compare-6`, made from `spaces-5-networks` (which holds this plan as it stands and is not yet in `dev`).
`packages/pangloss-compare` (`pangloss_compare`), by `builder`, read by main.

- **`CompareMeta(identifying=(), once_per=None, recurs=False, compared=True, orientation="after")`** in the slot
  `_compare_meta`, inherited whole (a subclass's own replaces its parent's). **No `negates` and no weight**: negation
  is the core's `logical`, and strength the core's `degree` (D5 put it there). `orientation` is a space's only.
  `compared=False` works on a class of documents too (it and what is below it are left out).
- **The checks** (`ModelRegistry.after_finalise`, `PanglossMetaError` by the class that declares): the slot on a
  class of documents, a trait documents have, or a space, and nothing else; on a space only `compared` and
  `orientation`; `orientation` not on a document; `identifying` a list of names; each a field of every concrete
  compared class, reaching an entity (through wrappers, by the walk `Attribution`'s check uses,
  `reaches_an_entity`, which is search's `leaf_classes`: a wrapper's own relation, `InRole.at`, is not on the way);
  `once_per` one of `identifying`; `once_per` with `recurs` refused. None has a `fix=` (no add-on's refusal has).
- **A narrowed field**: the field definitions of `MakingOfPicture` have `picture_made` and no `made` (only
  pydantic's `model_fields` still lists it), so `identifying_fields(MakingOfPicture)` is
  `{"made_by": ["made_by"], "made": ["picture_made"]}`; followed through each level.
- **Readers**: `compare_meta`, `compared_classes`, `identifying_fields`, `related`, `common_class` (the more general
  of two related classes; two subclasses of one class are not related), `space_compared`, `orientation_of`.
- **The test models**: `similar_models.declare(compared=True)` gives `Birth` (once per `person`), `Making` (once
  per `made`), `Activity`, `Transfer` (recurs), `Attendance`, `Order` and `Rule` their settings.
- **Left**: `orientation` on a space that does not prescribe is not refused; `pangloss-testing` does not list the
  package among its dependencies (none of the add-ons it imports is listed; it would make a cycle).
- **Green**: the package's 37 tests of the meta (one live, on Memgraph), the planted world's 14, ruff, `ty` (red
  only for the user's file), the skill check. Its live folder is in the Neo4j list of `run_tests.sh`; not yet run
  on Neo4j.

### 6.2 as built (2026-11-27)

`pangloss_compare/maths.py`, no database: `verdict(a, b, rules, weights=None) -> Verdict`. Its docstring has the
whole of it. Tests: `tests/test_compare_maths.py` (46).

- **The input is plain data**: `Told` (the class and those above it; the entities of each field, a narrowed field
  under the name it narrows, what is behind a wrapper as if in the field; the dates as `Span`s, a date's widest
  bounds; the walk's `Signature`; the head and the source; and of what is prescribed, `Prescribed`: by whom, to
  whom, when, and the space's `orientation`), and `Rules` (a class's `CompareMeta`). Step 6.3 reads them of the
  database.
- **`Verdict`**: `relation` (one of 18, `RELATIONS`), `first` and `second` (a prescription first), `likelihood`,
  `fields` and `how` (of each: `different`, or of a target `late`, `early`, `in_part`), `reported`, `within`
  (`"factoid"`, `"source"`, None), `strength`, `common` (the nearest common class), `superseded`.
- **One event or two**: by `once_per` certain either way; else a logistic set by hand (`WEIGHTS`, eleven terms:
  identifying fields alike, partly, different; other fields; dates overlapping, the more the narrower the two
  together; the weeks apart; what recurs; sources differ; the same factoid, of two that both assert).
- **What answers a prescription** is matched on its own: the thing (the identifying fields that do not name those
  it was prescribed to), the doer, the side of when it was prescribed, and the details as targets;
  `ANSWER_WEIGHTS` makes a doing far from the target date less likely the answer (even at about half a year).

**Settled by main where the row was silent** (the user may overrule each):

- *An entity list alike, partly, or different*: two lists are alike when one holds the other (a second report
  that names fewer), `partly` when they share some and each has one the other has not (a disagreement on that
  field, and only mild evidence of two events), `different` when they share none.
- *A "not" is held against the same thing only*: a pair one of which denies (or leans against) and whose fields
  differ is `nothing` ("they met on Tuesday", "they did not meet on Wednesday").
- *Two denials of one thing* `agree`.
- *"Reportedly carried out, or reportedly not"* is not two relations of its own: what only reports the outcome has
  the relation it would have were it asserted, with `reported=True` (so also "reportedly breached").
- *Done by another* is `done_not_carried_out` only where it is on the day prescribed; otherwise another's doing
  is another event (`two`). Without this every member's gift to a group read as the doing of what one member was
  ordered to give. *Done before it was prescribed* is `done_not_carried_out`, but of a class that `recurs` it is
  another time (`two`).
- *A permission* whose thing is said not to have been done, and an order not to whose thing was done before:
  `nothing`.
- *Two prescriptions of one thing* that point the same way are `compatible`; against each other, a `conflict`
  within one flavour and authority and `orders_at_odds` otherwise; never where both are possibilities.
- *`strength`* is the likelihood times how far each side commits: 1 where it asserts or denies, else the weight
  of its degree (`DEGREES`, the actual network's: none said 0.5). So a failure to carry out an order counts the
  more, the higher the order's degree. *"Once another statement tells what happened, it decides"* is of several
  pairs, so it is a function over them: `settled(verdicts)` marks what is only reported as `superseded` when a
  statement asserts or denies the outcome of the same prescription.
- *Where a date is missing*, the side of when it was prescribed is not judged, and counts as in order (call 23).

**Measured** (the planted world at 5,000 people, seeds 1 to 3; every statement of a compared class, the pairs
those 6.3's rule gives: 71,000 to 74,000):

| | Seed 1 | Seed 2 | Seed 3 |
|---|---|---|---|
| Planted pairs with the truth's relation and fields | 99.87% of 2,297 | 99.96% of 2,350 | 99.96% of 2,379 |
| All pairs rightly one event or not | 99.78% | 99.66% | 99.72% |

What it gets wrong is mostly what the data cannot say: a gift by the one ordered, to the one named, told elsewhere
in the world, answers the order (or breaks the prohibition) as far as the data goes; two gatherings of the same
host with some of the same people, both said only by the year, are one. "One event entered twice" in one factoid
is read as two for 2 to 6% (the price of counting the same factoid against one event). The first weights read a
gathering told a few days off as two events three times in four; the date term in weeks, not days, mended it.
The test's floors: 99% of the planted pairs (95% of each case, 85% of "entered twice"), 99% of the rest. A fit of
the same eleven terms on the world gives much the same weights, but "sources differ" is an artefact there (only
the added factoids have a source), so it stays small by hand.

### 6.3, the query measured before the brief (2026-11-27)

On the world for comparison at 32,000 people (2.7M nodes with the vectors' and the workers' records; the scratch
containers `pangloss-memgraph-compared`, `:7716`, and `pangloss-neo4j-compared`, `:7717`, stopped again after).
`notes/similarity-evaluation/compare_pairs_trial.py` and `.txt`: 60 statements of each class, both reads together
(the statement's own entities, then the other statements naming one in the same field).

| | Others found, median (most) | Memgraph, median ms | Neo4j, median ms |
|---|---|---|---|
| `Activity` | 11 to 14 (23 to 45) | 2.6 | 3.9 |
| `Transfer` | 2 to 4 (34) | 1.8 | 3.1 |
| `Attendance` | 5 (8) | 1.8 | 3.2 |
| `Birth` | 1 (1) | 1.6 | 2.8 |
| `Making` | 1 (3) | 1.7 | 3.1 |

What the shape has to be, found on the way:

- **From the entity, never from the class.** One pattern from the statement's class to the entity through wrappers
  scans every node of the class on Memgraph (4.9 s for a gathering). Two halves joined by `UNION`, each starting
  at the entity by its id: the direct edge, and the edge out of a wrapper followed up through the wrappers.
- **The class is tested after the match** (`WITH ... WHERE t:Activity`): in the `MATCH`'s own `WHERE`, Memgraph
  still starts from a scan of the label (200 ms instead of 2).
- **The entity's id as a scalar** (`WITH f, f.entity AS vid`) before the `MATCH`, as reconcile's query has it.
- **Only the fields a wrapper holds its contents in** on the way (`target`, `contents`, an identification's
  alternatives): otherwise the place of an `InRole.at` counts as a participant.
- The busiest entity of the world is a group 68 transfers are given to; a person is in at most 25 roles. A cap
  (`COMPARE_MOST_PAIRS`, 200) is in the brief all the same.

### 6.3 as built (2026-11-27)

By `builder` from main's brief, with the reading of stored statements the verdict needs (which the row did not
name, and 6.5 would otherwise have had to bring). `pangloss_compare`: `rules.py`, `reading.py`, `pairs.py`,
`settings.py`; `requires = {"cypher"}`.

- **`reading.read(tx, ids, see_unpublished=...)`** gives stored statements as `maths.Told`, in four statements at
  most for any number of ids. Entities of every relation field that reaches one, through wrappers by the fields a
  wrapper holds its contents in; **real entities only** (no stand-in, no computed relation, nothing below a
  suggestion not confirmed, none deleted; a merged entity as the one kept, `survivors_of`). Dates as the stored
  widest bounds. The signature of the stored path, the head, the source the ground names (the smallest id where a
  head names several). `prescribed` from the `Attribution` of the field holding the innermost prescribing space,
  `at` the holder's date where its class has exactly one date field. A statement inside a space that is
  `compared=False`, or that the reader may not see, is not read.
- **`pairs.by_rule`** and **`pairs.pairs_of(id, see_unpublished, most=None)`** (one read transaction: the
  statement, its pairs, the pairs read). A `Pair` has its reasons, each `(field, entity, "rule" | "addressee")`.
  Most reasons first, then by id; `more` where cut at `COMPARE_MOST_PAIRS` (200, checked at `initialise()`). No
  date is asked of what may answer a prescription ("after it" is the verdict's to judge, since a statement with no
  date is not to be left out).
- **A statement that is not compared, not there, or not the reader's to see gives nothing** (an empty `Pairs`,
  `None` from `pairs_of`), as vectors and reconcile answer, for a route to make a 404.
- **A merged entity pairs both ways**: the ids absorbed into each entity are looked up (`PGMerge`), so a statement
  naming the one absorbed and one naming the one kept find each other.
- **Where the query differs from the one measured**: the class by `t.type IN $types` (a property; an `OR` of
  labels after an `UNWIND` loses rows on Memgraph, as the skill records); the statement's own entities in two
  halves, so that the last hop is by a held field; one statement more for the merges. **Measured as built**
  (`notes/similarity-evaluation/compare_pairs_built.py`, 2.7M nodes, 60 statements of each class; the statement
  read, its pairs found and read, and a verdict on each): Memgraph 3.9 to 6.4 ms at the median (most 120),
  Neo4j 5.2 to 8.7 ms (most 140).
- **Copies, not shared code**: the rule "not below a suggestion not confirmed" (reconcile's `unconfirmed`;
  reconcile is no dependency) and the reading of a stored path (the fifth). Worth one place in the kit; not done
  here.
- **The second reading (★)** found the queries right on reverse edges, where they start, visibility, the order,
  narrowed fields, merges and names in the text. Mended by main after it:
  - *a wrapper's own relation was on the way where it led to another wrapper* (a space with a field of its own
    holding an `InRole`): only the hop into the entity was tested against the held fields. Now every hop of the
    walk is (`HELD_ALL_THE_WAY`). No test has such a model: the test models have no wrapper whose own relation is
    to a wrapper;
  - `read` had `see_unpublished=True` as a default; it has none now.
- **Found and left, to know**:
  - the held fields are one list for all wrapper classes: a wrapper's own relation named as another's held field
    would be followed;
  - a prescribing space held by a wrapper and not by the document (`Order.thing_ordered: InRole[Ordered[...]]`)
    has no `by`, `to` or `at`: the holder is the wrapper, as `signature.prescribed_by` has it, and the
    `Attribution` is on the document's field;
  - an entity merged into one that is deleted counts under the deleted one's id;
  - an entity inside a "not" within a field (`participants: [Negative[Person]]`) counts as named in the field;
  - untested: a deleted head; merges of two levels and one undone; two prescribing spaces on a path; a ground
    that prescribes; `orientation="before"` read of a stored space; a head with several sources.
- **Green**: the package on Memgraph (110), its live tests on Neo4j (19), ruff, `ty` (red only for the user's
  file), the skill check. The whole suite was not run.

### 6.4 measured (2026-11-27): waiting for the user

Nothing of 6.4 is built. Its row says main first measures whether stand-ins pull statements together; the
measurement says more than that, so the step is the user's to decide.

`notes/similarity-evaluation/compare_vectors.py` (and `.txt`), no database, the structural network (D11), the
planted world at 5,000 people on three seeds. A birth told twice has one identifying field, `person`: with another
node there in the second telling, the rule (6.3) finds no pair, and only vectors could. 205 such pairs, the second
telling naming the person, the person's **mention** (a `Person` of its own, named once elsewhere with their family
and group: two entities not yet reconciled), or a **stand-in**:

| The second telling names | The other telling is the nearest birth | Among the ten nearest | The pair's cosine (median) | The nearest other birth's (median) |
|---|---|---|---|---|
| the person (the rule finds it) | 83% | 99% | 0.80 | 0.54 |
| their mention | 25% | 71% | 0.45 | 0.54 |
| a stand-in | 23% | 69% | 0.42 | 0.54 |

- **A statement's vector does not find what the rule cannot.** With the person shared, the pair stands clear of
  every other birth (0.80 against 0.54). Without, the two tellings are alike only through the place, as every
  other birth at that place is: a threshold that keeps other births out (0.7) keeps every such pair out too, and
  one that lets a third of the pairs in (0.5) lets another birth in for seven statements in ten.
- **A stand-in pulls as much as an unreconciled entity does**, which is hardly at all: the row's question is
  answered (no profile without stand-ins is needed), but only because neither helps.
- **Why**: the graph part says who a statement is near through whom it names. Two statements that name different
  nodes for one person are near only if those two nodes are, and a statement's own vector is a poor way to ask
  that.

**Main's recommendation: ask of the entities, not of the statements.** For each identifying entity X of the
statement, the entities nearest to it by a profile that knows names (`nearest(of=X, types=[its class])`, above
`COMPARE_NEAR`: what reconciliation already measures well, the demo's `who`), and for each such X′ the rule of 6.3
with X′ in X's place. Each pair found so says why by construction ("one event if X and X′ are one person", with
the link to merging them), needs a real entity on both sides (a stand-in has no vector and is no entity: never
through one), and its verdict is 6.2's with X and X′ read as one. This changes D11 in one word: the profile is
not "one of the structural network" for statements, but the one the project names for finding who is who
(`COMPARE_PROFILE`, by default reconciliation's choice). To measure before it is built: on this world, how often
X′ is among the nearest of X by that profile (phase 10's figures are of mentions against candidates, the same
question), and what `COMPARE_NEAR` keeps out.

**The user's to say**: that; or 6.4 as its row has it (pairs by the statement's own vector, which this says finds
little); or no pairs by vectors for now.

### 6.4, the entities measured (2026-11-27): shown to the user before building

The user's word on 6.4: as main recommended (the nearest entities by a profile that knows names, then the rule of
6.3 with each in the other's place; D11 changed to match), measured first. Nothing is built.

`notes/similarity-evaluation/compare_entities.py` (`.txt`: 5,000 people, seeds 1 to 3; `_32000.txt`: 32,000, seed
1), no database. The world of the table above, row "their mention": 205 births told twice, the second telling
naming the person's mention. The profile `who` (name 1, graph 0.25, the structural network), with the table of
variants.

**A mention and its person, each sought from the other** (1,992 mentions, both ways about):

| | The right one first | Among 3 | Among 5 | Among 10 | Its score (median) | The nearest other's (median) |
|---|---|---|---|---|---|---|
| 5,000 people | 53% | 78% | 86% | 95% | 0.82 | 0.79 |
| 32,000 people | 43% | 69% | 77% | 87% | 0.81 | 0.82 |
| 5,000, no table of variants | 37% | 63% | 75% | 89% | 0.69 | 0.75 |

**End to end** (every statement of a compared class; a pair is kept where the verdict, with X′ read as X, is
neither `two` nor `nothing`; `COMPARE_NEAR` 0.6):

| | Planted births found and read right: asked from the first telling, from the second | Pairs kept through the right entity | Through a wrong one | Statements given any such pair |
|---|---|---|---|---|
| 5,000, k = 3 | 60%, 87% | 301 | 568 | 1.4% |
| 5,000, k = 5 | 70%, 89% | 327 | 964 | 2.0% |
| 5,000, k = 10 | 86%, 91% | 362 | 1,778 | 2.8% |
| 32,000, k = 5 | 63%, 89% | 650 | 2,385 | 2.0% |

- **It finds what a statement's own vector could not**: seven to nine in ten of the planted births, each read as
  the truth has it (relation and fields), against a quarter "nearest" with nothing to tell it from the rest.
- **The score does not tell the right entity from a wrong one** (0.82 against 0.79: the world is thick with
  namesakes and families of one surname). `COMPARE_NEAR` is only a floor: at 0.8 half the right ones are lost and
  one wrong one a person still comes; it is `COMPARE_NEAR_K` that decides.
- **The verdict does the sorting**: of 492,029 pairs worked out through a wrong entity (k = 5), 964 are kept, one
  in 500. What is left is mostly a namesake's birth (726 `disagree`, 44 `agree`): "once per person" makes two
  births of "one person" one event for certain, so the pair reads "one birth, told differently, if these are one
  person". Next a namesake's gift read as answering an order (179).
- **"Once per" weighed and not taken as certain** for these pairs (the logistic decides): the wrong ones kept fall
  from 964 to 250, and the planted births read right from 80% to 58% (a birth told again with another date is then
  two events).
- **The cost**: 2.5 searches a statement, 12 entities given (k = 5), and 11 more statements read and judged. One
  search by `who` among people was measured in phase 8 at 32,000 people: 336 ms at the median on Memgraph, 211 ms on
  Neo4j (`planted_names_*.txt`). So about 0.5 to 0.9 s for a statement, where the pairs by rule take 4 to 9 ms.
- Not measured: entities other than people (no group, place or thing is planted twice); the searches live on this
  world (the figure is phase 8's, of the same size).

**Main's proposals, for the user's word before the brief**:

1. `COMPARE_PROFILE` (default: reconciliation's choice, `who` in the guide), `COMPARE_NEAR_K` 5, `COMPARE_NEAR` 0.6
   as a floor.
2. A pair by vectors is given only where the verdict is neither `two` nor `nothing`, always marked as conditional
   ("if X and X′ are one person", with the link to merging them), listed after the pairs by rule, and never an
   example for learning unless a person judges it.
3. Asked for apart from the pairs by rule (`?near=true`, the interface asking once the page stands), since it
   costs a hundred times as much.
4. "Once per" kept certain (the pair then says what merging the two would mean: two accounts of one birth that
   disagree), or weighed: the user's to choose; main leans to certain, the disagreement shown being evidence
   against the merge.

### 6.4 as built (2026-11-27)

The user took the four proposals above ("once per" kept certain). By `builder` from main's brief, read by main and
by a second reader. `pangloss_compare`: `near.py` (new), `pairs.py` (`naming`; `by_rule`'s query part shared),
`compare.py` (`compare_near`), `api.py`, `settings.py`. The page [compare.md](compare.md) has the route's JSON.

- **Settings**: `COMPARE_PROFILE` (None: reconciliation's choice where `pangloss_vectors` and `pangloss_reconcile`
  are both installed, else no such pairs; a name must be a profile, and is refused without `pangloss_vectors`),
  `COMPARE_NEAR_K` (5), `COMPARE_NEAR` (0.6, a floor). Neither package is a dependency; each is imported only where
  installed.
- **`GET /api/compare/{type}/{ref}?near=true`** gives the same shape with only the pairs through near entities:
  each `found: "near"`, its reasons `{field, kind: "near", entity: {id, type, label}, near: {id, type, label},
  score}`; and `near: {profile, k, floor, state}` (`ok`, `pending`, `rebuild_due`, the worst of the searches; `none`
  with no profile). Without the parameter the answer is as before, with `near: null` added.
- **How**: the statement read; for each identifying entity a `nearest` (its own transaction) among the concrete
  entity classes the field reaches, in the statement's class and those related; then one query (the rule's own,
  with every condition of 6.3, a merge of X′ followed) for the statements naming an X′ in the same field, with the
  pairs by rule to leave out; cut at `COMPARE_MOST_PAIRS`, the nearest entity's first; the verdict with each X′ read
  as its X (in the fields and in what is prescribed by and to), kept where neither `two` nor `nothing`. Nothing
  through whom a prescription is to. Never superseded, superseding nothing. A person's judgement overrides as of
  any pair. A birth is 3 transactions and 16 statements, 6 of them a search.
- **Learning is unchanged**: a judgement of such a pair is read of the statements as they are, whose identifying
  entities differ, so it is left out (`by_rule`, `not_the_thing`); once the two entities are merged it is an
  example as any other.
- **The second reading (★)** found no fault to mend: the refactor of `by_rule` keeps its behaviour, no leak
  (entities have no published state; statements only as read for the reader), nothing written.
- **Found and left, for the user**:
  - *the cut is before the verdict*: a namesake named in 200 statements, nearer than the right one, takes every
    place, and the answer is `more: true` with few pairs. Rare at the sizes measured (11 statements at the mean);
  - the statement's own head or source is not read with X′ as X (`sources differ` may count where it should not);
    and where the statement itself names X′ in another field, it keeps both;
  - `COMPARE_PROFILE` is not checked to weigh a part that knows names;
  - a reason's `entity` is an object here and an id in a pair by rule;
  - untested live: `rebuild_due`; a class given only by use among those searched; X′ named only below a suggestion
    not confirmed, or in a space not compared (the rule's own query, which 6.3 tests);
  - **an older test depends on the hash seed**: `test_compare_learning.py`'s fit on the planted world fails with
    `PYTHONHASHSEED=4` (72 mistakes, floor 40) and passes with 1, 2, 3, 5. Of 6.6, not of this step; not mended.
- **Not measured at size**: the route with `near` (the searches' cost is phase 8's figure, above).
- **Green**: the package on Memgraph (212), its live tests on Neo4j (56), ruff, `ty` (red only for the user's
  file), the skill check. The whole suite was not run (nothing outside the package is touched but its docs and the
  lock file).

### 6.5 as built (2026-11-27)

By `builder`, read by main and by a second reader. `pangloss_compare`: `models.py`, `judgements.py`, `compare.py`,
`api.py`, `migrations/0001_initial.py`. The page [compare.md](compare.md) has the route's JSON.

- **`EventJudgement(Document)`**, abstract, no type parameter (0.5): `verdict` (D7's seven: `agree`, `disagree`,
  `two_events`, `carried_out`, `carried_out_otherwise`, `not_carried_out`, `breach`), `fields: list[str] = []`,
  `note: str = ""`. The project declares below it `statement: Cites[...]` and `other: Cites[...]`; checked at
  `initialise()` (each a single, protecting citation; no `fix=`: no add-on has one). The package ships a migration
  for the abstract class, as zotero and the calendar do; the test that shipped migrations cover their models has
  it now (Memgraph's). `similar_models.declare(compared=True)` has `StatementJudgement`.
- **`GET /api/compare/{type}/{ref}`**: the statement and its pairs, each with the other statement (id, class,
  label and its head's, for a chip), what the entry says (`relation`, `fields`, `how`, `reported`), the maths'
  own answer beside it (`workedOut`), `likelihood`, `within`, `strength`, `superseded`, `first`, `second`,
  `common`, how it was found (`found: "rule"`, `by`), `judged` and every judgement (newest first: verdict, fields,
  note, who, when, `changedSinceCited`). One read transaction, 5 to 9 statements; nothing written. Ordered by the
  maths' strength, `two` and `nothing` last. The same 404 for an unknown class or id, a class not compared, a
  statement of another class, and one the reader may not see.
- **A person's judgement overrides** the relation and the fields (`two_events` is `two`; never `reported`); the
  newest wins; either order of the two citations counts; one on a statement changed since cited still overrides,
  with the notice (the citations' own stored mark). A judgement shows only to a reader who may see the judgement
  itself; the statements it cites are those already read as that reader.
- **The second reading (★)** found no leak, no wrong judgement and no write. Mended by main after it:
  - *`superseded` was worked out of the maths alone, before the override*: a pair a person had judged could still
    be marked superseded, and a statement a person had judged to be another event still superseded a report. Now
    `compare.settle` works it out of what the entries say: a judged pair is never superseded, a person's answer
    tells as a statement does, a pair judged two events tells nothing (four pure tests);
  - the shipped migration was covered by no test.
- **Found and left, for the user**:
  - *"Newest", who and when are the judgement's creation.* A judgement can be edited by the ordinary `PUT`, and
    an edit changes none of the three: an older judgement edited today still loses to a newer one, and keeps its
    maker's name whoever edited it. Either a judgement is not to be edited (nothing refuses it), or the last write
    should order and name it;
  - *field names are Python's* (`carried_out_by`) in `fields`, `how` and `by`, where every payload says
    `carriedOutBy`; and a judgement's `fields` is not checked against the statements' fields. To settle with the
    interface (7.4 to 7.6), which is the first to send them;
  - a judgement that cites one statement in both fields is accepted, never shown, and protects the statement;
  - with `pangloss-derived`, a `Cites` field also takes a cited basis: a judgement written through one would not
    be found (it cannot arise unless a resolver makes a statement's citation a basis);
  - untested: another class's citation of the same statement (`Inference.evidence`) not taken for a judgement;
    `changedSinceCited` from the asked statement's own side; the 404 for a statement of another class, by itself.
- **Not measured at size**: the judgements' statement (it starts from the indexed `target_id`; the scratch worlds
  hold no judgements).
- **Green**: the package on Memgraph (142), its live tests on Neo4j (30), the shipped migrations' test on
  Memgraph, ruff, `ty` (red only for the user's file), the stubs' check, the skill check. Not run: the whole
  suite, the browser tests (no interface yet).

### 6.6, measured before its brief (2026-11-27)

`notes/similarity-evaluation/compare_learn_trial.py` (and `.txt`), no database: a judgement is taken to be the
truth of the pair; fitted (`pangloss_learn.fit`, the eleven terms of 6.2) on judgements of the planted world of
seed 1 at 5,000 people, counted on the 70,017 pairs of seed 2 that the logistic decides. By hand: **150 mistakes**
(0.21%). The median of seven draws:

| Judgements | Of any pair: the fit | Of pairs shown as likely (0.2 or more by hand): the fit | The same, with the hand-set score among the features |
|---|---|---|---|
| 50 | 1,682 | 17,361 | **54** |
| 100 | 1,003 | 17,198 | **38** |
| 200 | 687 | 15,211 | 38 |
| 400 | 83 | 15,065 | 38 |
| 800 | 63 | 6,825 | 47 |
| 3,200 | 54 | 1,008 | 41 |

- **People judge what they are shown**, and what is shown is what the hand-set score thinks likely (one pair in
  seventeen). A fit on those judgements alone knows nothing of the other sixteen and calls them one event: a
  hundred times the mistakes, however many judgements. Among the shown pairs themselves it is good (88 mistakes at
  100 judgements, 59 at 3,200, of 4,205), so a comparison held out of the judgements (`compare_calls`) would
  **pass it**: the check the row names does not catch this.
- **With the hand-set score as one more feature** (its log odds, `by_hand`) the fit corrects the score where there
  are judgements and leaves it standing where there are none: as good as by hand from about 25 to 50 judgements,
  mistakes cut by two thirds from 50 to 100, and no worse for being fitted only on what was shown.
- So 6.6 is built so: the features are 6.2's and `by_hand`; `COMPARE_LEARN_FROM` stays 100; the row's "how many
  judgements equal the hand-set rules, and how many cut mistakes by a third" is **about 50, and about 50 to 100**,
  not the several hundred of phase 12's trial (which fitted from nothing).
- Not measured: judges who are sometimes wrong; "does this answer that" (too few kinds of case planted to say
  more than the hand-set rule does); the class defaults of the degree learnt from how often prescriptions were
  carried out (the row's last sentence), which goes with phase 8's degree from outside.

### 6.6 as built (2026-11-28)

The maths by main (`verdict(..., fitted=)`), the rest by `builder` on reconciliation's design, read by main and by
a second reader. `pangloss_compare`: `learning.py` (pure), `fits.py`, `structure.py`, `migrations/0002_models.py`,
`cli.py`, `admin.py`. The page [compare.md](compare.md) has what a user types.

- **Two models, each a correction of the hand-set score** ([measured](#66-measured-before-its-brief-2026-11-27)):
  "one event or two" (`agree`, `disagree` yes; `two_events` no; of two that describe, where the logistic decides)
  and "does this answer that" (`carried_out`, `carried_out_otherwise`, `not_carried_out`, `breach` yes;
  `two_events` no; of a prescription and another). The features are 6.2's terms and `by_hand`, the log odds of
  the hand-set likelihood. `maths.verdict(fitted={...})` applies them; `weights` and `fitted` together are
  refused.
- **Which judgements are examples**: the newest of each pair only; left out, each counted by why: `older`,
  `changed` (a statement changed since cited: call 8), `unread`, `itself`, `not_compared`, `says_nothing`,
  `two_prescriptions`, `by_rule`, `not_the_thing`, `other_verdict`. Where the newest of a pair is left out, no
  older one stands in.
- **`pangloss compare learn [--dry-run] [--use ID|none]`, `pangloss compare status`, and the admin job
  `compare_learn`.** A fit is a `PGCompareModel` (none deleted, at most one in use; both models as JSON, the
  counts, the comparisons, the signature). A model is used when it has `COMPARE_LEARN_FROM` (100) examples and,
  over five folds held out, calls the judgements rightly at least as often as the hand-set score does
  (`pangloss_learn.compare_calls(baseline=...)`, an option added there). Each of the two by itself. A fit of
  another signature (the terms, the hand-set weights, any compared class's rules) is not used.
- **The route** reads the fit in use (one statement more, in its transaction) and says so: `model` is null, or
  `{id, at, judgements, oneEvent, answers}`.
- **Measured on the planted world at 2,000 people** (judged on seed 1, among the pairs by hand at 0.2 or more;
  counted on the 31,459 pairs of seed 2 that the logistic decides): 67 mistakes by hand; with 100 judgements 23
  to 40; with 400, 23 to 26; the same judgements fitted without `by_hand`, 513 to 8,222. The test's floors: 40,
  30, and fifty times as many without the term.
- **The second reading (★)** found the examples and what the verdict applies in step, the folds right, the write
  that puts a fit in use in one transaction, and the signature the same between processes. Mended by main after
  it:
  - *"does this answer that" learnt from pairs no likelihood decides*: what another did, or what was done before
    the order, the rules settle before any likelihood is asked, yet a judgement of such a pair was an example,
    and the hand-set score was held to a call it never makes (0.82 "yes" of a going by another). They are left
    out now (`by_rule`);
  - the route's `judgements` counted the examples of a model fitted and not used.
- **Not built** (the row's last sentence): the class defaults of the degree learnt from how often prescriptions
  were carried out. It goes with the degree from outside, phase 8.
- **Found and left, for the user**:
  - *the check is noisy at 100 judgements*: in two draws of five a fit that halves the mistakes across the world
    was refused, right 95 times against 96 held out. "No worse" is the row's word; a margin, or more judgements
    before a fit is tried, would be the user's change. And a fold with no "two events" in the others cannot be
    fitted, which refuses the model: people rarely judging "two events" is the likely case;
  - *anyone may read the route, and a fit is of every judgement*, unpublished ones too: the verdicts a reader not
    logged in is shown are shifted by judgements that reader may not see, and `model.judgements` counts them
    (reconciliation's route, which the design is from, is for logged-in readers only);
  - *a new fit with one usable model takes the place of one in use with both*: the other falls back to the
    hand-set score, and the lines say only what is in use;
  - *every run of `learn` writes a fit* (reconciliation skips when nothing is new; here an edited judgement
    changes neither count nor time, so "nothing new" cannot be told). The route scans the label on each request;
  - a person cannot say "done, but not carried out", "complied with" or "permission used" (D7's seven);
  - adding any compared class changes the signature and turns a fit off; only `status` says why;
  - untested: an "answers" model in use, live (every live judgement is of two gatherings); a fit one of whose
    models passed and the other was fitted and failed; two runs of `learn` at once.
- **Not measured at size**: `learn`'s read (every judgement and both its statements in one transaction) and the
  route's one statement more.
- **Green**: the package on Memgraph (175), its live tests on Neo4j (44), `pangloss-learn` (33), the shipped
  migrations' tests on both backends, ruff, `ty` (red only for the user's file), the skill check.

### Phase 6, the questions answered (2026-11-27)

The user took main's recommendation on each of what 6.4, 6.5 and 6.6 left. To build, as one step ("6.8"):

1. **A judgement is not edited.** An update of an `EventJudgement` is refused everywhere; a change of mind is a new
   judgement, the old one a record. Deleting stays as the framework has it.
2. **The route's JSON says field names in camelCase** (`fields`, `how`, `by`, a reason's `field`), both ways; the
   store keeps Python's. A judgement's `fields` is checked on write: each a field of one of the two statements'
   classes.
3. **The check before a fit is used**: refused only when worse than the hand-set score by more than chance (the
   hand-set score right more often by more than `COMPARE_LEARN_MARGIN`, 1.0, times the square root of the number of
   held-out judgements the two call differently); and the folds share each answer evenly (stratified), so no fold
   is fitted without a "two events".
4. **The route stays public and a fit is of every judgement.** The counts in `model` (`judgements`, `oneEvent`,
   `answers`) are given only to a logged-in reader.
5. **`learn` writes no fit when nothing is new** (the same signature, count of judgements and newest creation as
   the last fit), as reconciliation does.
6. **A fit that would lose a model the one in use has is not put in use**; it is written, and `learn` says why.
   `--use ID` still puts it in use.
7. **What a person cannot say** (D7's seven) waits for 7.4.
8. **The places below `COMPARE_MOST_PAIRS` are shared among the near entities in turn**, the nearest's first in
   each turn.
9. **The whole suite and the browser tests, then `spaces-5-networks` and `compare-6` into `dev`.**

And mended without a question: the test of 6.6 that depends on the hash seed; a reason's `entity` an object
(id, class, label) in a pair by rule too; the source and the head read with X′ as X, and X′ named in another field
of the statement itself read as X; a judgement citing one statement in both fields refused; `COMPARE_PROFILE`
refused at start-up when the profile weighs no part that knows names; tests for what 6.4, 6.5 and 6.6 list as
untested.

### 6.8 as built (2026-11-27)

By `builder` from main's brief, read by a second reader, mended by `builder` after it. `pangloss_compare`
(`models.py`, `compare.py`, `near.py`, `learning.py`, `fits.py`, `settings.py`, `judgements.py`) and
`pangloss_learn` (`maths.py`). The page [compare.md](compare.md) has the route's JSON and what a user types.

- **1, no edit**: `EventJudgement.refuse_any_update` (a `@before_update`): the `PUT` is a 422, a script's update
  raises. So the "changed since cited" mark of a judgement is for good. No model may hold a judgement as a
  subdocument (refused at `initialise()`: it would lock its holder).
- **2, camelCase**: in `fields`, the keys of `how`, `workedOut`, a reason's `field`, a judgement's `fields`. On
  creation a judgement's `fields` are matched against the two cited classes' own fields (by Python's name or its
  camelCase), stored by the name the maths uses (a narrowed field by its root name), refused where no field; one
  statement cited twice refused. *Not done*: the ordinary `GET` of a judgement gives Python's names.
- **3, the check**: `pangloss_learn.compare_calls(stratified=, count_differences=)` (both off by default:
  reconciliation gets what it did, pinned by a test), `CallsCompared.within(margin)`, `COMPARE_LEARN_MARGIN` (1.0;
  0 is "no worse"). **Measured** (the second reader; 2,000 people, 100 judgements, 30 draws, judges always right):
  all 30 pass at 1.0 (the old check refused 2), 27 of them at 23 to 40 mistakes against 67 by hand, three at 49 to
  67, which call the shown pairs exactly as the hand-set score does, so no check held out of what is shown can see
  them.
- **4**: `model`'s three counts null to a reader not logged in.
- **5, nothing new**: the same signature, count of judgements, newest creation, examples of each model, what was
  left out and a digest of the examples (`examples_digest` on the fit: an edit of a cited statement or a merge
  changes it) as the newest fit written. No way to force it (reconciliation has none). A dry run still fits.
- **6**: a fit that would lose a model is written, not in use, with `not_in_use` saying why. Two runs at once
  could leave two in use: a second transaction now leaves only the newest.
- **8, the places in turn** (`near.candidates`): across every identifying field, the nearest entity's first.
- **Mends**: the hash-seed fault was the test's own helper (a frozenset walked), not the product's (seeds 0 to 9
  pass); a rule reason's `entity` an object; the source read with X′ as X; `COMPARE_PROFILE` refused only when set
  and knowing no names (reconciliation's choice without a part of names: no near pairs, the project starts); tests
  for all the untested but "a class given only by use" (the test models have none).
- **Changed by main after the second reading, for the user to know**: *a statement that itself names both X and
  X′ gives no pair through that X′* (`near.not_both`): it is the best sign they are two. This takes the place of
  "X′ named in another field of the statement itself read as X", which made a giver and receiver swapped agree.
  It runs after the cut, so a pair it drops leaves its place empty.
- **Found and left, for the user**:
  - *the check does not tell a bad fit when judges are wrong*: with one verdict in ten flipped, 17 fits of 20 pass
    at 1.0, at 25 to 222 mistakes against 67 by hand; with one in five, three above 900. Margin 0 refuses more and
    no better. The check measures agreement with the judgements on what is shown. A guard would be another thing:
    more judgements before a fit is tried, or a bound on how far a fit may move the hand-set score;
  - a reviewable judgement class cannot be published by `PUT ?review_status=` (an update); review's own route
    works. History's restore of a judgement is refused likewise (untested);
  - `fields` are unchecked where the cited statements are made in the same bulk create;
  - a run of `learn` whose fit the other run's settling unmarks has already said its fit is in use.

## Phase 7: the interface

**Decide first** (D8): which of 7.1 to 7.3, and whether a headless space is the default or asked for by
`InterfaceMeta(headless=True)` on the space, as on a reified relation. Every step: its text as `t()` slots with
translations, a row of `e2e/COVERAGE.md`, the dev build (`e2e/test_dev_mode.py`), and `solidjs-v2-reviewer` on the
diff.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **7.1 A space with no choice, headless** | `headlessIn` (`schema/headless.ts`) takes a semantic space too: in a field that can hold that space and nothing else, one of it, and must (`Order.content: Ordered[...]`). The form (`ModelFields.tsx`) draws its contents with no head bar; the view (`ItemContents.tsx`) keeps the band and its colour | Vitest (`headless.test.ts`); e2e on the e2e project's models | `builder` | **Done** 2026-11-26, [as built](#71-as-built-2026-11-26) |
| **7.2 "Not" as a toggle** | Where a field or a space's contents offers `X \| Not[X]` (a space with `logical="not"`), a "not" toggle on the item wraps it in the space or takes it out, client-side (as the retyping of nested documents does), in place of the space's section of `TypeMenu` | Vitest; e2e: on, saved, read back inside `Not`; off | `builder` | **Done** 2026-11-26, [as built](#72-as-built-2026-11-26) |
| **7.3 What is not asserted, marked** | The walk ported to TypeScript (`interface-core`, pure), passing `space_cases.json` (3.1); a statement whose path is not `1` marked where it is listed without its band (search results, a person's statements) | Vitest on the shared cases; e2e: a statement in `Not` marked in a list | `builder` | **Done** 2026-11-26, [as built](#73-as-built-2026-11-26) |
| **7.3b What kind of space a band is** | Decided by the user 2026-11-26 (D17): a band shows what its space says of what it holds by a **pattern** (or by icons, if suitable ones are found: main looks first and says which it took and why), **and a project can change it**. From the walk's facts of the class (`spaceFacts`): denies, asserts, neither; prescribes; a modality. Main settles: the default for each kind; where it is drawn (the band on a page, in a form, round a chip, the "not" toggle's band); how it is changed (per class by `InterfaceMeta`, and the defaults for a project); that a space with no option set looks as it does today. Tailwind only; the user has refused new lighting and chips without outlines before | Vitest (which pattern a class gets; the override); e2e: a `Not` band and a plain one differ, an override is followed; screenshots for the user | Main settles, `builder` builds | **Done** 2026-11-26, [as built](#73b-as-built-2026-11-26) |
| **7.4 "Compared"** | A module of `pangloss-compare` (phase 12's 12.7): an item section on a statement's page, as "Similar" is: each pair's relation (by rule or by vectors, within one source or not), a judgement's chip; on an order's page, "Carried out?" | The module's unit tests; `e2e/test_compare.py` on the e2e project's models | `builder` | To do |
| **7.5 Side by side, and recording** | Phase 12's 12.8: `align` and `AlignedCell` moved from `pangloss-history` into `interface-core` (history imports them; its tests unchanged), with a pairing of parts by field and place where there are no shared ids; a page `/compare/:type/:a/:b` (a module route), the two statements on the fields of their nearest common class, the relation above (for a fulfilment, each target met or missed); logged in, a judgement recorded (6.5) and the page showing it; from a pair by vectors, a link to merging the two entities | Unit tests of the pairing; e2e: each verdict recorded, the section changes; history's e2e unchanged | `builder` | To do |
| **7.6 "Similar" by relation** | `pangloss-vectors`' section keeps its order, by content, and labels each statement by its relation to this one (6.2): "contradicts", "carried out", "reported", "might have"; filters "only what the sources assert" and "only contradictions" | The module's tests; e2e | `builder` | To do |
| **7.7 Derived's status shown** | Derived's section (`DerivedSection.tsx`) gives a fact's status ("asserted by two, denied by one") from 4.1 | The module's tests; e2e | `builder` | After 4.1 |

### 7.1 as built (2026-11-26)

On the branch `spaces-7-forms`, made from `dev` once phases 0 to 4 were merged into it. `builder` from main's brief;
a second reading with `solidjs-v2-reviewer`, which found no fault that blocks.

- **Asked for, not the default** (D8): `_interface_meta = InterfaceMeta(headless=True)` is allowed on a
  `SemanticSpace` as on a `ReifiedRelation` (`meta.py`, `HEADLESS_KINDS`), and refused on anything else.
- **`headlessIn`** takes a space on the same conditions: the field is single and required and that space is its one
  option. A space with a class below it offered in the field has two options and keeps its head.
- **The form**: no head bar, no band, no type menu, no button to remove or copy it: what it holds (with the
  controls its contents have), then its own fields. A new form holds the space from the start (`blankItem`, a rule
  for a headless space only: a space is not a choice of its own in the menu, the types inside it are).
- **The view**: no head, in its band and colour; what it holds, then its own fields where one is filled.
- The e2e project has `Reported[T]` (headless, with a `Degree()` field), `Deposition.account: Reported[Claim]` and
  `Hearsay.account: Reported[Claim] | Claim`.
- **Found and left, to know**:
  - a space *with* its head shows none of its own fields on an item's page (older than this step; the headless one
    does): mended with 7.3, where the degree is drawn beside the head;
  - the values of a degree are shown as they are stored (`likely`), with no translation: 7.3;
  - the field's mark of "required" is green from the start, the space being there (the save still refuses);
  - a document made through the type menu inside something else (`choiceValue`) has no headless space until it is
    added once, after which it cannot be removed (so of a headless reified relation, before this step);
  - where the field's option is a type variable the page draws the head and the form does not (the same);
  - no browser test of a unary headless space, or of one whose contents may be of several types.
- Tests: `test_interface_meta.py` (3 more), `headless.test.ts` (4 more), the workspace's Vitest (663) and
  typecheck; e2e `test_fields_and_wrappers.py` (2 more, 8) and `test_dev_mode.py` (1 more, 33). One older test of
  that file (`test_enums_are_pills...`, a `Dossier`) timed out in two of five runs and passed alone.

### 7.2 as built (2026-11-26)

On `spaces-7-forms`, by `builder` from main's brief (its eight decisions); a second reading with
`solidjs-v2-reviewer`, whose findings main mended.

- **The pure layer**, `schema/negation.ts`: `negationFor` (can this item be negated here, and in which space: exactly
  one "not" space among the options takes its type, with no fields but `contents` and db fields, no edge model on the
  item's option, the space's, or the type's inside it; the type offered plainly; not a space, a citation or a cited
  basis), `negatedValue` (a "not" space holding one item that `negationFor` would put there, not a space, and an
  entity only once chosen), `formMenuGroups` (the menu less the space's section for what the toggle makes), `negate` /
  `unnegate`. `relationLayout` and `blankItem` use `formMenuGroups`, so the buttons beside an entity search and the
  blank item of a required field follow the menu (a required `Claim | Not[Claim]` now starts with a `Claim`).
- **The form** (`ModelFields.tsx`): `NotToggle`, a button named by the space, `aria-pressed`, solid in the space's
  colour when on; in a document's bar after ↧/↥, in a reified relation's or a conjunction's bar, on an entity's chip
  before copy, cut and remove (`ReferenceChipProps.actions`). A negated value is drawn as its item inside the space's
  band, with no head; removing, cutting or copying it takes the space too. On and off replace the value at the same
  path; the space's own keys (its id, label) are kept by the relation's editor when taken out and given back when put
  in again, so a saved space toggled off and on has nothing to save.
- **Settled by main**: an item has the toggle only where exactly one "not" space takes its type, that space has no
  field of its own, and no edge model is in the way; anything else is made in the menu and drawn with the space's
  head, as before. The item's page and the search form are unchanged.
- **Found by the second reading, and mended**:
  1. A type that an interface module draws by an `editCard` (review's stand-in for a mention, criteria's
     `MatchesCriteria`) left the menu and had no toggle, so it could not be negated at all. Such a type is not
     "offered plainly": it stays in the menu and its space keeps its head.
  2. What a space had of its own was kept by the item's whole content: a change to the item between off and on lost
     the space's id (and so the item's), and the same entity twice in a list could be given one space's id twice. It
     is kept by the item's id, and used once.
  3. A press drew the item anew and the focus was lost; the toggle in its place takes it.
- **Found and left, to know**:
  - nothing inside a new node is sent with an id (the API refuses one there): a saved item put in a new `Not` is
    written anew, with new ids for it and what it holds, as when it was made through the menu. Its old id is gone, so
    an item that something cites (`Cites[T]`) cannot be negated by the toggle without the citation being refused;
  - bindings (`FieldBinding`) give an empty bound field its value again when the item is put in or taken out (the
    binder sees an object set under the relation);
  - the fold of a block inside the toggled item is not kept across a toggle (it is drawn anew);
  - a project that replaces `ReferenceChip` has to draw its `actions`, or an entity has no toggle there (as with
    `onCopy` and `onRemove`);
  - in a generic model (`parts: list[T | Not[T]]`) the toggle makes what the menu never offered, and the models
    accept;
  - no browser test of a reified relation or a conjunction as the item, of cut and copy of a negated item, or of
    the focus after a press.
- Tests: `negation.test.ts` (13), `NotToggle.test.tsx` (4); e2e `test_not_toggle.py` (2) and `test_dev_mode.py`
  (1 more), on the e2e project's `Not` and `Affidavit`.

### 7.3 as built (2026-11-26)

On `spaces-7-forms`, by `builder` from main's brief; main read the port against the Python line by line; a second
reading with `solidjs-v2-reviewer`, whose findings main mended.

- **The walk in TypeScript**, `interface-core/src/schema/spaces.ts`, pure, exported from `schema/index.ts`:
  `spaceFacts(definitions)` (from the exported models, abstract classes included, made once for them: the export
  gives every space class `veridical`, `fit`, `logical`, `unary`, `degree` and `abstract`, so it was not changed),
  `normalise`, `signature` (the `Signature` of `as_json()`, with `holdsAsSpace`: a space says something of its
  `contents` only), `UnknownSpaceError`, `signatureOf` (`undefined` for a space the models do not know), `statusOf`
  (derived's `status_of`, the same seven names), `markOf` (the mark's rule, below), `degreeField`, `DEGREE_STEPS`,
  `PATH_KIND_OF` (`context.KIND_OF`). The input is `WalkEntry` (`types/models.ts`), which the API's `PathEntry` is and
  a path built from a form's value (no ids) is. `spaces.test.ts` reads `pangloss-models/tests/space_cases.json` where
  it is (by a relative URL, as `labelTemplate.test.ts` reads `label_cases.json`) and passes all 57 cases.
- **The library's reading** (`identity.ts`): each `Claim` has `said` (the walk's `veridical` of its path: its stored
  `meta.path`, else the path built while walking what holds it, by `PATH_KIND_OF`, type, id and the field's Python
  name); `grouped`/`byContext` give `said` 1 (with those in no space), `-1` (one group, "Said to be different from")
  and `0` (by spaces, as before), in that order; `contested` is an entity said plainly and also otherwise. A space the
  models do not know reads as `0`; `claimDirect` with spaces and no path, as `0`. `IdentitySection.tsx` heads the
  `-1` group with `identity_different` (`data-said` on each context). A project that sets no space option sees no
  change: a plain space is `0`.
- **The mark**, `AssertionMark` (in `components/SpaceBands.tsx`, a file every page that draws a chip loads already,
  so no new chunk): derived's words and colours (`assertion_*` slots: Denied, Reported, Prescribed, Reported not,
  Forbidden, Not said either way; rose for what speaks against it, amber for the rest), the degree in its title
  (`assertion_with_degree`). **`markOf`**: nothing for `asserted`, nor for `reported` with no degree (a plain space,
  whose band says it); everything else. `ReferenceChip` and `ResultButton` take `path` and draw it after the label,
  inside the link.
  - *Covered*: a list page's rows (`List.tsx`); "search everything" (`GlobalSearch`: the home page, the quick search,
    the citation picker's search); what refers to an entity on its page (`ItemContents` with `asChip`: a chip, and the
    head of a block through `Head`'s new `mark`; so also `ItemValue` with `asChip` in modules' cards, and the library's
    `IdentityIncluded`, which draws each member's `ItemContents`); a nested item's own page, once, after "Contained in" and its field (`Item.tsx`).
  - *Not covered, and why*: a citation's chip and the citation picker's list of parts (`Citation.tsx`: the API gives
    `targetSpaces`, no path); the chips of interface modules that read their own routes (vectors' "Similar", derived,
    review, criteria, reconcile: their answers have no path); the identity section's claim chips (its grouping says
    it); the console's title and `ContextFrames` (the page's one mark covers them); a chip in a form (an entity: its
    path is empty); a module's `viewCard` that replaces a chip or a row (`Customised` is not given the path); the
    quick search's chip of the picked item (type, id and label only).
- **The degree beside a space's head**: the view (`ItemContents.tsx`, `SpaceDegree`) shows the step entered, in words,
  beside the space's name, else the class's default muted ("expected (default)", `degree_default_title`), else
  nothing; the space's other fields of its own are shown under what it holds (`Fields` takes several keys to leave
  out). The form (`ModelFields.tsx`, `HeadDegree`): a small `MenuSelect` in the head's bar (the five steps, and an
  empty choice that says the default or "No degree"), its row skipped, its problems (`useRowProblems`) beside it. A
  headless space keeps the row; its pills (`LiteralEditor`) and the value on the page (`Value`) are in words.
  `useDegreeName` (in `SpaceBands.tsx`) and the `degree_*` slots, in English as stored (`likely`), so the browser
  tests of 7.1 are unchanged.
- **The e2e project**: `Ledger.entries` also takes `Not[SameEntity[Person]]`. `e2e/test_assertion_marks.py` (3): a
  claim in `Not` "Denied" on `/Claim`, a plain one and one in a plain `Reported` not marked, one reported as likely
  marked with its degree in the title, and the claim's own page marked once; the degree on `Hearsay`'s page and
  chosen in its form, saved and read back; a `Not[SameEntity]` under "Said to be different from" and the cluster's
  "said to be different" row. `test_dev_mode.py::test_a_mark_of_what_is_not_asserted_and_the_degree_in_a_head`.
- **Settled by main**: an item in a plain space (no option set) has no mark, its band saying which space it is in:
  otherwise every such item would be marked "Reported". **Not built, the user's to decide** (D17): how a band shows
  what kind of space it is (an icon, a pattern); no band's look is changed.
- **Found by the second reading, and mended**:
  1. **In the Python walk** (3.1): `registered_spaces()` counted `Epistemic[T]`, the parametrisation that declaring
     a class below an abstract `Epistemic` makes, which has its `logical` and not its `abstract`. So an abstract
     necessity with a committing class below it made "cannot have been" uncommitted in Python (derived, the
     clusters) and denied in the port, which reads the export, where there is no such class. Parametrisations are
     left out, as the export leaves them out; the shared cases' tables lose them (no expectation changes); a test
     of the shape in `test_spaces_walk.py`.
  2. The degree's menu in a head was drawn for a degree the forms hide (`hide_on_forms`) or that something else
     keeps (read-only), and a required degree lost its mark. It is drawn only for a degree the form shows and that
     may be left out; a required one keeps its row.
- **Settled by the builder**: the wording is derived's (so "Forbidden", not "prescribed not", and "Not said either
  way"); the mark is not drawn on the item's own page but once on a nested item's; `said` `-1` claims are one group
  whatever their spaces (as the server's `saidDifferent`); the degree's English texts are the stored steps.
- **Found and left, to know**:
  - the identity section offers "Compare, or merge" on an entity it lists as "said to be different from";
  - no browser test of a chip with a mark (no model of the e2e project puts a document that refers to an entity, or
    one "search everything" finds, inside a space with options; `Claim` is not found by it): Vitest only;
  - the chip's mark is inside the link, so a chip with a mark is wider; a chip in a narrow place truncates the label
    first;
  - the head's degree menu is 176px wide in a narrow column (`@max-sm`) as well;
  - no Vitest of a validation problem shown beside the head's degree menu (a stored degree cannot be wrong through
    the form);
  - a citation's chip shows the spaces of what it cites and no mark, and a module's chips none (above): the same
    statement is "Denied" in a list and unmarked as a citation, until those routes give a path;
  - the path the library builds for a form's node has no degree (it reads only whether the claim is asserted), and
    a node of a class the models do not know is read as a statement there;
  - a headed space's degree has no description shown in the form (its row is gone).
- Tests: Vitest `schema/spaces.test.ts` (75), `components/AssertionMark.test.tsx` (7), `form/HeadDegree.test.tsx` (4),
  the library's `identity.test.ts` (5 more); the workspace's Vitest 765, typecheck, `check:layers`; the modules'
  Vitest and typecheck (`e2e/test_module_unit_tests.py`, 10); `pangloss-interface` and the walk's tests (268); e2e
  `test_assertion_marks.py`, `test_identity.py`, `test_fields_and_wrappers.py`, `test_not_toggle.py`,
  `test_dev_mode.py` (52), `test_code_splitting.py` and `test_lists_and_items.py` (20).

### 7.3b as built (2026-11-26)

On `spaces-7-bands` (from `dev`), by `builder` from main's brief; a second reading with `solidjs-v2-reviewer`.

- **A pattern, not icons** (main's choice, as D17 left it): icons would be six signs to learn, the obvious ones are
  the logician's (¬, □, ◇), and each would widen every tab round a chip. A pattern needs no room and no words, and
  hatching reads as "struck out" untaught.
- **The kind of a space**, `bandKind(facts)` (`schema/spaces.ts`), from the class's own options and not from a path,
  the first that fits: `denies` (`veridical` -1), `forbids` (it prescribes, by a necessity of the negation; found by the second reading: a possibility of the negation, "need not", was read as forbidding, and is now `prescribes`),
  `prescribes`, `necessity` or `possibility` (the force of its modality), `asserts` (`veridical` 1), `plain`.
- **The patterns**: `none`, `hatch`, `cross`, `lines`, `bars`, `dots`, `grid`. By default denies is hatched, forbids
  cross-hatched, prescribes ruled (`lines`), a necessity a grid, a possibility dotted; **asserts and plain have
  none**, so a project that sets no option sees no change, and what a space asserts looks as what is outside any
  space does. `bars` is no kind's default: it is there for a project.
- **How it is changed**: a class by `InterfaceMeta(band="dots")` (`"none"` for none; inherited as the other fields
  are; refused on what is not a semantic space), exported as `interfaceMeta.band`; a project by
  `InterfaceConfig(space_bands={"denies": "cross"})` in an app's `interface_config.py`, kind by kind, the later app
  winning, exported as `spaceBands`. `bandPattern(definitions, name)`: the class's, else the project's for its kind,
  else the kind's. Neither is in `export_models()`, so migrations do not see them.
- **Where it is drawn**: `spaceBand(definitions, name, depth)` (`primitives/kindTint.ts`: the tint as before and the
  pattern's class) at every place a space's band is: the tabs round a chip or a row and the stacked bands
  (`SpaceBands.tsx`), both branches of the item's page, the space's block in a form and the band of the "not"
  toggle, the console's tabs, the sections of the type menu; `data-band` names the pattern where there is one. Not
  the underlay of `ContextFrames`, which is under a band that has it.
- **The pattern itself**: a background image over the tint's colour, in Tailwind's arbitrary values (whole class
  strings; no CSS written), drawn in the band's own text colour at 10% (`BAND_INK`, the one place to tune it): 1px
  lines 7px apart, dots on a 6px tile. Flat: no outline or hairline is changed.
- **Seen in the screenshots, to know**: a band inside a band shows the outer pattern through its own tint (a `Might`
  in a `Not` is dotted over hatching), which reads as both; in the type menu a section for a space inside a space
  (`Not › Might`) has the innermost's band, as it had its tint; under the veil of the tabs round a chip the dots are
  the faintest.
- **Not tested in a browser**: the bands in a form, in the console and in the type menu, and a project's
  `space_bands` (Vitest and pytest only).
- Tests: Vitest `schema/bandKind.test.ts`, `components/SpaceBandPatterns.test.tsx` (10; the workspace 776),
  typecheck, `check:layers`; `pangloss-interface` (209); e2e `test_space_bands.py` and the five files round it (52).
  The e2e project's `Reported` has `band="dots"`.
  The whole of `./run_tests.sh` after the mend: Memgraph 2198, without a database 4810, `pangloss-neo4j` 176, Neo4j
  2091 and one failing (criteria's churn test, a known flake that passed alone), e2e 370.
- **Found by the second reading, and left for the user**: the outer pattern showing through a band inside it (above;
  to stop it a band would need an opaque base, which would also end the adding-up of nested tints); a describing
  necessity of the negation that does not commit ("cannot be", at `veridical` 0) has the grid of "must be"; a
  permission has the ruled lines of an order.

## Phase 8: negatives that record a relation

From [Negatives that record a relation](semantic-space-fields.md#negatives-that-record-a-relation), and, since
2026-11-24, prescriptions too ([the degree of a statement's contents](#the-degree-of-a-statements-contents)): for a
negative, how live the positive was; for an order, a promise or an intention, how likely it was carried out, which is
also evidence that it happened. **Decide first** (D9): its options.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **8.1 `Expectation[T]`** | The citing document, in `pangloss-library` (0.5), of a negative or of a prescription: `statement: Cites[T]`; `how_expected` in five steps (impossible, unlikely, possible, likely, expected), which for a prescription is its degree; `grounds: list[Cites[Statement]]`; `how_defeated` (the ground failed, an exception, not said: [the three kinds](semantic-space-fields.md#whose-expectation-a-negative-answers)); a note; and what was computed when it was judged (8.2, 8.3: the suggestion offered and its grounds), so that **new evidence since it was judged** shows: a changed ground is flagged by its citation ("changed since cited"), and a new statement that bears on it, not among its grounds, by the computed value now differing from the one kept ("new evidence since this was judged", on its card); its migration; a card on the statement's page. If D9 wants the source's side: `Not(answers=..., corrects=...)`, whose expectation the negative answers (the people of the time, the reader, a claim, cited) | Pure: the model and its checks; live: written, cited, "changed since cited"; a statement written after the judgement that changes what is computed shows "new evidence since this was judged" | `builder` | Decide |
| **8.2 The guard of feasibility** | "Impossible" with nobody judging, only where the data says so: a lifespan that does not reach the statement's date (`pangloss-dates`' bounds); a stand-in, or a class the project marks as fictional. **Missing data is "not judged", never "impossible"**: an unknown lifespan says nothing. **Uncertain data stays uncertain**: "impossible" only when even the widest reading of the dates excludes it, "possible" otherwise, with the uncertainty shown. Worked out when shown, so a lifespan recorded later counts at once | Pure: each case, an unknown lifespan and an uncertain one among them; live on the planted world's absences | `builder` | Decide |
| **8.3 Expectations by rules** | Rules of the project (`pangloss-derived`) deriving an "expected at" relation, its grounds read from the justifications; and **rules of authority** for prescriptions: an order from the addressee's superior (in the manmax model, `personreportstoperson` and the offices of `roleoccupation`) raises its degree, a request to a superior or an order from someone with no standing lowers it, and with no such data the degree is the class's default; the e2e project and the demo with one each (a member of a group expected at what the group took part in). **New data counts without anyone asking**: a rule's expectation is derived again when a write touches what it reads (a membership or a whereabouts recorded later makes or strengthens it). **What defeats an expectation cannot be in the rule** (a rule cannot say "unless"), so it is weighed when the expectation is shown: the reason the source gives with the negative (a `Causes`), and statements of classes the project names as defeating a rule of expectation (illness, captivity: an option of the rule, **decide**), found then and not derived. Nothing asks a rule for arithmetic on dates; where the data has nothing that bears on it, the expectation is as the rule gives it, and the person judges the rest. With 4.1 (d): virtual edge classes from denied or prescribed contents ("expected but absent", "was to give to"), and a notable absence from an expectation with its denial, if 0.4 finds a rule can read another's edges. Worked out when shown, stored when confirmed | Live, both backends: the planted world's expected absences found; a vacuous negative given none; a membership written later making an expectation; a defeating statement written later shown against it | `builder` | Decide |
| **8.4 Weighted joins** | The graph part weighs a negated statement's joins by its liveness, and a prescription's contents by their degree (an `Expectation`, a rule's proposal, else the class's default); the empty end joins nothing; the reader looks the value up as it reads citations. The part's signature takes it in | The part's suite; measured on 5.1's world | Main measures, `builder` builds | Decide |
| **8.5 In the interface** | "How expected was it?" on a negative, in five steps, with the computed reasons as chips; on an event's and a person's page, notable absences; in review, a negative judged impossible ("worth recording?") | The module's tests; e2e; `COVERAGE.md` | `builder`; `solidjs-v2-reviewer` (main) | Decide |
| **8.6 Suggested grounds** | A negative's missing grounds suggested for a person to confirm, never where the source undermines them; a suggestion of a statement is new (today only of an entity, `hooks.unconfirmed`) | — | — | Later |

## Phase 9: the demo, the guide, the measurements, the end

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **9.1 The demo** | The fields on its spaces, no migration: `Negative` (`logical="not"`), `Hypothetical` (`Modal("possibility", "epistemic")`), the two subjunctives as commands (`Modal("necessity", "command")`, with `of_not=True` for the negative one; `fit="prescribes"`). `CompareMeta` on its classes (phase 12's 12.7: `Gendering` once per `gendered`; `ChildOf` identifying `child` and `parent`, not recurring; `Sibling` identifying `people`; `MemberOf` recurs; the creation chain once per object; `Activity`, `Transfer`, `Order` recur, identifying the agents); `Addressee()` on `Order.ordered_to`, `Holder()` on `ordered_by`; its judgement class and its migration, read and not applied to `:7688`. **Decide** (D10): split `Negative` into a denial and a "not", or `Order.thing_ordered` into `Ordered[Statement \| Not[Statement]]` (a migration each); whether `Hypothetical` is compared, as "might have". (The demo's database already waits for `pangloss migrate`: library 0005, demo 0027, reconcile 0003.) Stubs made again | The demo's tests; `pangloss check` clean | `builder` | Decide |
| **9.2 The guide** | For modellers: spaces (the four fields, a family class, statement types that bring their spaces, the walk in two examples); comparison (`CompareMeta`, the relations, judgements, learning). For the people who enter data: [the paragraph](semantic-space-fields.md#how-to-explain-it-to-people), as a page a project can hand on | — | `builder`, read by main | To do |
| **9.3 Measured at size** | One run each, bounded, on both backends: the route's lookup at 300,000 nodes (phase 12's 12.10); the second graph part's rebuild and refresh (5.4) beside what phase 13 of the similarity plan lists; 4.1's status on the demo's rules | The floors of 6.2 and 6.6 | Main | To do |
| **9.4 Finished** | "As built" on every step; `implementation_docs/compare.md`; [semantic-spaces.md](semantic-spaces.md), the design pages and [the summary](semantic-spaces-summary.md) say what is built; `status.md`, `packages.md`, `TODO.md`; the skill (`pangloss-compare`'s row, the fields; `check_skill.py`); `/code-review` on the work's diff; `./run_tests.sh` whole | The whole suite | Main, `test-runner` | To do |

## Decisions for the user

Each is asked where its step says **decide**; none blocks the steps before it. On 2026-11-25 the user took main's
proposal for every decision then open (D2 to D11, D16): a step that says **decide** for one of them is decided as
its row says, and what a row leaves to a measurement (D4's graph part, actual network and reconciliation; 6.4's
threshold) is still settled by that measurement and shown to the user.

| | Decision | Step | Proposed |
|---|---|---|---|
| D1 | Fix the fault, and mend stored data by a command or by a migration | 1 | **Decided 2026-11-25**: fixed, by the stored path; a migration |
| D2 | `logical` as force and flavour, the flavour the project's own word | 2.1 | **Decided 2026-11-25, as proposed**: Yes |
| D3 | `Holder()` and `Addressee()` field markers | 2.5 | **Decided 2026-11-25, as proposed**: Yes (fulfilment needs the addressee). **Changed by the user later that day**: one marker on the field that holds the space, `Attribution(by="ordered_by", to="ordered_to")`, naming the person fields ("holder" read as a space holding its contents; the fact is about the space; a class with two spaces can say each). `Holder()` and `Addressee()` are not built; where this plan says them, read `Attribution`'s `by` and `to` |
| D4 | Which packages follow the fields: derived (4.1), criteria (4.2), identity claims (4.3), RDF (4.4); the time part (5.2: `-1` only, or `0` too); the graph part (5.3: what `stop` does, weights); the actual network (5.4); reconciliation (5.5) | 4, 5 | **Decided 2026-11-25, as proposed**: Derived, criteria, identity, RDF; time `-1` only; the rest after their measurements |
| D5 | `orientation` (before or after); and strength, which is now the class's default degree for its contents: a fifth field on `SemanticSpaceMeta`, or each package's slot | 2.1, 6.1, 6.2 | **Decided 2026-11-25, as proposed**: `orientation` in `CompareMeta`; the default degree as a fifth field, since several packages read it |
| D6 | The verdict's relations, fulfilment's matching, and "the same factoid" and "the same source" as features | 6.2, 6.3 | **Decided 2026-11-25, as proposed**: Yes |
| D7 | `EventJudgement`'s verdicts | 6.5 | **Decided 2026-11-25, as proposed**: Agree, disagree, two events, carried out, carried out otherwise, not carried out, breach |
| D8 | The forms: headless spaces (by default, or asked for), "not" as a toggle, marks of what is not asserted | 7.1-7.3 | **Decided 2026-11-25, as proposed**: Asked for, as on reified relations; the toggle; the marks |
| D9 | Negatives and prescriptions: one gradient (the historian's) and the source's side (whose expectation); a prescription's degree as evidence that it happened; where the judgement lives; how it is proposed; which classes of statement defeat a rule of expectation (an option of the rule, weighed when shown); which uses | 8 | **Decided 2026-11-25, as proposed**: `Expectation[T]`, keeping what was computed when judged; the project's rules and the guard; defeating classes named on the rule; the uses one by one |
| D10 | The demo: subjunctives as commands, or split; `Negative` split; `Hypothetical` compared | 9.1 | **Decided 2026-11-25, as proposed**: Commands; no split yet; compared, as "might have" |
| D11 | The profile pairs by vectors use | 6.4 | **Decided 2026-11-25, as proposed**: One of the structural network. **Changed by the user, 2026-11-27**: pairs by vectors are sought through the entities, by the profile the project names for finding who is who (`COMPARE_PROFILE`, by default reconciliation's choice) |
| D12 | The word to start, and phase 12's hold lifted | 0 | **Given 2026-11-25** |
| D13 | A document in the context of what follows it (a `Causes` result and its cause): dropped, or declared on the conjunction and worked out by the view | 1.1 | **Decided 2026-11-25**: declared, when a page first needs it |
| D14 | `meta.context_labels`: removed, every reader moved to the path; or kept beside it for a time | 1.1, 1.2 | **Decided 2026-11-25**: removed where not required; the interface's use first thought about (D17) |
| D15 | The two axes as [the review](#the-review-of-2026-11-25-and-what-it-changed) has them; the degree's range | 3.1, 8 | **Decided 2026-11-25**: that split; `0` to `1`, its sign the walk's lean; in the entry first, outside it as a fallback |
| D16 | The degree in the entry: a `Degree()` marker on a field the project declares, or a field every space has; five steps or a number | 2.7 | **Decided 2026-11-25, as proposed**: The marker; five steps |
| D17 | How the interface shows a path: which kinds of node are shown, the field said or not, what the label flag means, bands by a space's fields | 1.2 | **Decided 2026-11-25**: other kinds passed over for now; the field said; the flag leaves a class out of a trail; bands by a space's fields later, with 7.3; **2026-11-26: a pattern (or icons if suitable ones are found), changeable by a project: step 7.3b** |
| D18 | Whether stored data is carried over a change of what is stored | 1.3, and every later step | **Decided 2026-11-25** (the user): no. The demo can be reset from scratch and nothing else uses Pangloss, so a feature of this plan writes no data migration and keeps nothing that tolerates an older stored shape; a database made before it is made again. The demo project is rewritten whole when the plan is done, at the user's word (so 9.1 is that rewriting, and its migration and D10's are not written) |

## Calls taken

None confirmed by the user. "From" says where each was first taken.

| | Call | Instead of | From |
|---|---|---|---|
| 1 | A stand-in, or what is below an unconfirmed suggestion, is no identifying entity; a pair by vectors needs a real entity in an identifying field of each statement | Trusting the vectors alone | Phase 12, a |
| 2 | Negation and the rest come from the core's four fields; `CompareMeta(compared=False)` stays compare's own choice | `CompareMeta(negates=True)` on spaces | Phase 12, b, replaced |
| 3 | "The same factoid" and "the same source" are features of the verdict, never filters | A ban on two statements of one factoid | Phase 12, c, replaced |
| 4 | `EventJudgement` cites the two statements (`Cites[T]`); a changed one still overrides, with a notice | A plain reference | Phase 12, d |
| 5 | The newest judgement of a pair wins; all are listed | Asking for agreement between judges | Phase 12, e |
| 6 | Any logged-in user may record a judgement | A role | Phase 12, f |
| 7 | Learning is of "one event or two" and of "does this answer that"; the relation itself stays the signatures' table | Learning "one event or two" only | Phase 12, g, widened |
| 8 | A judgement's features are worked out at learning time from the statements as they are | Kept when it is written | Phase 12, h |
| 9 | Places compare as same, different or silent; nested places later | Nesting now | Phase 12, i |
| 10 | History's side by side moves into the interface core, shared | A copy in `pangloss-compare` | Phase 12, j |
| 11 | A pair by vectors links to the merge page; nothing more of reconciliation here | An offer of a reconciliation in the view | Phase 12, k |
| 12 | The fault is fixed first, by the narrower fix, measured to leave the demo's data as it is | The fields first; copying the lists | Spaces plan, a and h |
| 13 | The walk lives in the core, pure; its cases are data shared with the TypeScript port | In `pangloss-compare`; two sets of tests | Spaces plan, b and f |
| 14 | The signature is worked out when read, never stored | A value stored on each node | Spaces plan, c |
| 15 | `unary` is a length of one on `contents` | A validator of its own | Spaces plan, d |
| 16 | A project that sets no field sees no change; the one exception, a date in a `0` space (5.2), is asked | Changing every space at once | Spaces plan, e |
| 17 | Stored data is mended by a command run once | A migration | Spaces plan, g |
| 18 | A positive derived edge class means the positive; virtual relations are classes of their own | One class with a status "denied" | Spaces plan, i |
| 19 | Fulfilment is matched by the addressee and the prescribed thing, its details as targets | "One event?", in which an order's date counts as evidence of two events | Spaces plan, k |
| 20 | The planted world is extended once, for the vector parts and for comparison | A world for each | New |
| 21 | Pairs by vectors use the structural network; reconciliation stays on it | The actual network | New |
| 22 | The judgement of a negative is a citing document in `pangloss-library`, where `EventJudgement` is compare's | Both in one package | New |
| 23 | Missing data is "not judged", never "impossible"; uncertain dates are read at their widest before "impossible"; nothing asks a rule for arithmetic on dates | Counting years from a birth date | The user, 2026-11-24 |
| 24 | What defeats an expectation is weighed when it is shown, not derived (a rule cannot say "unless"); a person's judgement keeps what was computed when it was made, so new evidence since shows | Negation in rules | The user, 2026-11-24 |
| 25 | A statement's degree sits on the veridical axis, for each statement; the class's `veridical` is its default and keeps the logic | The gradient in `veridical` itself, or a scale of its own | The user, 2026-11-24 |
| 26 | For prescriptions the degree is evidence that the contents happened, standing in where no other statement tells; for a denial it is the virtual relation's strength, and the contents stay at `-1` | A prior for comparison only | The user, 2026-11-24 |

## Not in this plan

- **ChatGPT's four fields** (decided against).
- **Phase 12's "not in this phase"**: asking for judgements on the least sure pairs; a list of verdicts across the
  database or a cache of them; nested places; a role part.
- **Search by assertedness** beyond the outline (4.5).
- **`generic` contents and an `Alleged` space**: what the manmax exercise asks for beyond the four; `Alleged` is a
  project's space with `veridical=0`, needing nothing of the core.
- **Spaces over entities**: a rule for modellers, in the guide (9.2), not a check.
- **The rest of the similarity plan's phase 13** (a cheaper overlay on Neo4j), beyond what 9.3 measures.
- **The manmax port.**

## What can go wrong

- **The fix of 1.1 changes what other readers see**: the views' bands, citations, search's `$spaces` and derived read
  the stored lists ([the table](#the-features-this-plan-changes)); their tests run in 1.1.
- **A project mends its data late**: until `pangloss contexts fix` is run, stored paths of the affected shape are wrong
  and so is the walk for them; `check` says how many (`pangloss check` reads no database, and cannot).
- **More pairs, now that one factoid's statements pair**: the pairs are of one statement when it is shown, so they are
  bounded by its factoid and by what names its entities; the cost budget of 6.3 says so.
- **The truth of the planted world for the new relations is made by hand**, and can be made wrong: a handful read by
  hand (5.1) before anything is measured against it.
- **Too many spaces**: the fields make any number cheap to declare; the guide (9.2) says to start from families and
  from statement types that bring their spaces.
- **Flavours spelt two ways**: two flavours never rewritten into each other; 2.2 warns.
- **The walk in two languages**: kept equal by the shared cases.
- **A second graph part doubles a rebuild**: measured (5.4) before it is kept.
- **An event counted twice**: an order's contents at their degree, and a later report of the same event, both count in
  derived and the graph until comparison (phase 6) says they are one; until then, the degree is said beside the fact.
- **Link prediction is circular** unless its vectors come from the actual network: not built here (8.3 uses rules).

## Where the work stands

2026-11-24: **the plan is written; nothing is built.** Steps 0.1 and 0.3 are answered; 0.6 removed (not a question);
0.4, 0.5, 8.1 to 8.3 reworded at the user's word (no arithmetic on dates; incomplete data; new evidence since a
judgement). Last that day: the degree of a statement's contents (a king's order makes its contents likely, and is
often the only evidence), with the steps it changes. Waiting for the user: the
decisions above (D1 to D11) and the word to start (D12), which also lifts phase 12's hold.

2026-11-25: **reviewed; still nothing built.** [The review](#the-review-of-2026-11-25-and-what-it-changed) and the
user's answers: a true path stored in place of the shared lists (phase 1 rewritten, as a proposal for `context.py`:
D13, D14), mended by a migration; the degree out of the walk and an axis of its own (D15); `veridical` defaulting to
what `logical` implies; `EventJudgement` with two named fields; built in three parts, phases 0 to 3 on one branch.
Later that day: D13 and D15 decided, R8 confirmed, and the degree both in the entry (2.7, in the first build) and
outside it as a fallback (R9). Then: D14 (removed where not required) and every other open decision taken as proposed (D2 to D11, D16).
D17 decided, and **the word to start given (D12)**.

2026-11-25, later: **phase 0 done** ([as found](#phase-0-as-found-2026-11-25)). 0.2: `stop` cuts a statement off
from its factoid and nothing else (a test). 0.4: a rule reads another rule's derived documents, not its edges. 0.5:
no type parameter on a top-level document; an abstract base, the project declares the citing fields, a check at
`initialise()`. 0.7: stored `context_labels` hold the node itself and its siblings, as the trial said. Next: 1.1.

2026-11-25, later still: **1.1 built** ([as built](#11-as-built-2026-11-25)): the path, on instances, stored and
read, on both backends, with the migrations that change a tree working the paths out again. Green: the models'
tests, the conformance suite on Memgraph and on Neo4j (1,049 each, with the check of true paths after every test),
and before the last test-only changes the whole of `./run_tests.sh --no-e2e`. **Its second reading (★) was started
and stopped before it reported: still owed**, with the e2e run. Paused at the user's word. Next: the second
reading of 1.1, then 1.2 (two briefs for `builder`).

2026-11-25, later: **1.2 is built** ([as built](#12-as-built-2026-11-25)): `context_labels` is no longer written or
read anywhere, and every reader reads the path or `semantic_spaces`. Green on the whole of `./run_tests.sh --no-e2e`
(both backends; `ty` red only for the user's `semantic_spaces_demo.py`), Vitest, and all of e2e (359), which also
covers what 1.1 still owed of e2e. Three second readings were made (the Python, the interface with the
`solidjs-v2-reviewer` skill, and a search for what was missed). 1.1's own second reading was not made again. Next:
1.3 (main measures at size on a scratch database, then `builder`), then 1.4, then a pause for the user.

2026-11-25, later still: **the user decided that no stored data is carried over (D18)**: the demo can be reset, and
is rewritten when the plan is done. 1.3 is therefore not a migration ([as built](#13-as-built-2026-11-25)): what was
kept for old data is removed. Wherever a later step speaks of a migration of stored data, or of the demo's
database, D18 overrides it. Then 1.4, the docs. The whole of `./run_tests.sh --no-e2e` on both backends and all of
e2e (359) pass after both. **Phase 1 is done; paused for the user.** Next: phase 2, from 2.1 (main).

2026-11-25: **2.1 is built** ([as built](#21-as-built-2026-11-25)). Next: 2.2 (the checks at `initialise()`, `builder` from main's brief).

2026-11-25: **2.2 is built** ([as built](#22-as-built-2026-11-25)), with a sixth refusal (`degree` on a space whose
contents are asserted or denied). Next: 2.3 (`unary` enforced on `contents`, `builder` from main's brief).

2026-11-25: **2.3 is built** ([as built](#23-as-built-2026-11-25)). Next: 2.4 (the fields exported, not migrated;
`builder`).

2026-11-25, after 2.3: the user decided that **no space is empty** (`MinLen(1)` on every space's `contents`; in
"2.3 as built"), and, having weighed one item for every space, that **a space that is not unary may hold several**:
`unary` stays as built. Several items in one space are read each by itself, never together (to be said in 2.6's
docs). The whole suite on both backends and e2e were run for this and passed.

2026-11-25: **2.4 is built** ([as built](#24-as-built-2026-11-25)). Next: 2.5 (the markers `Holder()` and
`Addressee()`, `builder`).

2026-11-25: **2.5 is built** ([as built](#25-as-built-2026-11-25)), as `Attribution(by=, to=)` (D3 changed by the
user). Next: 2.6 (docs and the skill, `builder`, read by main), then 2.7 (`Degree()`).

2026-11-25: **2.6 is written** ([as built](#26-as-built-2026-11-25)). Next: 2.7 (`Degree()`, the last step of phase
2; `builder`), then a pause for the user.

2026-11-25: **2.7 is built** ([as built](#27-as-built-2026-11-25)): **phase 2 is done**, the whole suite on both
backends and e2e green. Paused for the user. Open for them: whether the degree is drawn beside a space's head now or
with 7.3. Next: phase 3 from 3.1 (the walk, main).

2026-11-25, later: the user decided that the degree beside a space's head is drawn with 7.3. **Phase 3 is built**
([3.1](#31-as-built-2026-11-25), [3.2](#32-as-built-2026-11-25), [3.3](#33-as-built-2026-11-25)): the walk,
`pangloss_models.spaces.signature`, pure, with its cases as data; read from what is stored on both backends; the
docs. Green: the whole of `pangloss-models` (1758) and the whole conformance suite on Memgraph and on Neo4j (1060
each); the other packages and e2e were not run again, nothing of theirs being touched. **Phases 0 to 3, the foundation, are done; paused for the user.** Theirs to say: `spaces-foundation` into
`dev`. Next, of the first build: 4.1 to 4.4 on `spaces-4-readers` (each changes behaviour; D4 decided them as
proposed) and 7.1 to 7.3 on `spaces-7-forms`.

2026-11-25, later: the user said to go on. On `spaces-4-readers`: **4.1 (a) and (b) are built**
([as built](#41-a-and-b-as-built-2026-11-25)): each justification of a derived rule has a status from the walk,
and the derivation follows it. Next: 4.1 (c) and (d) by `builder` from main's brief (★), without "likely" and (e),
which are phase 8's; then 4.2 to 4.4.

2026-11-25, later still: **4.1 (c) and (d) are built**
([as built](#41-c-and-d-as-built-and-the-second-reading-2026-11-25)), and the second reading's four findings in
(a) and (b) mended. Next: 4.2 (criteria's `$derived`, `builder`), 4.3 (identity claims), 4.4 (the RDF export).

2026-11-26: **4.3 and 4.4 are built** ([4.3](#43-as-built-2026-11-26), [4.4](#44-as-built-2026-11-26)), and the
walk mended with them ([a space says something of its `contents`
only](#the-walk-mended-a-space-says-something-of-its-contents-only-2026-11-26)). **4.2 is not built**: it waits for
criteria's step 13 ([why](#42-not-built-2026-11-26)). **Phase 4 is done as far as it goes; paused for the user.**
Theirs to say: `spaces-foundation` and `spaces-4-readers` into `dev`. Next, of the first build: 7.1 to 7.3 on
`spaces-7-forms`.

The whole of `./run_tests.sh` on this tree: without a database 4799, `pangloss-neo4j` 176, Memgraph 2193, Neo4j
2091, e2e 359. Five tests failed or erred under the load of the whole run and passed alone, none of them of this
plan: a merge under concurrent writes (`test_merge_concurrent.py`, Memgraph), criteria's churn and via tests (a
`clear_database` teardown, Memgraph), `test_computed.py`'s update and set at once (Neo4j), and the interface's
`.search-types-check-*` race.

2026-11-26, later: the user said to merge and go on. `dev` is at `cf9057ac` (phases 0 to 4, fast-forward), pushed.
On `spaces-7-forms`: **7.1 is built** ([as built](#71-as-built-2026-11-26)). Next: 7.2 (the "not" toggle,
`builder`), then 7.3 (the walk in TypeScript, the marks, the degree beside a space's head, and the library's
`identity.ts`), then pause.

2026-11-26, later still: **7.2 is built** ([as built](#72-as-built-2026-11-26)). Next: 7.3, then pause.

2026-11-26, last: **7.3 is built** ([as built](#73-as-built-2026-11-26)): the walk in TypeScript on the shared
cases, the marks, the degree beside a space's head, the library's reading of claims; and a fault of the Python walk
mended with it (parametrisations of an abstract modality counted). The whole of `./run_tests.sh` before the last two
mends: without a database 4802, `pangloss-neo4j` 176, Memgraph 2198, Neo4j 2092, e2e 369, none failing; the
packages the mends touch run again after them. **7.1 to 7.3 are done: the first build (phases 0 to 4, 7.1 to 7.3)
is complete but for 4.2, which waits for criteria's step 13. Paused for the user.** Theirs to say: `spaces-7-forms`
into `dev`; how a band shows what kind of space it is (D17); what is built next (the second part: phases 5 and 6).

2026-11-26, the user's answers: (1) `spaces-7-forms` into `dev`: **done**, `dev` is at `f37fb212` (fast-forward),
pushed. (2) D17: **a pattern, unless suitable icons are found, with a way for a project to change it**: step 7.3b,
above. (3) **Carry on with phase 5**, unless something outstanding is better taken first. Main's answer: 7.3b first
(small, and it closes phase 7's first part), then phase 5 from 5.1 on a new branch `spaces-5-vectors` made from
`dev`. Nothing else outstanding is worth going back for now: 4.2 waits for criteria's step 13, which is another
plan's (`matches-criteria.md`, to resume at its step 12); the marks on citations' and modules' chips wait for those
routes to give a path, and are small. **Next: 7.3b on a branch `spaces-7-bands` from `dev`, pause; then 5.1 (the
planted world with spaces, main), 5.2 (the time part: `-1` only, D4), and 5.3 to 5.5, each after its measurement.**

2026-11-26, a new session: **7.3b is built** ([as built](#73b-as-built-2026-11-26)) on `spaces-7-bands`: a pattern
over a band's tint by the kind of space, changed by a class or a project. Screenshots shown to the user; **paused
for their word** on the look and on `spaces-7-bands` into `dev`. Next: phase 5 from 5.1 on `spaces-5-vectors` from
`dev`.

2026-11-26, the user's word on 7.3b: the pattern is **left as it is for now** (they are not sure of it; icons may be
preferable; to be reviewed later, with the points the second reading left). One fault of the look mended at their
word, not of this step: in a narrow column the rule down the left of a nested item was flush with its head bar's
left edge, under the rounded corner; it is now 2px in, where the rounding ends (`nestedClass`, `@max-sm:ml-0.5`).
`spaces-7-bands` is pushed and **not merged into `dev`** (the user has not said). **Next, in a new session: phase 5
from 5.1 on `spaces-5-vectors`**, which is made from `spaces-7-bands` (so it holds 7.3b and this page as it stands).

2026-11-26, a new session on `spaces-5-vectors`: **5.1 is built** ([as built](#51-as-built-2026-11-26)): the planted
world for comparison, `planted.world(compared=True)` on `similar_models.declare(compared=True)`, its truth read by
hand and by the walk. `Negative` of the tests' shared models is now a "not" everywhere, so the whole of
`./run_tests.sh --no-e2e` was run: without a database 4823, `pangloss-neo4j` 176, Memgraph 2197 and one failing
(criteria's `test_criteria_churn_live.py`, a write conflict of Memgraph under load, which passes alone and names no
space), Neo4j 2092. The browser tests were not run (nothing of this step reaches them). **Next: 5.2 (the time part:
a date whose statement is denied counts for nothing, D4; `builder`), then 5.3 (main measures first).**

2026-11-26, later: **5.2 is built** ([as built](#52-as-built-2026-11-26)): the time part leaves out a date of a
statement the walk says is denied. `pangloss-dates-vectors` on Memgraph 124, its live tests on Neo4j 32, none
failing; the whole suite was not run again (no other package imports the part). **Next: 5.3, where main measures
first** (the graph part on 5.1's world, with spaces and without: `notes/similarity-evaluation/planted.py` gains
`compared` for it), **and the user decides** what `stop` does and whether a space takes a weight from the walk.

2026-11-26, last: **5.3 is measured, and waits for the user** ([the figures and main's
recommendation](#53-measured-2026-11-26-waiting-for-the-user)): `stop` as it is does nothing for who comes out
alike; cutting a denied statement out mends that and loses every denial for comparison's pairs by vectors; so the
graph part is best left as the structural network, and what the walk says built into 5.4's second part. Nothing of
5.3 is built. **Paused. The user's to say: (1) that, or one network; (2) then 5.4 (its costs measured on both
backends first) and 5.5; or phase 6 first (6.1 and 6.2 need only 5.1).**

2026-11-26, the end of the session: **the user's new thought, the ground of a head class**
([the section](#the-ground-of-a-head-class): G1 whose commitment and whether it can be contradicted, not the truth
axis; G2 by class only; G3 main orders the work), **and the outstanding steps reordered**
([the order from here](#the-order-from-here)). Nothing of the ground is built. 5.3 is still unanswered and holds up
only 5.4, 5.5 and 6.4. **Next, in a new session: 3.4 on a new branch `spaces-ground` made from `spaces-5-vectors`,
then 3.5, 3.6, 5.1b, 4.5, the whole suite, and a pause.**

**To resume (a new session)**: read this page whole, [the review](#the-review-of-2026-11-25-and-what-it-changed)
first, since it overrides older rows, and D18 (no stored data is carried over); then
[the ground of a head class](#the-ground-of-a-head-class) and [the order from here](#the-order-from-here), which
override the order of the older rows; then the last paragraphs above, which say what is built and what is next. Every decision is taken (the table above); what a step still leaves open is
main's to settle and report. One commit for each step, pushed when green, this section and the memory note brought
up to date with it; a pause for the user after each phase. In the working tree and not the plan's: the demo's
`.pangloss/interface/linked/` (generated), `chatgpt-semantic-space-conv.md` and `semantic_spaces_demo.py` (the
user's own): left as they are, never committed.

2026-11-26, a new session on `spaces-ground` (made from `spaces-5-vectors`): **the ground is built**, steps 1 and 2 of
[the order from here](#the-order-from-here): [3.4](#34-as-built-2026-11-26), [3.5](#35-as-built-2026-11-26),
[3.6](#36-as-built-2026-11-26), [5.1b](#51b-as-built-2026-11-26), [4.5](#45-as-built-2026-11-26), each committed
and pushed, 3.5 and 4.5 with a second reading whose findings are mended. **The user answered 5.3: two networks, as
main recommended** (the graph part stays the structural network, unchanged; what the walk says goes into 5.4's
actual network). The whole of `./run_tests.sh` on `e037ceee`: ruff clean; `ty` red only for the user's
`semantic_spaces_demo.py`; Memgraph 2211; without a database 4912 and one failing (the interface's
`.search-types-check-*` race, which passes alone and is not of this branch); `pangloss-neo4j` 176; Neo4j 2105; e2e
370. **Paused for the user.** Theirs to say: `spaces-ground` and what it stands on (`spaces-7-bands`,
`spaces-5-vectors`) into `dev`; the names `Ground`, `standing`, and the RDF predicates `pgo:standing` and
`pgo:accordingTo` (main's, 4.5); whether the identity clusters should follow a ground of 0 as they now do (3.5).
**Next: phase 6 on `compare-6`** (6.1 by `builder` beside 6.2 by main, then 6.3, 6.5, 6.4, 6.6); 5.4 and 5.5 can go
between any two of its steps now that 5.3 is answered (5.4's costs measured on both backends first); how a ground
is shown in the interface is talked through with the user before 7.4 to 7.6.

2026-11-26, the user's word: **`spaces-ground` into `dev`** (fast-forward, with `spaces-7-bands` and
`spaces-5-vectors` under it), pushed. **Next, in a new session: 5.4 and 5.5** on a branch `spaces-5-networks` made
from `dev`, **the costs of 5.4 measured first and shown to the user before anything is built** (a second rebuild's
and refresh's cost on both backends; how the nearest neighbours differ on the planted world). Phase 6 after it.

2026-11-26, a new session on `spaces-5-networks` (made from `dev`): **5.4 is measured, and waits for the user**
([the figures and main's recommendation](#54-measured-2026-11-26-waiting-for-the-user)): a second graph part by the
rule "by-walk" doubles a rebuild (Memgraph 310 s and 311 s more, Neo4j 161 s and 149 s more) and a turn of the
worker, the walk itself costing nothing that shows; the neighbours differ as 5.3 said. Nothing is built: the part
is a trial in `notes/similarity-evaluation/actual_network.py`. The world at size is still in two stopped scratch
containers (`pangloss-memgraph-compared`, `:7716`; `pangloss-neo4j-compared`, `:7717`). **Paused. The user's to
say: build 5.4 so; one profile or two (what would set `who_belonged` apart). Then 5.5, then phase 6.**

2026-11-27: the user's word: **build 5.4 as measured, `who_met` alone** (`who_belonged` dropped until a case says
what sets it apart). **5.4 is built** ([as built](#54-as-built-2026-11-27)): the second part `"actual"` in
`pangloss-fastrp`, idle unless a profile weighs it. Run one after another, not by `./run_tests.sh`: ruff and the
skill check clean; `ty` red only for the user's `semantic_spaces_demo.py`; Memgraph 2232; without a database 4958;
`pangloss-neo4j` 176; Neo4j 2126; none failing. The browser tests were not run (nothing of the interface is
touched). **`./run_tests.sh --no-e2e` itself did not finish in three attempts that night** (the Memgraph run at 58%
after two hours, its parts side by side; each part alone is as fast as ever): not explained, and not of this step
as far as was found. **Next: 5.5** (`builder`), then phase 6 on `compare-6`.

2026-11-27, later: **5.5 is built** ([as built](#55-as-built-2026-11-27)): the warning when reconciliation's profile
weighs the actual network and not the structural one. `pangloss-reconcile` on Memgraph 545, ruff and `ty` clean;
nothing else run again (the change is one check of the settings). **Phase 5 is done** (5.1 to 5.5). **Paused for
the user.** Theirs to say: `spaces-5-networks` into `dev` (a clean `./run_tests.sh` first, which did not finish
on 2026-11-27); whether the choice of a profile without `RECONCILE_PROFILE` should leave `actual` out of its count.
**Next: phase 6 on `compare-6`** (6.1 by `builder` beside 6.2 by main, then 6.3, 6.5, 6.4, 6.6); 6.4 (pairs by
vectors) is of the structural network, by 5.3.

2026-11-27, a new session on `compare-6` (made from `spaces-5-networks`, not `dev`: it holds the plan as it stands):
**6.1 and 6.2 are built** ([6.1](#61-as-built-2026-11-27), by `builder`; [6.2](#62-as-built-2026-11-27), main):
the package `pangloss-compare` with `CompareMeta` and its checks, and the verdict on two statements with no
database, which reads 99.9% of the planted pairs as the truth has them. The package's 83 tests on Memgraph, ruff
and the skill check are green; `ty` red only for the user's file. Nothing else was run (nothing else imports the
package but `similar_models.declare(compared=True)`, whose users' tests the builder ran). **Next: 6.3** (pairs by
rule: main plans the query at size on `:7716` and `:7717`, then `builder` ★), then 6.5, 6.4, 6.6.

2026-11-27, later: **6.3 is built** ([as built](#63-as-built-2026-11-27); the query
[measured first](#63-the-query-measured-before-the-brief-2026-11-27), and again as built: 4 to 9 ms for a
statement's pairs with their verdicts at 2.7M nodes), with a second reading whose one real finding is mended.
**6.4 is measured and waits for the user** ([the figures](#64-measured-2026-11-27-waiting-for-the-user)): a
statement's own vector does not find what the rule cannot; main recommends asking of the entities. **6.6 is
measured before its brief** ([the figures](#66-measured-before-its-brief-2026-11-27)): a fit needs the hand-set
score among its features. **Next: 6.5** (`EventJudgement` and the route; `builder` ★), then 6.6.

2026-11-27, later still: **6.5 is built** ([as built](#65-as-built-2026-11-27)): `EventJudgement`, and
`GET /api/compare/{type}/{ref}`, in which a person's judgement overrides what is worked out; the second reading's
finding (what is superseded, once judgements are in) is mended. Left for the user there: whether a judgement may be
edited, and what "newest" then means; field names as Python has them. **Next: 6.6** (learning from judgements,
with the hand-set score among the features, as measured), then the whole suite and a pause; 6.4 waits for the
user's answer.

2026-11-28: **6.6 is built** ([as built](#66-as-built-2026-11-28)), all but the class defaults of the degree,
which go with phase 8: two fits of people's judgements, each a correction of the hand-set score, used when no
worse held out; `pangloss compare learn` and `status`, the admin job, and the route saying which fit it used. The
second reading's finding is mended. **Phase 6 is built but 6.4**, which waits for the user
([the figures](#64-measured-2026-11-27-waiting-for-the-user)), and 6.7, which is with phase 8.

2026-11-28, later: **the whole suite on `7fcd6d80`**, its parts one after another (`test-runner`; not
`./run_tests.sh` in one go, which did not finish on 2026-11-27): ruff, the skill check and the stubs' check clean;
`ty` red only for the user's `semantic_spaces_demo.py`; without a database 5,096 and two failing; Memgraph 2,275
and one failing; `pangloss-neo4j` 176; Neo4j 2,170; e2e 370. Of the three failures, **one was of this branch**: the
test that every app with commands is in the guide's list (`pangloss-cli`, `test_cli_guide.py`) did not have
`pangloss_compare`; mended and green (101). The other two pass alone and are of load: the SDK server's
`test_git.py` (its server not up within ten seconds) and the conformance `test_merge_concurrent.py` (a merge that
gave way to other writes until it ran out of time, Memgraph's writes at 16 s under four workers). **Paused for the
user**: 6.4, and the questions the steps left ([6.5](#65-as-built-2026-11-27), [6.6](#66-as-built-2026-11-28));
`compare-6` and `spaces-5-networks` into `dev`. **Next, at the user's word**: 6.4 as decided, then 7.4 to 7.6 (the
comparison in the interface), how a ground is shown talked through first.

2026-11-27, a new session: **the user's word on 6.4: by the entities, as main recommended, D11 changed; measured
first** ([the figures](#64-the-entities-measured-2026-11-27-shown-to-the-user-before-building)): it finds seven to
nine in ten of the planted births the rule cannot, the score does not tell a right entity from a namesake, the
verdict sorts out all but one pair in 500 of the wrong ones, and it costs about 0.5 to 0.9 s a statement. Nothing
is built. **Paused for the user**: the four proposals under the figures (the settings; which pairs are given;
asked for apart; "once per" certain or weighed). **Next, at their word**: the brief for `builder`, 6.4 built with
a second reading, then 7.4 to 7.6.

2026-11-27, later: the user took the four proposals. **6.4 is built** ([as built](#64-as-built-2026-11-27)):
`?near=true` on the route gives the pairs through near entities, each conditional on two entities being one. **Phase
6 is built but 6.7**, which is with phase 8. **Paused for the user**: what 6.4 left (the cut before the verdict; the
hash-seed test of 6.6), the questions of 6.5 and 6.6 still open, and `compare-6` and `spaces-5-networks` into `dev`.
**Next, at their word**: 7.4 to 7.6 (the comparison in the interface), how a ground is shown talked through first.

2026-11-27, later still: **the user answered every open question of phase 6**
([the answers](#phase-6-the-questions-answered-2026-11-27)), and **they are built**
([6.8 as built](#68-as-built-2026-11-27)). Left for the user there: the check before a fit is used cannot tell a
bad fit when judges are sometimes wrong; a statement naming both X and X′ gives no pair through X′ (main's call).
**Next, at their word**: 7.4 to 7.6, how a ground is shown and what a person may say (D7's seven) talked through
first.

2026-11-27, last: **the whole suite on 6.8, by itself**: Memgraph 2,298 passed and 1 failed
(`test_merge_concurrent.py`, "conflicting transactions" under load; passed three times alone; not of this step),
without a database 5,149, `pangloss-neo4j` 176, Neo4j 2,193, the browser tests 370. **`spaces-5-networks` and
`compare-6` are in `dev`** (fast-forward to `24ea141e`, pushed). The Memgraph part took 33 minutes where it took
about 6: not looked into.
