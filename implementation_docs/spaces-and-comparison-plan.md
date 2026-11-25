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
- The features this plan changes
- The order
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

- **2.7 (new), a degree in the entry**: a field marker `Degree()` (`markers.py`, as `Holder()` in 2.5) on a field of
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
| **2.4 Exported, not migrated** | `export.py` gives a space's `veridical`, `fit`, `logical` (`{"not": true}` or `{"force", "flavour", "ofNot"}`) and `unary`; `interface-core/src/types/models.ts` has them; `make-stubs` knows `Modal`. The migrations' snapshot (`migrations/diff.py`, its list of keys) is left as it is: the fields are not data | Pure: the export; `packages/pangloss-interface/tests/test_models_match_typescript.py`; a change of `veridical` makes no migration | `builder` | To do |
| **2.5 `Holder()` and `Addressee()`** | Field markers (`markers.py`, `FieldMarker`) on a relation of a statement class: who holds the attitude or gives the order, and to whom; at most one of each on a class, on a relation to agents, found through a reified relation (a proxy) by the code search already uses to reach what is behind a wrapper (`pangloss_models.search`). Exported (on a relation a marker is kept on the field's definition today, not exported). **Needed by fulfilment (6.2)**; **decide** (D3) | Pure: the checks; the marked fields of a class read through wrappers; the export | `builder` | Decide |
| **2.6 Docs and the skill** | [semantic-spaces.md](semantic-spaces.md) (the fields, ✅), [models.md](models.md), `imports.md`, the guide's statements page (`guide/tutorial/04-statements.md`), `status.md`; the skill's `references/modelling.md` (a new `Meta` option is one a newcomer needs to be told), and `check_skill.py` | The skill's check | `builder`, read by main | To do |

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
- Not done: the docstring of `PanglossModelWarning` still speaks only of what the generated models cannot carry
  (2.6); a `Meta(` whose bracket is on a later line than the name gets no fix where the fix would add the first
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

## Phase 3: the walk

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **3.1 `pangloss_models.spaces`** | `signature(path) -> Signature` (rewritten 2026-11-25, R1 and R2): from a node's stored path (1.1), which says which of its nodes are spaces and which are statements between them; each run of spaces next to each other normalised ([the table](semantic-space-fields.md#logical): within one flavour; `of_not`; a double "not"); then [the walk](semantic-space-fields.md#veridical): `veridical`; for an uncommitted path its lean (for, against, neither) and the default degree of the class of its innermost space. **No statement's own degree**: a caller that has one (phase 8's hook) weighs with it; the walk reads no database; the `fit` of the innermost space that prescribes; the id of the statement holding it; the force and flavour of the innermost modal. Reads the classes' meta from the registry; no database | Pure: every row of the walk's table and of the normalising table; the two limits (two flavours never rewritten into each other; a statement between two spaces stops it); `Not[ChurchService(parts=[p])]`, which the flat list gets wrong. The cases are data (`space_cases.json`, beside the models' `label_cases.json`), which the TypeScript port (7.3) passes too | Main | To do |
| **3.2 Read from what is stored** | Where a package's query reads only `semantic_spaces`, it reads the path (`meta.path`) too: derived's `compile.py` (4.1), the library's clusters (4.3), the time part's rows (5.2) | Pure: the signature of a node read back (1.1's conformance write) | Main | To do |
| **3.3 Docs** | [semantic-spaces.md](semantic-spaces.md): `signature`, what it gives, with three examples | — | Main | To do |

**Worked out when read, never stored**: a change of a space's fields changes nothing stored and needs no migration.
What waits on that is search's `$asserted` (4.5).

## Phase 4: the packages that read spaces

Each step is one package, backend-neutral, with its own tests on both backends, and **each changes behaviour, so
each is decided by the user before it is built** (D4). A project that sets no field sees no change.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **4.1 Derived** | As [Derived edges through spaces](semantic-space-fields.md#derived-edges-through-spaces) says. (a) The rule's query reads the matched nodes' `context_labels` beside `semantic_spaces` (`compile.py`), and each justification gets its status from the walk over the node's path and the wrappers on the rule's own paths: asserted, denied, uncommitted leaning for or against, prescribed, or saying nothing. (b) The derivation follows the status (asserted: through; uncommitted or prescribed: qualified; denied, or leaning neither way: blocked) unless a wrapper's own `DerivedMeta` says otherwise. (c) The status kept on each justification and summed up on the fact (asserted, contested, **likely** (prescribed contents whose degree is above a setting: a fact from a royal order counts as a weighted fact, not only as a virtual edge), reported, prescribed, denied only), `plain` kept; in the views, the API's filters, `why`, `export`, `graph` and derived's RDF. (d) A rule option to take only justifications of a status, for virtual edge classes. (e) The degree (and, for a denial, the liveness) as a `PerJustification()` value (8.4) | Pure: the status of the walk's cases. Live, both backends: a rule over a purchase in a `1`, a `0` and a `-1` space; `Not[Not[...]]` plain and `Not[Known[...]]` nothing; a contested fact; `DerivedMeta` winning. On the demo's data (read, not applied): of its 34 `GaveTo` edges, the 3 from ordered gifts prescribed, the 1 from a forbidden gift blocked, the other 30 as they are | Main (a, b), `builder` (c to e) ★ | Decide |
| **4.2 Criteria's `$derived`** | Its filter of facts by their justifications' context labels follows 4.1's status: a description that asks for what is plain gets what is asserted; one may ask for a status | Live, both backends: a description over a contested fact and over a prescribed one | `builder` | Decide |
| **4.3 Identity claims** | A `SameEntity` whose path is `1` joins as if it were in no space; one whose path is `-1` is a claim that the two are different, given apart in the cluster ("said to be different"), not joining. `clusters.py` reads `context_labels` too; `identity.ts` shows it | Live, both backends: each case; a claim in a `0` space as today | `builder` | Decide |
| **4.4 The RDF export** | What is inside a space whose path is `1` has its direct triples (today nothing inside any space does); `0` and `-1` as today. `convert.py` walks the tree itself, so it asks the walk of each node's path as it goes | The RDF package's tests: a `Known[...]` statement asserted; a `Not[...]` one not | `builder` | Decide |
| **4.5 Search's `$asserted`** (outline) | A condition on a document's pattern: needs the value on the node (stored at write, and so a migration whenever a space's fields change) or a filter after the query (slow on large results). Not built until a page needs it | — | — | Later |

## Phase 5: the vector parts

Changes to parts that are built, under the similarity plan's discipline: each part keeps passing its suite
(`pangloss_testing.parts.PartSuite`), takes the fields into its signature (so a rebuild is due once), and is measured
on the planted world before a default is chosen.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **5.1 The planted world with spaces** | `planted.world(..., compared=True)` with `similar_models.declare(compared=True)`, made once for this phase and phase 6: phase 12's cases (a once-per class; a general and a specific class; other reports that disagree; `Negative` reports; `Hypothetical`; the series kept) and these: reports in `Reported` and `Believed` leaning each way; "cannot have been" (`Not[Might[...]]`); orders carried out on time and late, not carried out, orders not to kept and broken; permissions used; two normative orders; absences that were expected (members of a group missing from its events) and absences that were not; a source contradicting itself in one factoid; an order and what came of it in one passage; one event entered twice in a factoid. The truth (`world.verdicts`) has the relation of each pair, and the liveness of each negative | Pure: the same seed, the same world; each kind of pair present in a share near the one asked; the truth holds for a handful read by hand | Main | To do |
| **5.2 The time part** | A date counts for nothing when its statement's path is `-1`, and a date of prescribed contents counts at their degree (the date of what a king ordered helps date the act); **decide** (D4) whether an uncommitted date with no degree counts, which changes every project with statements in spaces (and answers the open item of the similarity plan's step 9.3). `counts_for` (`pangloss_dates_vectors/part.py`) reads `context_labels` | Pure (`counts_for`); the part's suite (`dated=True`); a statement in `Not` has no time vector | `builder` | Decide |
| **5.3 The graph part's `stop` and weights** | From 0.2: if a negated statement is still joined to its people, what `stop` should do (end the statement's own joins too, or an option of its own); whether a space with no `FastRPMeta` takes a weight from the walk: the degree (asserted 1, a royal order's contents likely, a stranger's hardly at all, denied: what `stop` decides). Measured on 5.1's world, against the same world without spaces: who comes out alike | Pure (the maps, the joins); the part's suite; the measurement written into the step | Main measures, `builder` builds | Decide |
| **5.4 The actual network** | A second graph part in which a node joins at its degree (the walk in the graph's reader): asserted in full, a prescription's contents at their degree, a denied or a vacuous one not at all, beside the structural one (virtual relations weighed: 5.3, 8.4); profiles `who_met` and `who_belonged`. Measured: a second rebuild's and refresh's cost on both backends; how the nearest neighbours differ on 5.1's world | The part's suite for the second part; the measurement | Main measures, `builder` builds | Decide |
| **5.5 Reconciliation's network** | `RECONCILE_PROFILE` stays a profile of the structural network (for "who is this?", co-mention in a denial is good evidence of the same world); said in `reconcile.md` and checked at `initialise()` if the actual part is installed (a warning when the profile weighs only it). A claim that two are different (4.3) as a reason against a candidate: later | Pure: the warning | `builder` | Decide |

## Phase 6: `pangloss-compare`

Phase 12 of the similarity build plan, rewritten on the four fields: its user's answers hold, its calls b, c and g are
replaced (below), and its steps are these.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **6.1 The package and `CompareMeta`** | `pangloss-compare`, scaffolded as the testing list's item 10 says; its `tests/live` in `run_tests.sh`. `CompareMeta(identifying=[...], once_per=None \| "field", recurs=False)`, the slot `_compare_meta`, inherited; a class without `identifying` is not compared. On a space only `compared=False` (its statements left out): negation and the rest come from the four fields, so phase 12's `negates` goes. A weight for each space class (strength: an order more than a recommendation), unless D5 puts strength in the core. Checks at `initialise()` as phase 12's 12.2 has them (each field the class's; an identifying field reaches an entity, through wrappers, by the code search already uses (`held_field_names`, `wrappers_of`); `once_per` one of `identifying`; `once_per` and `recurs` not both; a narrowed field counts as the field it narrows, as the field definitions say) | Pure: every refusal by its message; inheritance; a narrowed field; an identifying field behind an `InRole` and behind an identification's alternatives; `compared=False` on a space | `builder` from main's brief, after 0.5 | To do |
| **6.2 The verdict, pure** | `maths.py`, no database. (a) The contents' verdict as phase 12's 12.3 has it: the nearest common class; field by field (same, different, one silent; dates overlapping, nested or apart beyond both uncertainties, from `Bounds`); one event by once-per, else a hand-set logistic of the date gap, the place, the people in common and different, `recurs`, sources differ, **the same factoid** and **the same source**. (b) The two signatures (3.1), and the relation by [the table](semantic-space-fields.md#how-it-works-with-similarity): agree or disagree, contradiction, support, tension, compatible or at odds, carried out (as prescribed, or otherwise), done but not carried out, not carried out, breach, complied with, permission used, reportedly carried out, conflict, two orders at odds, nothing. (c) Fulfilment's [own matching](semantic-space-fields.md#pairs-within-one-factoid-and-what-carries-out-an-order): the addressee (2.5) doing the prescribed thing after it was prescribed (`orientation`, D5), the prescribed details compared as targets (on time, late, early, elsewhere, in part). (d) A relation within one source says so. (e) The degree weighs the relation: an order with no other evidence still supports a later report that it happened; a failure to carry it out is the more notable, the higher the order's degree; once another statement tells what happened, it decides | Pure: phase 12's cases (a general and a specific class; once per; recurring; negated), each by name; every row of the relation table; Tuesday and Wednesday (carried out, a day late); a source contradicting itself; a seeded floor on 5.1's world (phase 12's trial gave 95 to 98% on "one event"; the floor a little under what is measured) | Main | To do |
| **6.3 Pairs by rule** | `pairs(statement)`, as phase 12's 12.4 without "in other factoids": the statement's identifying entities, **real entities only** (no stand-in, nothing below an unconfirmed suggestion; a merged entity followed to the one kept); statements of related classes naming one of them in the same identifying field, that the reader may see. Beside them, for a prescription, the statements that may answer it: the addressee's, of the prescribed class or below, after it. The query planned on both backends at size (`:7702`, `:7706`) before the brief names it | Live, both backends: each rule by name (a stand-in never pairs; a suggestion not confirmed never pairs, and does once confirmed); two statements of one factoid pair; an unpublished factoid and a reader not logged in; a merged entity; **nothing written** (nodes, edges, `PGPending` before and after); a cost budget in `test_query_costs.py` | Main, then `builder` ★ | To do |
| **6.4 Pairs by vectors** | As phase 12's 12.5 without "less those of the same factoid": `nearest(of=statement, types=related classes, k=COMPARE_NEAR_K)` above `COMPARE_NEAR` (measured), less those 6.3 has; never through a stand-in (main first measures on 5.1's world with `stand_in=True` whether stand-ins pull statements together). Through a profile of the **structural** network (D11): a pair by vectors says why ("one event if X and X′ are one person") and links to merging the two | Live: a pair found only by vectors; none by a stand-in; none without `pangloss-vectors`; the reader's visibility as 6.3; nothing written | Main (measure), then `builder` | Decide |
| **6.5 `EventJudgement` and the route** | `EventJudgement[T]` in `pangloss-compare`, named by the project with its own root (0.5): two citing fields with roles (R7: `statement: Cites[T]` and `other: Cites[T]`, the prescription first where one is; the names in the brief), not a list of two; `verdict`: agree, disagree, two events, carried out, carried out otherwise, not carried out, breach (**decide**, D7); `fields`: the fields disagreed on or the targets missed; `note`. `GET /api/compare/{type}/{ref}`: the pairs (6.3, 6.4), each with its relation (6.2), how it was found, and whether it is within one source; a person's judgement of a pair overrides (the newest wins, all listed with who and when; one on a statement changed since cited still overrides, with that notice). A judgement is written by the ordinary `POST` of its class, logged in; nothing else is written | Live, both backends: a judgement overrides; the newest wins; changed since cited; nothing written by a lookup, on the error paths too; the reader's visibility; a judgement the reader may not see does not show | `builder` ★ | To do |
| **6.6 Learning from judgements** | `pangloss compare learn` (`--dry-run`) and an admin job: each judgement is an example of "one event or two" (agree and disagree yes, two no) or of "does this answer that" (carried out, otherwise, not); its features worked out from the statements as they are now (a judgement on a statement changed since cited left out, and counted), among them the same factoid, the same source and the pair of signatures; `compare_calls` against the hand-set logistic; a `PGCompareModel` (one per fit, none deleted, one in use, the features' signature kept), written only past `COMPARE_LEARN_FROM` judgements (100) and when no worse; the route then uses it and says so. And the class defaults of the degree (D5) are learnt from how often prescriptions of each kind, and from each kind of holder, were carried out. Main first: on 5.1's world, how many judgements equal the hand-set rules, and how many cut mistakes by a third | Pure: reproducible; the planted figures as floors. Live: none, too few, a fit, a worse one refused, a model of another signature not used | Main, then `builder` ★ | To do |
| **6.7 Liveness in the verdict** | With 8.1 to 8.3: a contradiction between a denial and an assertion weighed by the denial's liveness; "expected, and did not" as a relation of its own (a notable absence) | Pure: the weights; live: a notable absence on the route | `builder` | After 8.3 |

## Phase 7: the interface

**Decide first** (D8): which of 7.1 to 7.3, and whether a headless space is the default or asked for by
`InterfaceMeta(headless=True)` on the space, as on a reified relation. Every step: its text as `t()` slots with
translations, a row of `e2e/COVERAGE.md`, the dev build (`e2e/test_dev_mode.py`), and `solidjs-v2-reviewer` on the
diff.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **7.1 A space with no choice, headless** | `headlessIn` (`schema/headless.ts`) takes a semantic space too: in a field that can hold that space and nothing else, one of it, and must (`Order.content: Ordered[...]`). The form (`ModelFields.tsx`) draws its contents with no head bar; the view (`ItemContents.tsx`) keeps the band and its colour | Vitest (`headless.test.ts`); e2e on the e2e project's models | `builder` | Decide |
| **7.2 "Not" as a toggle** | Where a field or a space's contents offers `X \| Not[X]` (a space with `logical="not"`), a "not" toggle on the item wraps it in the space or takes it out, client-side (as the retyping of nested documents does), in place of the space's section of `TypeMenu` | Vitest; e2e: on, saved, read back inside `Not`; off | `builder` | Decide |
| **7.3 What is not asserted, marked** | The walk ported to TypeScript (`interface-core`, pure), passing `space_cases.json` (3.1); a statement whose path is not `1` marked where it is listed without its band (search results, a person's statements) | Vitest on the shared cases; e2e: a statement in `Not` marked in a list | `builder` | Decide |
| **7.4 "Compared"** | A module of `pangloss-compare` (phase 12's 12.7): an item section on a statement's page, as "Similar" is: each pair's relation (by rule or by vectors, within one source or not), a judgement's chip; on an order's page, "Carried out?" | The module's unit tests; `e2e/test_compare.py` on the e2e project's models | `builder` | To do |
| **7.5 Side by side, and recording** | Phase 12's 12.8: `align` and `AlignedCell` moved from `pangloss-history` into `interface-core` (history imports them; its tests unchanged), with a pairing of parts by field and place where there are no shared ids; a page `/compare/:type/:a/:b` (a module route), the two statements on the fields of their nearest common class, the relation above (for a fulfilment, each target met or missed); logged in, a judgement recorded (6.5) and the page showing it; from a pair by vectors, a link to merging the two entities | Unit tests of the pairing; e2e: each verdict recorded, the section changes; history's e2e unchanged | `builder` | To do |
| **7.6 "Similar" by relation** | `pangloss-vectors`' section keeps its order, by content, and labels each statement by its relation to this one (6.2): "contradicts", "carried out", "reported", "might have"; filters "only what the sources assert" and "only contradictions" | The module's tests; e2e | `builder` | To do |
| **7.7 Derived's status shown** | Derived's section (`DerivedSection.tsx`) gives a fact's status ("asserted by two, denied by one") from 4.1 | The module's tests; e2e | `builder` | After 4.1 |

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
| D3 | `Holder()` and `Addressee()` field markers | 2.5 | **Decided 2026-11-25, as proposed**: Yes (fulfilment needs the addressee) |
| D4 | Which packages follow the fields: derived (4.1), criteria (4.2), identity claims (4.3), RDF (4.4); the time part (5.2: `-1` only, or `0` too); the graph part (5.3: what `stop` does, weights); the actual network (5.4); reconciliation (5.5) | 4, 5 | **Decided 2026-11-25, as proposed**: Derived, criteria, identity, RDF; time `-1` only; the rest after their measurements |
| D5 | `orientation` (before or after); and strength, which is now the class's default degree for its contents: a fifth field on `SemanticSpaceMeta`, or each package's slot | 2.1, 6.1, 6.2 | **Decided 2026-11-25, as proposed**: `orientation` in `CompareMeta`; the default degree as a fifth field, since several packages read it |
| D6 | The verdict's relations, fulfilment's matching, and "the same factoid" and "the same source" as features | 6.2, 6.3 | **Decided 2026-11-25, as proposed**: Yes |
| D7 | `EventJudgement`'s verdicts | 6.5 | **Decided 2026-11-25, as proposed**: Agree, disagree, two events, carried out, carried out otherwise, not carried out, breach |
| D8 | The forms: headless spaces (by default, or asked for), "not" as a toggle, marks of what is not asserted | 7.1-7.3 | **Decided 2026-11-25, as proposed**: Asked for, as on reified relations; the toggle; the marks |
| D9 | Negatives and prescriptions: one gradient (the historian's) and the source's side (whose expectation); a prescription's degree as evidence that it happened; where the judgement lives; how it is proposed; which classes of statement defeat a rule of expectation (an option of the rule, weighed when shown); which uses | 8 | **Decided 2026-11-25, as proposed**: `Expectation[T]`, keeping what was computed when judged; the project's rules and the guard; defeating classes named on the rule; the uses one by one |
| D10 | The demo: subjunctives as commands, or split; `Negative` split; `Hypothetical` compared | 9.1 | **Decided 2026-11-25, as proposed**: Commands; no split yet; compared, as "might have" |
| D11 | The profile pairs by vectors use | 6.4 | **Decided 2026-11-25, as proposed**: One of the structural network |
| D12 | The word to start, and phase 12's hold lifted | 0 | **Given 2026-11-25** |
| D13 | A document in the context of what follows it (a `Causes` result and its cause): dropped, or declared on the conjunction and worked out by the view | 1.1 | **Decided 2026-11-25**: declared, when a page first needs it |
| D14 | `meta.context_labels`: removed, every reader moved to the path; or kept beside it for a time | 1.1, 1.2 | **Decided 2026-11-25**: removed where not required; the interface's use first thought about (D17) |
| D15 | The two axes as [the review](#the-review-of-2026-11-25-and-what-it-changed) has them; the degree's range | 3.1, 8 | **Decided 2026-11-25**: that split; `0` to `1`, its sign the walk's lean; in the entry first, outside it as a fallback |
| D16 | The degree in the entry: a `Degree()` marker on a field the project declares, or a field every space has; five steps or a number | 2.7 | **Decided 2026-11-25, as proposed**: The marker; five steps |
| D17 | How the interface shows a path: which kinds of node are shown, the field said or not, what the label flag means, bands by a space's fields | 1.2 | **Decided 2026-11-25**: other kinds passed over for now; the field said; the flag leaves a class out of a trail; bands by a space's fields later, with 7.3 |
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

**To resume (a new session, on `spaces-foundation`)**: read this page whole, [the review](#the-review-of-2026-11-25-and-what-it-changed)
first, since it overrides older rows; then the first part of [the order](#the-order). Every decision is taken (the
table above); what a step still leaves open is main's to settle and report. Begin with phase 0: 0.2 and 0.7 by main,
0.4 and 0.5 by two `Explore` agents at once; then phase 1 (1.1 by main, with a second reading). One commit for each
step, pushed when green, this section and the memory note brought up to date with it; a pause for the user after
each phase. In the working tree and not the plan's: the demo's `.pangloss/interface/linked/` (generated),
`chatgpt-semantic-space-conv.md` and `semantic_spaces_demo.py` (the user's own): left as they are, never committed. The first things then: this branch into `dev`; 0.2 and 0.7 by main, 0.4 and 0.5 by two `Explore`
agents at once.
