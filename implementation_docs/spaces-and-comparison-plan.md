# Semantic spaces and comparison: the build plan ⏳

Written 2026-11-24, at the user's word: **one plan** for the fields of a semantic space and for the comparison of
statements, with every feature they change. It takes the place of two plans, both kept as they were written with a
note at their head: [semantic-spaces-plan.md](semantic-spaces-plan.md) (its phases 0 to 8), and the steps of phase 12
of [the similarity build plan](similarity-build-plan.md#phase-12-pangloss-compare) (12.1 to 12.10, rewritten here as
phase 6). **Nothing here is built, and nothing is to be built without the user's word.** Phase 12 is on hold at the
user's word (`TODO.md`), and this plan with it.

The design is in [the fields of a semantic space](semantic-space-fields.md) (the four fields, the walk, similarity,
negatives that record a relation, derived edges, the manmax exercise), [the report](semantic-spaces-formalisation.md)
and [the summary](semantic-spaces-summary.md); for comparison, in [similarity-plan.md](similarity-plan.md) (stages 11
and 12) and [graph-embeddings.md](graph-embeddings.md) ("Judgements at lookup"). The numbering of phases 0 to 4 and 8
is that of the plan it replaces, so that the design pages' references to them still hold.

## Contents

- What is taken as settled
- What was found before the steps
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

## The degree of a statement's contents

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

- **0 to 3 are the foundation**, small and in the core; 1 is worth doing alone, since it mends a fault.
- **4, 5 and 6 depend on 3 and not on each other**: three lines that can go side by side, each in its own branch.
- **8.1 to 8.3** need 3 (and 0.5); their uses (8.4 to 8.6) need 5 and 6.
- **7** needs 3 (the walk in TypeScript), 6 (the comparison's sections) and 4 (derived's status shown).
- A pause for the user's word **after each phase**, and inside one wherever a step says **decide**.

## How the work is run

As in [the similarity build plan](similarity-build-plan.md#how-the-work-is-run):

- **Branches**: one for each phase, from `dev` (`spaces-0-ground`, `spaces-1-fault`, `spaces-2-fields`,
  `spaces-3-walk`, `spaces-4-readers`, `spaces-5-vectors`, `compare-6`, `spaces-7-interface`, `spaces-8-negatives`,
  `spaces-9-end`), merged into `dev` when its last step is green and the user says.
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

The agents of `.claude/agents/`: **`builder`** builds decided work from a written brief, with its tests, and does
not commit; **`test-runner`** makes every run; **`Explore`** reads the code for a question; **`solidjs-v2-reviewer`**
reads every interface diff. **Main**, the session holding this plan, settles what a step leaves open, makes every
change to a core read or write path (`context.py`, the meta and its checks, the walk, the verdict's maths), takes the
measurements, writes the briefs, reads each diff, writes "As built" and commits. ★ marks a step that gets a second
reading of its diff before it is committed.

## Phase 0: the ground

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **0.1 Why single relations share their lists** | Answered on the demo, read only: the sharing gives a document its place in the context of what follows it (the result of the demo's `Causes` has its cause in its context); a copy of the lists would lose it, and the narrower fix keeps it ([as found](semantic-spaces-plan.md#phase-0-as-found-2026-11-24)) | — | Main | **Done** 2026-11-24 |
| **0.2 What `stop` does, as a test** | Whether a statement inside `Negative` (`FastRPMeta(stop=True)`) is still joined to its own people, on a graph in memory (`pangloss_fastrp.maths.joins`): factoid → `Negative` → statement → person. Read so far: it is | Pure, in `pangloss-fastrp`'s unit tests, kept as a test of what the code does | Main | To do |
| **0.3 Who reads the spaces** | Every reader of the stored lists, by file: [the table above](#the-features-this-plan-changes) | — | Main | **Done** 2026-11-24 |
| **0.4 What a derived rule can read** | Whether a rule can read another rule's edges (a notable absence from an expectation and its denial, 8.3). Known already, from [derived.md](derived.md): a rule cannot say "unless" (no negation across documents, decided); its date conditions (`overlaps`, `within`) are generous by a date's uncertainty unless `strict=True`; and its facts are derived again when a write touches what it reads (`DerivedRegistry.triggers`). No arithmetic on dates is asked of a rule (the user, 2026-11-24): what an expectation needs of the data is in 8.2 and 8.3 | A written finding in 8.3's brief | `Explore`, read by main | To do |
| **0.5 A package's document about the project's statements** | `EventJudgement` (6.5) and `Expectation` (8.1) are documents that point at statements by citing them (so that Pangloss notices when a cited statement changes). They ship in packages, which do not know a project's statement classes, so the class takes the statement class as a parameter that the project fills in: `class StatementJudgement(EventJudgement[Statement])`. Pangloss has such parameters on wrappers (`Negative[T]`, `Identification[T]`); whether a top-level document can take one, and still be migrated and saved, has not been checked (phase 12's first question for its 12.2). If it cannot: the package ships a base class without the citing field, the project declares the field with its own class (`statements: list[Cites[Statement]]`), and `initialise()` checks that it did | A written finding in 6.5's and 8.1's briefs | `Explore`, then main | To do |
| **0.6 (removed)** | Was "how a field reached through wrappers is found from its class". Not a question: the code already reaches the entities behind wrappers (search's `through`: `held_field_names` and `wrappers_of` in `pangloss_models.search`; derived's rules match through them), and the field definitions know which field narrows which (`FieldSubclassing`). 2.5 and 6.1 reuse that | — | — | Removed 2026-11-24 |

## Phase 1: the fault in recording spaces

**Decide first** (D1): fix it, and how stored data is mended.

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **1.1 A space adds itself to new lists** | In `propagate_context`, a space gives what it holds new lists with itself added (`[*semantic_spaces, type]`, `[*context_labels, {"type": type}]`) and no longer appends to the lists it was given; all else as it is. `_InstanceContext` and the migrations' `StoredContext` share the one algorithm, so both follow | Pure, in `pangloss-models`, from the scratch trials (`/tmp/space-trial/`): two single slots each in a space, in a list and in a single field; a bare result after a cause in `Negative`; an order's space nested inside a cause; a result keeping its cause in its context; the existing context tests unchanged. Conformance: written and read back, on both backends | Main | To do |
| **1.2 Stored data mended** | `pangloss contexts check` (the heads whose stored lists differ from a recomputation, by class) and `pangloss contexts fix` (recompute those with `recompute_contexts`), run once by a project after upgrading, on the classes with two or more single relations to nodes of their own (from the models). `fix` marks each head it mends as written (`pending.mark_written`), so derived, the vectors and criteria find its facts again. The prototype of `check` is `/tmp/space-check/check_demo_contexts.py`. (The other way, a migration that `makemigrations` writes once: D1) | Live, both backends: a document written in the old shape (by hand, in the test); `check` finds it; `fix` mends it; `check` is clean; nothing else changes (nodes, edges, versions); a derived fact from the mended node is plain after the worker's turn | `builder` from main's brief | To do |
| **1.3 Docs** | [semantic-spaces.md](semantic-spaces.md): what is recorded, and the rule; the command (`guide/cli.md`); `status.md`; the item of `TODO.md` ticked | — | `builder` | To do |

## Phase 2: the four fields in the core

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **2.1 The fields and `Modal`** | On `SemanticSpaceMeta` (`model_bases/semantic_space.py`): `veridical: Literal[1, 0, -1] = 0`, `fit: Literal["describes", "prescribes"] = "describes"`, `logical: Literal["not"] \| Modal \| None = None`, `unary: bool \| None = None` (`None`: what `logical` implies, else `False`), inherited by the meta kit's default rule. `Modal(force, flavour, of_not=False)`, frozen: `force` `"necessity"` or `"possibility"`, `flavour` a non-empty word; exported from `pangloss_models` (`imports.md`). If D5 says so, a fifth field: the class's default degree for its contents (in the five steps of an `Expectation`), the strength of an order above a request. **Decide** (D2): `logical` as force and flavour | Pure: defaults; a family class sets values once, a subclass changes one and inherits the rest; `Modal`'s validation | Main | To do |
| **2.2 The checks at `initialise()`** | `initialise_models/check_semantic_spaces.py`, called where `check_label_templates` is (`model_registry.py`). Refused by the class's name, each a `PanglossModelError` with `fix=` (so the language server offers it): `"not"` with `veridical` other than `-1`; a possibility with `veridical` other than `0`; `-1` on a modal that is not a necessity `of_not`; `1` on a necessity `of_not`; `unary=False` on `"not"` or a modal `of_not`. A warning for two flavours that differ only in case | Pure: every refusal by its message and its `fix` | `builder` from main's brief | To do |
| **2.3 `unary` enforced** | A unary space's `contents` gets a length of at most one in its field definition (`initialise_field_definitions.py`), so `Create` and `Update` refuse a second item with a message that says why, and the interface's handling of a length (no "Add" past the last) follows. Measured: every space of the demo holds one item | Pure: two refused, one taken, the message; the export says the length | `builder` | To do |
| **2.4 Exported, not migrated** | `export.py` gives a space's `veridical`, `fit`, `logical` (`{"not": true}` or `{"force", "flavour", "ofNot"}`) and `unary`; `interface-core/src/types/models.ts` has them; `make-stubs` knows `Modal`. The migrations' snapshot (`migrations/diff.py`, its list of keys) is left as it is: the fields are not data | Pure: the export; `packages/pangloss-interface/tests/test_models_match_typescript.py`; a change of `veridical` makes no migration | `builder` | To do |
| **2.5 `Holder()` and `Addressee()`** | Field markers (`markers.py`, `FieldMarker`) on a relation of a statement class: who holds the attitude or gives the order, and to whom; at most one of each on a class, on a relation to agents, found through a reified relation (a proxy) by the code search already uses to reach what is behind a wrapper (`pangloss_models.search`). Exported (on a relation a marker is kept on the field's definition today, not exported). **Needed by fulfilment (6.2)**; **decide** (D3) | Pure: the checks; the marked fields of a class read through wrappers; the export | `builder` | Decide |
| **2.6 Docs and the skill** | [semantic-spaces.md](semantic-spaces.md) (the fields, ✅), [models.md](models.md), `imports.md`, the guide's statements page (`guide/tutorial/04-statements.md`), `status.md`; the skill's `references/modelling.md` (a new `Meta` option is one a newcomer needs to be told), and `check_skill.py` | The skill's check | `builder`, read by main | To do |

## Phase 3: the walk

| Step | What | Tests | Who | State |
|---|---|---|---|---|
| **3.1 `pangloss_models.spaces`** | `signature(context_labels) -> Signature`: the path from a node's `context_labels` (the spaces and the documents between them); each run of spaces next to each other normalised ([the table](semantic-space-fields.md#logical): within one flavour; `of_not`; a double "not"); then [the walk](semantic-space-fields.md#veridical): `veridical`, and the **degree** ([above](#the-degree-of-a-statements-contents)): `±1` for a committed path; for an uncommitted one the class's default, or the statement's own (an `Expectation`, or what a rule proposes: 8.1, 8.3), its sign what the lean was (for, against, neither); the `fit` of the innermost space that prescribes; the id of the statement holding it; the force and flavour of the innermost modal. Reads the classes' meta from the registry; no database | Pure: every row of the walk's table and of the normalising table; the two limits (two flavours never rewritten into each other; a statement between two spaces stops it); `Not[ChurchService(parts=[p])]`, which the flat list gets wrong. The cases are data (`space_cases.json`, beside the models' `label_cases.json`), which the TypeScript port (7.3) passes too | Main | To do |
| **3.2 Read from what is stored** | Where a package's query reads only `semantic_spaces`, it reads `context_labels` too: derived's `compile.py` (4.1), the library's clusters (4.3), the time part's rows (5.2) | Pure: the signature of a node read back (1.1's conformance write) | Main | To do |
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
| **6.5 `EventJudgement` and the route** | `EventJudgement[T]` in `pangloss-compare`, named by the project with its own root (0.5): `statements: list[Cites[T]]`, exactly two; `verdict`: agree, disagree, two events, carried out, carried out otherwise, not carried out, breach (**decide**, D7); `fields`: the fields disagreed on or the targets missed; `note`. `GET /api/compare/{type}/{ref}`: the pairs (6.3, 6.4), each with its relation (6.2), how it was found, and whether it is within one source; a person's judgement of a pair overrides (the newest wins, all listed with who and when; one on a statement changed since cited still overrides, with that notice). A judgement is written by the ordinary `POST` of its class, logged in; nothing else is written | Live, both backends: a judgement overrides; the newest wins; changed since cited; nothing written by a lookup, on the error paths too; the reader's visibility; a judgement the reader may not see does not show | `builder` ★ | To do |
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

Each is asked where its step says **decide**; none blocks the steps before it.

| | Decision | Step | Proposed |
|---|---|---|---|
| D1 | Fix the fault, and mend stored data by a command or by a migration | 1 | A command, `pangloss contexts check \| fix` |
| D2 | `logical` as force and flavour, the flavour the project's own word | 2.1 | Yes |
| D3 | `Holder()` and `Addressee()` field markers | 2.5 | Yes (fulfilment needs the addressee) |
| D4 | Which packages follow the fields: derived (4.1), criteria (4.2), identity claims (4.3), RDF (4.4); the time part (5.2: `-1` only, or `0` too); the graph part (5.3: what `stop` does, weights); the actual network (5.4); reconciliation (5.5) | 4, 5 | Derived, criteria, identity, RDF; time `-1` only; the rest after their measurements |
| D5 | `orientation` (before or after); and strength, which is now the class's default degree for its contents: a fifth field on `SemanticSpaceMeta`, or each package's slot | 2.1, 6.1, 6.2 | `orientation` in `CompareMeta`; the default degree as a fifth field, since several packages read it |
| D6 | The verdict's relations, fulfilment's matching, and "the same factoid" and "the same source" as features | 6.2, 6.3 | Yes |
| D7 | `EventJudgement`'s verdicts | 6.5 | Agree, disagree, two events, carried out, carried out otherwise, not carried out, breach |
| D8 | The forms: headless spaces (by default, or asked for), "not" as a toggle, marks of what is not asserted | 7.1-7.3 | Asked for, as on reified relations; the toggle; the marks |
| D9 | Negatives and prescriptions: one gradient (the historian's) and the source's side (whose expectation); a prescription's degree as evidence that it happened; where the judgement lives; how it is proposed; which classes of statement defeat a rule of expectation (an option of the rule, weighed when shown); which uses | 8 | `Expectation[T]`, keeping what was computed when judged; the project's rules and the guard; defeating classes named on the rule; the uses one by one |
| D10 | The demo: subjunctives as commands, or split; `Negative` split; `Hypothetical` compared | 9.1 | Commands; no split yet; compared, as "might have" |
| D11 | The profile pairs by vectors use | 6.4 | One of the structural network |
| D12 | The word to start, and phase 12's hold lifted | 0 | — |

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
